# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Chat Session History API Lambda Handler.

Implements Pattern 2 ("Memory + DynamoDB, metadata only" flavor) from
docs/SESSION_MANAGEMENT.md:

- AgentCore Memory (the "AgentMemory" resource created in backend-construct.ts)
  remains the single source of truth for actual conversation content — this
  Lambda never writes conversation messages anywhere. The agent runtime keeps
  writing to Memory exactly as it always has.
- DynamoDB stores only per-session metadata (name, createdAt, updatedAt), so
  the sidebar can list a user's sessions sorted by recency with one fast
  Query, instead of one ListEvents call per session.

Endpoints (all require a Cognito-authenticated request; userId is taken from
the JWT "sub" claim, never from the request body/path, to prevent a user from
reading/deleting another user's sessions):

    GET    /sessions              -> list this user's sessions, newest first
    GET    /sessions/{sessionId}  -> session metadata + full message history
    PUT    /sessions/{sessionId}  -> upsert metadata ("touch"); generates a
                                      title via Bedrock on first touch only
    DELETE /sessions/{sessionId}  -> delete metadata + best-effort Memory cleanup
"""

import os
import time
from typing import Any, Dict, List, Optional

import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, CORSConfig
from aws_lambda_powertools.logging.correlation_paths import API_GATEWAY_REST
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# Environment variables
TABLE_NAME = os.environ["TABLE_NAME"]
MEMORY_ID = os.environ["MEMORY_ID"]
TITLE_MODEL_ID = os.environ["TITLE_MODEL_ID"]
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "*")

# Parse CORS origins - can be comma-separated list
cors_origins = [
    origin.strip() for origin in CORS_ALLOWED_ORIGINS.split(",") if origin.strip()
]
primary_origin = cors_origins[0] if cors_origins else "*"
extra_origins = cors_origins[1:] if len(cors_origins) > 1 else None

cors_config = CORSConfig(
    allow_origin=primary_origin,
    extra_origins=extra_origins,
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)

dynamodb = boto3.client("dynamodb")
bedrock_runtime = boto3.client("bedrock-runtime")
agentcore_data_plane = boto3.client("bedrock-agentcore")

tracer = Tracer()
logger = Logger()
app = APIGatewayRestResolver(cors=cors_config)

# Validation constants
MAX_SESSION_ID_LENGTH = 100
MAX_MESSAGE_LENGTH = 5000
FALLBACK_TITLE_LENGTH = 50
TITLE_GENERATION_TIMEOUT_SECONDS = 8


class TouchSessionRequest(BaseModel):
    """
    Request payload for PUT /sessions/{sessionId} ("touch").

    Accepts camelCase from the client but uses snake_case internally.

    Attributes:
        first_user_message: The first user message of the conversation, used
            to generate a title on the session's first touch (and as the
            fallback title if title generation fails).
        first_assistant_message: The first assistant response, optionally
            included to give the title-generation model more context.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    first_user_message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    first_assistant_message: Optional[str] = Field(None, max_length=MAX_MESSAGE_LENGTH)


def _get_user_id() -> Optional[str]:
    """
    Extract the Cognito user sub ("userId") from the request's authorizer claims.

    Returns:
        Optional[str]: The Cognito user sub, or None if the request has no
            authorizer claims (should not normally happen, since every route
            is protected by the Cognito authorizer at the API Gateway level).
    """
    request_context = app.current_event.request_context
    authorizer = request_context.authorizer
    claims = authorizer.get("claims", {}) if authorizer else {}
    return claims.get("sub")


def _generate_session_title(
    first_user_message: str, first_assistant_message: Optional[str]
) -> str:
    """
    Generate a short, descriptive session title using Claude Haiku.

    Falls back to a truncated version of the first user message if the
    Bedrock call fails or returns an unusable response — title generation
    must never block or fail the "touch" request.

    Args:
        first_user_message: The first user message of the conversation.
        first_assistant_message: The first assistant response, if available,
            used to give the model more context for a better title.

    Returns:
        str: A short session title (never empty).
    """
    fallback_title = (
        first_user_message[:FALLBACK_TITLE_LENGTH].strip() or "Nova conversa"
    )

    prompt_parts = [f"Mensagem do usuario: {first_user_message}"]
    if first_assistant_message:
        prompt_parts.append(f"Resposta do assistente: {first_assistant_message}")
    conversation_excerpt = "\n".join(prompt_parts)

    prompt = (
        "Gere um titulo curto (no maximo 6 palavras, em portugues, sem aspas "
        "e sem pontuacao final) que resuma o assunto da conversa abaixo.\n\n"
        f"{conversation_excerpt}\n\nTitulo:"
    )

    try:
        response = bedrock_runtime.invoke_model(
            modelId=TITLE_MODEL_ID,
            body=_build_claude_request_body(prompt),
            contentType="application/json",
            accept="application/json",
        )
        response_body = _parse_claude_response_body(response)
        generated_title = response_body.strip().strip('"').strip()
        return (
            generated_title[:FALLBACK_TITLE_LENGTH]
            if generated_title
            else fallback_title
        )
    except Exception as exc:  # noqa: BLE001 - any failure must fall back, not raise
        logger.warning(f"Title generation failed, using fallback: {exc}")
        return fallback_title


def _build_claude_request_body(prompt: str) -> str:
    """
    Build the Bedrock Messages API request body for a Claude model.

    Args:
        prompt: The user prompt to send to the model.

    Returns:
        str: JSON-encoded request body for bedrock_runtime.invoke_model.
    """
    import json

    return json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 30,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}],
        }
    )


def _parse_claude_response_body(response: Dict[str, Any]) -> str:
    """
    Parse the text content out of a Bedrock Claude Messages API response.

    Args:
        response: The raw response from bedrock_runtime.invoke_model.

    Returns:
        str: The text content of the model's reply.
    """
    import json

    response_body = json.loads(response["body"].read())
    content_blocks = response_body.get("content", [])
    text_blocks = [
        block.get("text", "") for block in content_blocks if block.get("type") == "text"
    ]
    return "".join(text_blocks)


def _extract_message_text(raw_text: str) -> str:
    """
    Extract the plain display text from a Memory event's conversational content.

    The Strands AgentCoreMemorySessionManager stores each turn as a JSON
    string with a nested Strands message structure, not plain text, e.g.:

        '{"message": {"role": "assistant",
                       "content": [{"text": "actual reply text"}]},
          "message_id": 0, ...}'

    This unwraps that structure to get the actual text. Falls back to the
    raw string as-is if it isn't in this expected JSON shape (e.g. future
    format changes, or content produced by a different agent pattern) —
    better to show something than to raise and break the whole session view.

    Args:
        raw_text: The raw "text" field from a Memory event's conversational content.

    Returns:
        str: The extracted plain text, or the original raw_text if parsing fails.
    """
    import json

    try:
        parsed = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return raw_text

    content_blocks = parsed.get("message", {}).get("content", [])
    text_blocks = [block.get("text", "") for block in content_blocks if "text" in block]
    extracted = "".join(text_blocks)
    return extracted if extracted else raw_text


def _list_session_events_as_messages(
    user_id: str, session_id: str
) -> List[Dict[str, Any]]:
    """
    Fetch a session's conversation history from AgentCore Memory and convert
    it into the frontend's Message[] shape.

    Args:
        user_id: The Cognito user sub, used as the Memory actorId.
        session_id: The session ID to read events for.

    Returns:
        List[Dict[str, Any]]: Messages in chronological order (oldest first),
            each with "role" ("user" | "assistant"), "content", and "timestamp".
    """
    messages: List[Dict[str, Any]] = []
    next_token: Optional[str] = None

    while True:
        kwargs: Dict[str, Any] = {
            "memoryId": MEMORY_ID,
            "actorId": user_id,
            "sessionId": session_id,
            "includePayloads": True,
        }
        if next_token:
            kwargs["nextToken"] = next_token

        response = agentcore_data_plane.list_events(**kwargs)

        for event in response.get("events", []):
            event_timestamp = event.get("eventTimestamp")
            for payload_item in event.get("payload", []):
                conversational = payload_item.get("conversational")
                if not conversational:
                    continue
                role = (
                    "assistant" if conversational.get("role") == "ASSISTANT" else "user"
                )
                raw_text = conversational.get("content", {}).get("text", "")
                text = _extract_message_text(raw_text)
                messages.append(
                    {
                        "role": role,
                        "content": text,
                        "timestamp": str(event_timestamp) if event_timestamp else "",
                    }
                )

        next_token = response.get("nextToken")
        if not next_token:
            break

    # AgentCore Memory returns events newest-first; reverse for chronological display.
    messages.reverse()
    return messages


def _delete_session_events_best_effort(user_id: str, session_id: str) -> None:
    """
    Best-effort deletion of a session's events from AgentCore Memory.

    Failures are logged but never raised — the DynamoDB metadata row (deleted
    by the caller) is the authoritative record for whether a session is
    "deleted" from the user's perspective. A partially-cleaned-up Memory
    session does not affect the sidebar listing.

    Args:
        user_id: The Cognito user sub, used as the Memory actorId.
        session_id: The session ID whose events should be deleted.
    """
    try:
        next_token: Optional[str] = None
        while True:
            kwargs: Dict[str, Any] = {
                "memoryId": MEMORY_ID,
                "actorId": user_id,
                "sessionId": session_id,
            }
            if next_token:
                kwargs["nextToken"] = next_token

            response = agentcore_data_plane.list_events(**kwargs)
            for event in response.get("events", []):
                event_id = event.get("eventId")
                if not event_id:
                    continue
                try:
                    agentcore_data_plane.delete_event(
                        memoryId=MEMORY_ID,
                        actorId=user_id,
                        sessionId=session_id,
                        eventId=event_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to delete event {event_id}: {exc}")

            next_token = response.get("nextToken")
            if not next_token:
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"Best-effort Memory cleanup failed for session {session_id}: {exc}"
        )


@app.get("/sessions")
def list_sessions() -> Any:
    """
    Handle GET /sessions — list the authenticated user's chat sessions.

    Returns:
        List of session metadata dicts, sorted by updatedAt descending.
    """
    user_id = _get_user_id()
    if not user_id:
        return {"error": "Unauthorized"}, 401

    try:
        response = dynamodb.query(
            TableName=TABLE_NAME,
            KeyConditionExpression="userId = :userId",
            ExpressionAttributeValues={":userId": {"S": user_id}},
        )

        sessions = [
            {
                "sessionId": item["sessionId"]["S"],
                "name": item["name"]["S"],
                "createdAt": item["createdAt"]["S"],
                "updatedAt": item["updatedAt"]["S"],
            }
            for item in response.get("Items", [])
        ]
        sessions.sort(key=lambda s: s["updatedAt"], reverse=True)
        return sessions

    except ClientError as e:
        logger.error(
            f"DynamoDB error listing sessions: {e.response['Error']['Message']}"
        )
        return {"error": "Internal server error"}, 500


@app.get("/sessions/<session_id>")
def get_session(session_id: str) -> Any:
    """
    Handle GET /sessions/{sessionId} — return metadata plus full conversation
    history (read live from AgentCore Memory).

    Args:
        session_id: The session ID from the URL path.

    Returns:
        Session metadata merged with a "messages" list, or 404 if the
        session's metadata row does not exist for this user.
    """
    user_id = _get_user_id()
    if not user_id:
        return {"error": "Unauthorized"}, 401

    if len(session_id) > MAX_SESSION_ID_LENGTH:
        return {"error": "Invalid sessionId"}, 400

    try:
        response = dynamodb.get_item(
            TableName=TABLE_NAME,
            Key={"userId": {"S": user_id}, "sessionId": {"S": session_id}},
        )
        item = response.get("Item")
        if not item:
            return {"error": "Session not found"}, 404

        messages = _list_session_events_as_messages(user_id, session_id)

        return {
            "sessionId": item["sessionId"]["S"],
            "name": item["name"]["S"],
            "createdAt": item["createdAt"]["S"],
            "updatedAt": item["updatedAt"]["S"],
            "messages": messages,
        }

    except ClientError as e:
        logger.error(
            f"DynamoDB error reading session: {e.response['Error']['Message']}"
        )
        return {"error": "Internal server error"}, 500
    except Exception as e:  # noqa: BLE001 - AgentCore Memory client errors
        logger.error(f"Error reading session history from Memory: {str(e)}")
        return {"error": "Internal server error"}, 500


@app.put("/sessions/<session_id>")
def touch_session(session_id: str) -> Any:
    """
    Handle PUT /sessions/{sessionId} — upsert session metadata ("touch").

    On the session's first touch (no existing metadata row), generates a
    title via Bedrock and creates the row. On subsequent touches, only
    refreshes updatedAt — the title is never regenerated, avoiding repeated
    Bedrock calls and letting a user-renamed title (future feature) persist.

    Args:
        session_id: The session ID from the URL path.

    Returns:
        The upserted session metadata dict.
    """
    user_id = _get_user_id()
    if not user_id:
        return {"error": "Unauthorized"}, 401

    if len(session_id) > MAX_SESSION_ID_LENGTH:
        return {"error": "Invalid sessionId"}, 400

    try:
        touch_data = TouchSessionRequest(**app.current_event.json_body)
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return {"error": str(e)}, 400

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    try:
        existing = dynamodb.get_item(
            TableName=TABLE_NAME,
            Key={"userId": {"S": user_id}, "sessionId": {"S": session_id}},
        ).get("Item")

        if existing:
            # Subsequent touch: only refresh updatedAt, keep the existing title.
            dynamodb.update_item(
                TableName=TABLE_NAME,
                Key={"userId": {"S": user_id}, "sessionId": {"S": session_id}},
                UpdateExpression="SET updatedAt = :updatedAt",
                ExpressionAttributeValues={":updatedAt": {"S": now_iso}},
            )
            return {
                "sessionId": session_id,
                "name": existing["name"]["S"],
                "createdAt": existing["createdAt"]["S"],
                "updatedAt": now_iso,
            }

        # First touch: generate a title and create the row.
        title = _generate_session_title(
            touch_data.first_user_message, touch_data.first_assistant_message
        )
        dynamodb.put_item(
            TableName=TABLE_NAME,
            Item={
                "userId": {"S": user_id},
                "sessionId": {"S": session_id},
                "name": {"S": title},
                "createdAt": {"S": now_iso},
                "updatedAt": {"S": now_iso},
            },
        )
        return {
            "sessionId": session_id,
            "name": title,
            "createdAt": now_iso,
            "updatedAt": now_iso,
        }

    except ClientError as e:
        logger.error(
            f"DynamoDB error touching session: {e.response['Error']['Message']}"
        )
        return {"error": "Internal server error"}, 500


@app.delete("/sessions/<session_id>")
def delete_session(session_id: str) -> Any:
    """
    Handle DELETE /sessions/{sessionId} — delete session metadata and attempt
    best-effort cleanup of the corresponding AgentCore Memory events.

    Args:
        session_id: The session ID from the URL path.

    Returns:
        {"success": True} on success (DynamoDB deletion is authoritative;
        Memory cleanup failures are logged but do not fail this request).
    """
    user_id = _get_user_id()
    if not user_id:
        return {"error": "Unauthorized"}, 401

    if len(session_id) > MAX_SESSION_ID_LENGTH:
        return {"error": "Invalid sessionId"}, 400

    try:
        dynamodb.delete_item(
            TableName=TABLE_NAME,
            Key={"userId": {"S": user_id}, "sessionId": {"S": session_id}},
        )
    except ClientError as e:
        logger.error(
            f"DynamoDB error deleting session: {e.response['Error']['Message']}"
        )
        return {"error": "Internal server error"}, 500

    _delete_session_events_best_effort(user_id, session_id)

    return {"success": True}


@logger.inject_lambda_context(correlation_id_path=API_GATEWAY_REST)
def handler(event: dict, context: LambdaContext) -> dict:
    """
    Lambda handler for the chat session history API.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    return app.resolve(event, context)
