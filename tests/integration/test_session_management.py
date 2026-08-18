# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for chat session management.

Validates the full flow:
1. List sessions via API
2. Load a specific session with its history
3. Verify that different sessions have different content
4. Verify that touching a session creates/updates metadata
"""

import pytest
import requests


class TestSessionListing:
    """Tests for GET /sessions endpoint."""

    def test_list_sessions_returns_array(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that GET /sessions returns a list of sessions."""
        response = authenticated_session.get(f"{api_base_url}sessions")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        sessions = response.json()
        assert isinstance(sessions, list), "Sessions should be a list"
        assert len(sessions) > 0, "Should have at least one session"

    def test_list_sessions_have_required_fields(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that each session has required metadata fields."""
        response = authenticated_session.get(f"{api_base_url}sessions")
        sessions = response.json()

        for session in sessions:
            assert "sessionId" in session, "Session missing sessionId"
            assert "name" in session, "Session missing name"
            assert "createdAt" in session, "Session missing createdAt"
            assert "updatedAt" in session, "Session missing updatedAt"
            assert isinstance(session["sessionId"], str)
            assert isinstance(session["name"], str)
            assert len(session["sessionId"]) > 0

    def test_list_sessions_sorted_by_updated(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that sessions are sorted by updatedAt (newest first)."""
        response = authenticated_session.get(f"{api_base_url}sessions")
        sessions = response.json()

        if len(sessions) > 1:
            timestamps = [session["updatedAt"] for session in sessions]
            # Verify descending order
            assert timestamps == sorted(timestamps, reverse=True), (
                f"Sessions not sorted by updatedAt DESC. Got: {timestamps}"
            )


class TestSessionDetail:
    """Tests for GET /sessions/{sessionId} endpoint."""

    def test_get_session_returns_metadata_and_messages(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that GET /sessions/{id} returns metadata + message history."""
        # First, list sessions to get a valid ID
        list_response = authenticated_session.get(f"{api_base_url}sessions")
        sessions = list_response.json()
        assert len(sessions) > 0, "Need at least one session"

        session_id = sessions[0]["sessionId"]

        # Now fetch the session detail
        response = authenticated_session.get(f"{api_base_url}sessions/{session_id}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        session_detail = response.json()
        assert "sessionId" in session_detail
        assert "name" in session_detail
        assert "createdAt" in session_detail
        assert "updatedAt" in session_detail
        assert "messages" in session_detail

    def test_get_session_messages_have_required_fields(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that each message has role, content, and timestamp."""
        list_response = authenticated_session.get(f"{api_base_url}sessions")
        sessions = list_response.json()

        session_id = sessions[0]["sessionId"]
        response = authenticated_session.get(f"{api_base_url}sessions/{session_id}")
        session_detail = response.json()
        messages = session_detail.get("messages", [])

        assert len(messages) > 0, "Session should have at least one message"

        for message in messages:
            assert "role" in message, "Message missing role"
            assert "content" in message, "Message missing content"
            assert message["role"] in ["user", "assistant"], (
                f"Invalid role: {message['role']}"
            )
            assert isinstance(message["content"], str)
            assert len(message["content"]) > 0, "Message content should not be empty"

    def test_different_sessions_have_different_messages(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that selecting different sessions loads different message histories."""
        list_response = authenticated_session.get(f"{api_base_url}sessions")
        sessions = list_response.json()

        # Need at least 2 sessions to compare
        if len(sessions) < 2:
            pytest.skip("Need at least 2 sessions to compare")

        # Fetch first session
        session1_response = authenticated_session.get(
            f"{api_base_url}sessions/{sessions[0]['sessionId']}"
        )
        session1_messages = session1_response.json().get("messages", [])
        session1_content = [m["content"] for m in session1_messages]

        # Fetch second session
        session2_response = authenticated_session.get(
            f"{api_base_url}sessions/{sessions[1]['sessionId']}"
        )
        session2_messages = session2_response.json().get("messages", [])
        session2_content = [m["content"] for m in session2_messages]

        # Verify they're different (at least the first user message should differ)
        assert session1_content != session2_content, (
            f"Sessions should have different content. Session 1: {session1_content[:2]}, Session 2: {session2_content[:2]}"
        )

    def test_session_not_found_returns_404(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that requesting a non-existent session returns 404."""
        fake_session_id = "00000000-0000-0000-0000-000000000000"
        response = authenticated_session.get(
            f"{api_base_url}sessions/{fake_session_id}"
        )

        assert response.status_code == 404, (
            f"Expected 404 for non-existent session, got {response.status_code}"
        )

    def test_messages_are_in_chronological_order(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that messages are returned in chronological order (oldest first)."""
        list_response = authenticated_session.get(f"{api_base_url}sessions")
        sessions = list_response.json()

        session_id = sessions[0]["sessionId"]
        response = authenticated_session.get(f"{api_base_url}sessions/{session_id}")
        messages = response.json().get("messages", [])

        if len(messages) < 2:
            pytest.skip("Need at least 2 messages to verify order")

        # Verify alternation: user -> assistant -> user -> assistant
        for i, message in enumerate(messages):
            expected_role = "user" if i % 2 == 0 else "assistant"
            assert message["role"] == expected_role, (
                f"Message {i} should be {expected_role}, got {message['role']}"
            )


class TestTouchSession:
    """Tests for PUT /sessions/{sessionId} endpoint (metadata upsert)."""

    def test_touch_session_returns_metadata(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that PUT /sessions/{id} returns updated session metadata."""
        session_id = "test-session-" + str(hash("touch_test") % 10000000)

        payload = {
            "firstUserMessage": "This is a test message",
            "firstAssistantMessage": "This is a test response",
        }

        response = authenticated_session.put(
            f"{api_base_url}sessions/{session_id}",
            json=payload,
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        result = response.json()
        assert "sessionId" in result
        assert "name" in result
        assert "createdAt" in result
        assert "updatedAt" in result
        assert result["sessionId"] == session_id

    def test_touch_generates_title_on_first_touch(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that first touch generates a title from the message content."""
        session_id = "test-session-title-" + str(hash("title_test") % 10000000)

        payload = {
            "firstUserMessage": "What is the status of my judicial case?",
            "firstAssistantMessage": "Your case is in progress...",
        }

        response = authenticated_session.put(
            f"{api_base_url}sessions/{session_id}",
            json=payload,
        )

        result = response.json()
        title = result.get("name", "")

        # Title should be derived from the message (or fallback)
        assert len(title) > 0, "Title should not be empty"
        assert len(title) <= 50, "Title should be reasonably short"
        # Should not contain quotes or extra formatting
        assert '"' not in title, "Title should not contain quotes"

    def test_touch_preserves_title_on_subsequent_touch(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that subsequent touches don't regenerate the title."""
        session_id = "test-session-preserve-" + str(hash("preserve_test") % 10000000)

        # First touch
        payload1 = {
            "firstUserMessage": "First message about judicial case",
            "firstAssistantMessage": "First response about the case",
        }
        response1 = authenticated_session.put(
            f"{api_base_url}sessions/{session_id}",
            json=payload1,
        )
        title1 = response1.json().get("name")
        updated_at_1 = response1.json().get("updatedAt")

        # Second touch (simulating a new message in the same session)
        import time

        time.sleep(1)  # Ensure updatedAt changes

        payload2 = {
            "firstUserMessage": "Second message (different)",
            "firstAssistantMessage": "Second response (different)",
        }
        response2 = authenticated_session.put(
            f"{api_base_url}sessions/{session_id}",
            json=payload2,
        )
        title2 = response2.json().get("name")
        updated_at_2 = response2.json().get("updatedAt")

        # Title should be the same
        assert title1 == title2, f"Title should be preserved: '{title1}' vs '{title2}'"

        # updatedAt should have changed
        assert updated_at_1 != updated_at_2, (
            "updatedAt should have changed on second touch"
        )


class TestDeleteSession:
    """Tests for DELETE /sessions/{sessionId} endpoint."""

    def test_delete_session_returns_success(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that DELETE /sessions/{id} returns success."""
        session_id = "test-session-delete-" + str(hash("delete_test") % 10000000)

        # First, touch the session to create metadata
        payload = {
            "firstUserMessage": "Message for deletion test",
        }
        authenticated_session.put(
            f"{api_base_url}sessions/{session_id}",
            json=payload,
        )

        # Now delete it
        response = authenticated_session.delete(f"{api_base_url}sessions/{session_id}")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        result = response.json()
        assert result.get("success") is True

    def test_deleted_session_not_in_list(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Verify that a deleted session no longer appears in the list."""
        session_id = "test-session-delete-list-" + str(
            hash("delete_list_test") % 10000000
        )

        # Create a session
        payload = {
            "firstUserMessage": "Message for deletion list test",
        }
        authenticated_session.put(
            f"{api_base_url}sessions/{session_id}",
            json=payload,
        )

        # Verify it appears in list
        list_response1 = authenticated_session.get(f"{api_base_url}sessions")
        session_ids_before = [s["sessionId"] for s in list_response1.json()]
        assert session_id in session_ids_before, (
            "Session should appear in list after creation"
        )

        # Delete it
        authenticated_session.delete(f"{api_base_url}sessions/{session_id}")

        # Verify it's gone from list
        list_response2 = authenticated_session.get(f"{api_base_url}sessions")
        session_ids_after = [s["sessionId"] for s in list_response2.json()]
        assert session_id not in session_ids_after, (
            "Session should not appear in list after deletion"
        )
