# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Direct API integration tests using boto3 clients (no Selenium required).

These tests validate the sessions API by making direct boto3 calls to the Lambda.
"""

import json

import boto3
import pytest


@pytest.fixture
def lambda_client():
    """AWS Lambda client for direct invocation."""
    return boto3.client("lambda", region_name="us-east-1")


@pytest.fixture
def user_id():
    """Test user ID (Cognito sub)."""
    return "e4589408-10d1-70e7-0bc3-a831f9c2ae4f"


def invoke_lambda(lambda_client, function_name, event):
    """Helper to invoke Lambda and extract response."""
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(event),
    )

    response_payload = json.loads(response["Payload"].read())
    if "body" in response_payload:
        return json.loads(response_payload["body"]), response_payload.get(
            "statusCode", 200
        )
    return response_payload, response_payload.get("statusCode", 200)


class TestSessionsAPIDirect:
    """Direct Lambda invocation tests for sessions API."""

    def test_list_sessions_api(self, lambda_client, user_id):
        """Test GET /sessions via direct Lambda invocation."""
        event = {
            "httpMethod": "GET",
            "path": "/sessions",
            "resource": "/sessions",
            "headers": {},
            "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
            "multiValueHeaders": {},
            "queryStringParameters": None,
            "multiValueQueryStringParameters": None,
            "pathParameters": None,
            "stageVariables": None,
            "body": None,
            "isBase64Encoded": False,
        }

        response, status_code = invoke_lambda(
            lambda_client, "juris-consult-sessions", event
        )

        assert status_code == 200, f"Expected 200, got {status_code}: {response}"
        assert isinstance(response, list), "Response should be a list"

        if len(response) > 0:
            session = response[0]
            assert "sessionId" in session
            assert "name" in session
            assert "createdAt" in session
            assert "updatedAt" in session

    def test_get_session_detail_api(self, lambda_client, user_id):
        """Test GET /sessions/{sessionId} via direct Lambda invocation."""
        # First, list sessions to get a valid ID
        list_event = {
            "httpMethod": "GET",
            "path": "/sessions",
            "resource": "/sessions",
            "headers": {},
            "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
            "multiValueHeaders": {},
            "queryStringParameters": None,
            "multiValueQueryStringParameters": None,
            "pathParameters": None,
            "stageVariables": None,
            "body": None,
            "isBase64Encoded": False,
        }

        sessions, _ = invoke_lambda(lambda_client, "juris-consult-sessions", list_event)

        if not sessions:
            pytest.skip("No sessions available")

        session_id = sessions[0]["sessionId"]

        # Now get the session detail
        detail_event = {
            "httpMethod": "GET",
            "path": f"/sessions/{session_id}",
            "resource": "/sessions/{sessionId}",
            "headers": {},
            "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
            "multiValueHeaders": {},
            "queryStringParameters": None,
            "multiValueQueryStringParameters": None,
            "pathParameters": {"sessionId": session_id},
            "stageVariables": None,
            "body": None,
            "isBase64Encoded": False,
        }

        session_detail, status_code = invoke_lambda(
            lambda_client, "juris-consult-sessions", detail_event
        )

        assert status_code == 200, f"Expected 200, got {status_code}: {session_detail}"
        assert "sessionId" in session_detail
        assert "name" in session_detail
        assert "messages" in session_detail

        # Verify messages structure
        messages = session_detail.get("messages", [])
        if messages:
            msg = messages[0]
            assert "role" in msg
            assert "content" in msg
            assert msg["role"] in ["user", "assistant"]

    def test_different_sessions_have_different_content(self, lambda_client, user_id):
        """Verify that different sessions have different message content."""
        # List all sessions
        list_event = {
            "httpMethod": "GET",
            "path": "/sessions",
            "resource": "/sessions",
            "headers": {},
            "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
            "multiValueHeaders": {},
            "queryStringParameters": None,
            "multiValueQueryStringParameters": None,
            "pathParameters": None,
            "stageVariables": None,
            "body": None,
            "isBase64Encoded": False,
        }

        sessions, _ = invoke_lambda(lambda_client, "juris-consult-sessions", list_event)

        if len(sessions) < 2:
            pytest.skip("Need at least 2 sessions to compare")

        # Get details for first two sessions
        session1_messages = []
        session2_messages = []

        for i, sid in enumerate(sessions[:2]):
            detail_event = {
                "httpMethod": "GET",
                "path": f"/sessions/{sid['sessionId']}",
                "resource": "/sessions/{sessionId}",
                "headers": {},
                "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
                "multiValueHeaders": {},
                "queryStringParameters": None,
                "multiValueQueryStringParameters": None,
                "pathParameters": {"sessionId": sid["sessionId"]},
                "stageVariables": None,
                "body": None,
                "isBase64Encoded": False,
            }

            session_detail, _ = invoke_lambda(
                lambda_client, "juris-consult-sessions", detail_event
            )
            messages = [m["content"] for m in session_detail.get("messages", [])]

            if i == 0:
                session1_messages = messages
            else:
                session2_messages = messages

        # Verify they're different
        assert session1_messages != session2_messages, (
            f"Sessions should have different content.\nSession 1: {session1_messages[:2]}\nSession 2: {session2_messages[:2]}"
        )

    def test_sessions_sorted_by_updated(self, lambda_client, user_id):
        """Verify that sessions are sorted by updatedAt (newest first)."""
        list_event = {
            "httpMethod": "GET",
            "path": "/sessions",
            "resource": "/sessions",
            "headers": {},
            "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
            "multiValueHeaders": {},
            "queryStringParameters": None,
            "multiValueQueryStringParameters": None,
            "pathParameters": None,
            "stageVariables": None,
            "body": None,
            "isBase64Encoded": False,
        }

        sessions, _ = invoke_lambda(lambda_client, "juris-consult-sessions", list_event)

        if len(sessions) > 1:
            timestamps = [s["updatedAt"] for s in sessions]
            sorted_timestamps = sorted(timestamps, reverse=True)

            assert timestamps == sorted_timestamps, (
                f"Sessions not sorted by updatedAt DESC.\nGot: {timestamps}\nExpected: {sorted_timestamps}"
            )
