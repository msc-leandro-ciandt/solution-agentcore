# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Daily judicial case digest Lambda.

Runs once per day on an EventBridge Scheduler trigger (see
infra-cdk/lib/backend-construct.ts, createMonitoringDigest()). For each
monitored judicial case configured in config.yaml's monitoring.processes:

  1. Queries the DataJud (CNJ) Public API for the current case metadata.
  2. Compares the latest movement against the previously cached state in the
     ProcessDigestState DynamoDB table to detect what changed since the last run.
  3. Writes the new snapshot back to DynamoDB. This is the SAME table read by
     the consulta-processual Gateway tool Lambda
     (gateway/tools/consulta_processual/consulta_processual_lambda.py) to
     answer chat questions — that Lambda never calls DataJud itself.
  4. Sends a summary email via Amazon SES to the configured notification
     recipients, highlighting any new movements.

This is the ONLY Lambda in the system that calls the external DataJud API —
by design, to keep the chat-triggered Lambda's IAM footprint and latency
minimal. See PLAN_CONSULTA_PROCESSOS.md for the full rationale.

No external pip dependencies are used — only the Python standard library
(urllib, json, datetime) and boto3 (bundled in the Lambda runtime).
"""

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DataJud endpoint template — {tribunal} is the lowercase tribunal alias (tjrs, tjsc, ...)
DATAJUD_URL_TEMPLATE = (
    "https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search"
)

# Number of most recent movimentos (case events) to include in the email body.
MAX_MOVIMENTOS_NO_EMAIL = 5

_ssm_client = boto3.client("ssm")
_dynamodb_client = boto3.client("dynamodb")
_ses_client = boto3.client("sesv2")


def _load_monitored_processes() -> List[Dict[str, str]]:
    """
    Load the list of monitored judicial cases from the PROCESSOS_MONITORADOS
    environment variable (JSON-encoded, set by CDK from config.yaml's
    monitoring.processes section).

    Returns:
        List[Dict[str, str]]: Each entry has "label", "tribunal", and
            "numero_processo" string keys.

    Raises:
        ValueError: If the environment variable is missing or not valid JSON.
    """
    raw_value = os.environ.get("PROCESSOS_MONITORADOS")
    if not raw_value:
        raise ValueError("PROCESSOS_MONITORADOS environment variable is required")

    try:
        processes: List[Dict[str, str]] = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"PROCESSOS_MONITORADOS is not valid JSON: {exc}") from exc

    return processes


def _get_datajud_api_key(parameter_name: str) -> str:
    """
    Fetch the DataJud Public API key from AWS SSM Parameter Store.

    The DataJud API key is a public credential published by the CNJ (not a
    per-account secret) — it is stored in SSM rather than hardcoded so it can
    be rotated without a code change, in case the CNJ issues a new key.

    Args:
        parameter_name (str): Full SSM parameter name (e.g. "/my-stack/datajud_api_key").

    Returns:
        str: The current DataJud Public API key value.

    Raises:
        ValueError: If the parameter cannot be retrieved.
    """
    try:
        response = _ssm_client.get_parameter(Name=parameter_name)
        return response["Parameter"]["Value"]
    except Exception as exc:
        raise ValueError(
            f"Failed to retrieve DataJud API key from SSM parameter {parameter_name}: {exc}"
        ) from exc


def _query_datajud(
    tribunal: str, numero_processo: str, api_key: str
) -> Optional[Dict[str, Any]]:
    """
    Query the DataJud Public API for a single case by its unique CNJ case number.

    Args:
        tribunal (str): Lowercase tribunal alias (e.g. "tjrs", "tjsc").
        numero_processo (str): The CNJ unique case number, with or without
            punctuation (DataJud indexes it unformatted, punctuation is
            stripped before querying).
        api_key (str): The DataJud Public API key (see _get_datajud_api_key).

    Returns:
        Optional[Dict[str, Any]]: The first matching case document's "_source"
            field from the Elasticsearch response, or None if no case was found.

    Raises:
        RuntimeError: If the HTTP request to DataJud fails.
    """
    url = DATAJUD_URL_TEMPLATE.format(tribunal=tribunal)

    # DataJud indexes numeroProcesso without punctuation (only digits).
    numero_sem_pontuacao = "".join(ch for ch in numero_processo if ch.isdigit())

    query_body = {
        "query": {"match": {"numeroProcesso": numero_sem_pontuacao}},
        "size": 1,
    }

    request_data = json.dumps(query_body).encode("utf-8")
    request = urllib.request.Request(  # nosec B310 — fixed, hardcoded HTTPS host, not user-controlled
        url=url,
        data=request_data,
        method="POST",
        headers={
            "Authorization": f"APIKey {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # nosec B310 — fixed HTTPS host
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Failed to reach DataJud API for {tribunal}: {exc}"
        ) from exc

    hits = response_body.get("hits", {}).get("hits", [])
    if not hits:
        return None

    return hits[0].get("_source")


def _get_latest_movement(source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Find the most recent movimento (case event) in a DataJud case document.

    Args:
        source (Dict[str, Any]): The DataJud "_source" document for a case.

    Returns:
        Optional[Dict[str, Any]]: The movimento dict with the latest
            "dataHora", or None if the case has no movimentos.
    """
    movimentos = source.get("movimentos", []) or []
    if not movimentos:
        return None
    return max(movimentos, key=lambda m: m.get("dataHora", ""))


def _read_previous_state(
    table_name: str, numero_processo: str
) -> Optional[Dict[str, str]]:
    """
    Read the previously cached digest state for a case from DynamoDB, used to
    detect whether a new movement has appeared since the last run.

    Args:
        table_name (str): Name of the ProcessDigestState DynamoDB table.
        numero_processo (str): The CNJ unique case number (partition key).

    Returns:
        Optional[Dict[str, str]]: A dict with "ultimo_movimento_codigo" and
            "ultimo_movimento_data" string values, or None if no previous
            state exists (e.g. first run).
    """
    response = _dynamodb_client.get_item(
        TableName=table_name,
        Key={"numero_processo": {"S": numero_processo}},
    )
    item = response.get("Item")
    if not item:
        return None

    return {
        "ultimo_movimento_codigo": item.get("ultimo_movimento_codigo", {}).get("S", ""),
        "ultimo_movimento_data": item.get("ultimo_movimento_data", {}).get("S", ""),
    }


def _write_new_state(
    table_name: str,
    numero_processo: str,
    source: Optional[Dict[str, Any]],
    latest_movement: Optional[Dict[str, Any]],
    sync_timestamp: str,
) -> None:
    """
    Write the latest DataJud snapshot for a case to DynamoDB.

    This is the cache read by the consulta-processual Gateway tool Lambda to
    answer chat questions without calling DataJud itself. The "dados_json"
    attribute's structure — {"fonte": ..., "ultima_sincronizacao": ...} — must
    stay in sync with what that Lambda's _get_cached_case_state() expects.

    Args:
        table_name (str): Name of the ProcessDigestState DynamoDB table.
        numero_processo (str): The CNJ unique case number (partition key).
        source (Optional[Dict[str, Any]]): The DataJud "_source" document for
            the case, or None if the case was not found in this run.
        latest_movement (Optional[Dict[str, Any]]): The most recent movimento
            dict (see _get_latest_movement), or None.
        sync_timestamp (str): ISO 8601 timestamp of this synchronization run.
    """
    dados_json = json.dumps({"fonte": source, "ultima_sincronizacao": sync_timestamp})

    item: Dict[str, Dict[str, str]] = {
        "numero_processo": {"S": numero_processo},
        "dados_json": {"S": dados_json},
        "ultimo_movimento_codigo": {
            "S": str(latest_movement.get("codigo", "")) if latest_movement else ""
        },
        "ultimo_movimento_data": {
            "S": latest_movement.get("dataHora", "") if latest_movement else ""
        },
    }

    _dynamodb_client.put_item(TableName=table_name, Item=item)


def _build_case_email_section(
    label: str,
    numero_processo: str,
    source: Optional[Dict[str, Any]],
    latest_movement: Optional[Dict[str, Any]],
    previous_state: Optional[Dict[str, str]],
) -> str:
    """
    Build the plain-text email section for a single monitored case.

    Highlights whether a new movement was detected since the previous run,
    so the recipient does not have to re-read an unchanged status every day.

    Args:
        label (str): Human-friendly case label (e.g. "Processo TJSC").
        numero_processo (str): The CNJ unique case number.
        source (Optional[Dict[str, Any]]): The DataJud "_source" document for
            the case, or None if not found in this run.
        latest_movement (Optional[Dict[str, Any]]): The most recent movimento
            dict, or None.
        previous_state (Optional[Dict[str, str]]): The previously cached
            movement identifiers (see _read_previous_state), or None on first run.

    Returns:
        str: A formatted multi-line email section for this case.
    """
    if source is None:
        return (
            f"{label} ({numero_processo}):\n"
            "  Nao encontrado na base publica do DataJud nesta sincronizacao.\n"
        )

    classe = source.get("classe", {}).get("nome", "desconhecida")
    grau = source.get("grau", "desconhecido")
    orgao_julgador = source.get("orgaoJulgador", {}).get("nome", "desconhecido")

    if latest_movement is None:
        movimento_texto = "  (nenhuma movimentacao registrada)"
        houve_novidade = False
    else:
        movimento_texto = (
            f"  {latest_movement.get('dataHora', 'data desconhecida')}: "
            f"{latest_movement.get('nome', 'movimento sem descricao')}"
        )
        movimento_atual_data = latest_movement.get("dataHora", "")
        movimento_anterior_data = (previous_state or {}).get(
            "ultimo_movimento_data", ""
        )
        houve_novidade = movimento_atual_data != movimento_anterior_data

    destaque = (
        "*** NOVA MOVIMENTACAO DETECTADA ***"
        if houve_novidade
        else "(sem novidade desde ontem)"
    )

    return (
        f"{label} ({numero_processo})\n"
        f"  Classe: {classe} | Grau: {grau} | Orgao julgador: {orgao_julgador}\n"
        f"  Ultima movimentacao {destaque}:\n{movimento_texto}\n"
    )


def _send_digest_email(
    sender_email: str, recipient_emails: List[str], body_sections: List[str]
) -> None:
    """
    Send the daily digest email via Amazon SES.

    Args:
        sender_email (str): Verified SES sender identity (the "From" address).
        recipient_emails (List[str]): Verified SES recipient addresses.
        body_sections (List[str]): One formatted text section per monitored case.

    Raises:
        Exception: Propagates any SES send_email error (e.g. identity not verified).
    """
    subject = "JurisConsult — Atualizacao diaria dos processos monitorados"
    body_text = (
        "Resumo diario dos processos judiciais monitorados:\n\n"
        + "\n".join(body_sections)
        + "\nEste e um email automatico gerado pelo JurisConsult.\n"
    )

    _ses_client.send_email(
        FromEmailAddress=sender_email,
        Destination={"ToAddresses": recipient_emails},
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
            }
        },
    )


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    EventBridge Scheduler entrypoint for the daily judicial case digest.

    For each monitored case: queries DataJud, updates the DynamoDB cache used
    by the chat tool, and assembles one section of the digest email. Sends a
    single email covering all monitored cases to every configured recipient.

    Args:
        event (Dict[str, Any]): The EventBridge Scheduler event (unused —
            this Lambda takes no input, it always processes all monitored cases).
        context (Any): Lambda context (unused).

    Returns:
        Dict[str, Any]: A summary of the run, useful when invoked manually via
            `aws lambda invoke` for testing (see PLAN_CONSULTA_PROCESSOS.md).
    """
    logger.info("Starting daily judicial case digest run")

    monitored_processes = _load_monitored_processes()
    table_name = os.environ["DIGEST_STATE_TABLE_NAME"]
    datajud_api_key_param = os.environ["DATAJUD_API_KEY_PARAM"]
    sender_email = os.environ["SENDER_EMAIL"]
    recipient_emails = json.loads(os.environ["NOTIFICATION_EMAILS"])

    api_key = _get_datajud_api_key(datajud_api_key_param)
    sync_timestamp = datetime.now(timezone.utc).isoformat()

    email_sections: List[str] = []
    cases_processed = 0
    cases_with_new_movement = 0

    for process in monitored_processes:
        numero_processo = process["numero_processo"]
        tribunal = process["tribunal"]
        label = process["label"]

        try:
            source = _query_datajud(
                tribunal=tribunal, numero_processo=numero_processo, api_key=api_key
            )
        except Exception as exc:
            logger.error(f"Failed to query DataJud for {numero_processo}: {exc}")
            email_sections.append(
                f"{label} ({numero_processo}):\n  Erro ao consultar o DataJud nesta sincronizacao.\n"
            )
            continue

        latest_movement = _get_latest_movement(source) if source else None
        previous_state = _read_previous_state(table_name, numero_processo)

        email_sections.append(
            _build_case_email_section(
                label=label,
                numero_processo=numero_processo,
                source=source,
                latest_movement=latest_movement,
                previous_state=previous_state,
            )
        )

        if latest_movement is not None:
            movimento_atual_data = latest_movement.get("dataHora", "")
            movimento_anterior_data = (previous_state or {}).get(
                "ultimo_movimento_data", ""
            )
            if movimento_atual_data != movimento_anterior_data:
                cases_with_new_movement += 1

        _write_new_state(
            table_name=table_name,
            numero_processo=numero_processo,
            source=source,
            latest_movement=latest_movement,
            sync_timestamp=sync_timestamp,
        )
        cases_processed += 1

    _send_digest_email(
        sender_email=sender_email,
        recipient_emails=recipient_emails,
        body_sections=email_sections,
    )

    logger.info(
        f"Digest run complete: {cases_processed} cases processed, "
        f"{cases_with_new_movement} with new movements, email sent to {recipient_emails}"
    )

    return {
        "cases_processed": cases_processed,
        "cases_with_new_movement": cases_with_new_movement,
        "recipients": recipient_emails,
    }
