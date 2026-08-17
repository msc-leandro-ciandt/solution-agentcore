# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Gateway Lambda tool: consulta de processos judiciais monitorados.

DESIGN PATTERN:
Follows the "one tool per Lambda" pattern used across FAST Gateway tools (see
gateway/tools/sample_tool/sample_tool_lambda.py). This Lambda implements exactly
one tool: consultar_processo_judicial.

DATA SOURCE — CACHED, NOT LIVE:
This Lambda does NOT call the DataJud (CNJ) Public API directly. Instead, it
reads a cached snapshot from the ProcessDigestState DynamoDB table, which is
refreshed once per day by the separate process-digest Lambda
(infra-cdk/lambdas/process-digest/index.py) on the schedule configured in
config.yaml's monitoring.digest_schedule_cron.

This is an intentional design choice:
  - Judicial case status rarely changes more than once a day, so a daily
    snapshot is fresh enough for chat Q&A.
  - Keeping DataJud API calls confined to a single, scheduled Lambda avoids
    every chat message depending on an external, unauthenticated third-party
    API's availability and reduces the IAM/network footprint of the
    chat-triggered Lambda (no internet egress or DataJud API key needed here).
  - DynamoDB reads are far faster than an external HTTPS round trip, so chat
    responses are quicker.

If the daily digest has not run yet (e.g. right after deployment), the cache
will be empty for a given case. This Lambda returns an explicit message about
that rather than silently returning stale or fabricated data.

No external pip dependencies are used — only boto3 (bundled in the Lambda
runtime).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Number of most recent movimentos (case events) to include in the tool's response text.
MAX_MOVIMENTOS_RETORNADOS = 5

_dynamodb_client = boto3.client("dynamodb")


def _load_monitored_processes() -> List[Dict[str, str]]:
    """
    Load the allowlist of monitored judicial cases from the PROCESSOS_MONITORADOS
    environment variable.

    This variable is a JSON-encoded list set by CDK from config.yaml's
    monitoring.processes section. Each entry has "label", "tribunal", and
    "numero_processo" string keys.

    Returns:
        List[Dict[str, str]]: The list of monitored process definitions.

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


def _get_cached_case_state(
    table_name: str, numero_processo: str
) -> Optional[Dict[str, Any]]:
    """
    Read the cached DataJud snapshot for a single case from DynamoDB.

    The item is written by the process-digest Lambda once per day. Its shape
    matches the "_source" document returned by the DataJud API (see
    infra-cdk/lambdas/process-digest/index.py for the writer).

    Args:
        table_name (str): Name of the ProcessDigestState DynamoDB table.
        numero_processo (str): The CNJ unique case number, used as the table's
            partition key.

    Returns:
        Optional[Dict[str, Any]]: The cached case data (a plain Python dict,
            already unmarshalled from DynamoDB's typed attribute format), or
            None if no snapshot has been cached yet for this case.
    """
    response = _dynamodb_client.get_item(
        TableName=table_name,
        Key={"numero_processo": {"S": numero_processo}},
    )
    item = response.get("Item")
    if not item:
        return None

    # dados_json stores the full DataJud "_source" document as a JSON string,
    # written by the process-digest Lambda. See that Lambda for the writer side.
    dados_json = item.get("dados_json", {}).get("S")
    if not dados_json:
        return None

    return json.loads(dados_json)


def _format_case_summary(
    label: str, numero_processo: str, cached_state: Optional[Dict[str, Any]]
) -> str:
    """
    Format a single case's cached DataJud metadata into a human-readable text summary.

    Args:
        label (str): Human-friendly label for the case (e.g. "Processo TJSC").
        numero_processo (str): The CNJ unique case number, as configured.
        cached_state (Optional[Dict[str, Any]]): The cached DataJud "_source"
            document for the case (see _get_cached_case_state), or None if no
            snapshot has been cached yet.

    Returns:
        str: A formatted multi-line summary of the case status and recent movements.
    """
    if cached_state is None:
        return (
            f"{label} ({numero_processo}): ainda nao ha dados sincronizados para este "
            "processo. A atualizacao diaria automatica ainda nao foi executada pela "
            "primeira vez, ou o processo nao foi encontrado na ultima sincronizacao."
        )

    fonte = cached_state.get("fonte")
    if fonte is None:
        return (
            f"{label} ({numero_processo}): a ultima sincronizacao nao encontrou este "
            "processo na base publica do DataJud. O processo pode ainda nao ter sido "
            "indexado pelo tribunal, ou o numero configurado pode estar incorreto."
        )

    classe = fonte.get("classe", {}).get("nome", "desconhecida")
    grau = fonte.get("grau", "desconhecido")
    orgao_julgador = fonte.get("orgaoJulgador", {}).get("nome", "desconhecido")
    data_ajuizamento = fonte.get("dataAjuizamento", "desconhecida")

    assuntos = fonte.get("assuntos", []) or []
    assuntos_nomes = (
        ", ".join(a.get("nome", "") for a in assuntos if a.get("nome"))
        or "nao informado"
    )

    movimentos = fonte.get("movimentos", []) or []
    movimentos_ordenados = sorted(
        movimentos, key=lambda m: m.get("dataHora", ""), reverse=True
    )
    movimentos_recentes = movimentos_ordenados[:MAX_MOVIMENTOS_RETORNADOS]

    linhas_movimentos = (
        "\n".join(
            f"  - {m.get('dataHora', 'data desconhecida')}: {m.get('nome', 'movimento sem descricao')}"
            for m in movimentos_recentes
        )
        or "  (nenhuma movimentacao registrada)"
    )

    ultima_sincronizacao = cached_state.get("ultima_sincronizacao", "desconhecida")

    return (
        f"{label} ({numero_processo})\n"
        f"Classe: {classe} | Grau: {grau} | Ajuizado em: {data_ajuizamento}\n"
        f"Orgao julgador: {orgao_julgador}\n"
        f"Assuntos: {assuntos_nomes}\n"
        f"Ultimas {len(movimentos_recentes)} movimentacoes:\n{linhas_movimentos}\n"
        f"(Dados sincronizados em: {ultima_sincronizacao} — atualizado 1x por dia)"
    )


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Consulta de processos judiciais tool Lambda for the AgentCore Gateway.

    Reads cached case snapshots from DynamoDB — see module docstring for why
    this Lambda never calls the DataJud API directly.

    INPUT FORMAT:
    - event: Contains tool arguments directly (not wrapped in HTTP body).
      Expected key: "numero_processo" (str, optional).
    - context.client_context.custom['bedrockAgentCoreToolName']: Full tool
      name with target prefix, e.g. "consulta-processual-target___consultar_processo_judicial".

    OUTPUT FORMAT:
    - Returns an object with a 'content' array containing response text,
      matching the shape expected by the AgentCore Gateway.

    Args:
        event (Dict[str, Any]): Tool arguments passed directly from the gateway.
        context (Any): Lambda context with AgentCore metadata in client_context.custom.

    Returns:
        Dict[str, Any]: Response object with 'content' array, or an 'error' string.
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        delimiter = "___"
        original_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = original_tool_name[
            original_tool_name.index(delimiter) + len(delimiter) :
        ]

        if tool_name != "consultar_processo_judicial":
            logger.error(f"Unexpected tool name: {tool_name}")
            return {
                "error": (
                    "This Lambda only supports 'consultar_processo_judicial', "
                    f"received: {tool_name}"
                )
            }

        numero_processo_solicitado = event.get("numero_processo")

        monitored_processes = _load_monitored_processes()
        table_name = os.environ["DIGEST_STATE_TABLE_NAME"]

        if numero_processo_solicitado:
            # Enforce the allowlist — only monitored case numbers can be queried.
            matching = [
                p
                for p in monitored_processes
                if p["numero_processo"] == numero_processo_solicitado
            ]
            if not matching:
                allowed_numbers = ", ".join(
                    p["numero_processo"] for p in monitored_processes
                )
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"O numero de processo '{numero_processo_solicitado}' nao esta "
                                f"na lista de processos monitorados. Processos disponiveis: "
                                f"{allowed_numbers}"
                            ),
                        }
                    ]
                }
            processes_to_query = matching
        else:
            processes_to_query = monitored_processes

        summaries = []
        for process in processes_to_query:
            cached_state = _get_cached_case_state(
                table_name=table_name,
                numero_processo=process["numero_processo"],
            )
            summaries.append(
                _format_case_summary(
                    label=process["label"],
                    numero_processo=process["numero_processo"],
                    cached_state=cached_state,
                )
            )

        result_text = "\n\n".join(summaries)
        return {"content": [{"type": "text", "text": result_text}]}

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {"error": f"Internal server error: {str(e)}"}
