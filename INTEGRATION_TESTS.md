# Integration Tests for FAST Chat

This document describes the integration test suite for the FAST Chat application. Tests validate both the backend API (session management) and frontend UI (chat interface, session selection).

## Test Structure

- **`tests/integration/test_session_management.py`** - API tests for session endpoints
  - `TestSessionListing` - Tests for `GET /sessions`
  - `TestSessionDetail` - Tests for `GET /sessions/{sessionId}`
  - `TestTouchSession` - Tests for `PUT /sessions/{sessionId}`
  - `TestDeleteSession` - Tests for `DELETE /sessions/{sessionId}`

- **`tests/integration/test_frontend_ui.py`** - UI tests for browser interactions
  - `TestAuthentication` - Login flow validation
  - `TestChatInterface` - Chat UI functionality
  - `TestSessionSelection` - Session switching and history loading

- **`tests/integration/conftest.py`** - Pytest fixtures
  - `id_token` - Cognito authentication
  - `authenticated_session` - HTTP client with auth headers
  - `aws_client`, `dynamodb_client` - AWS SDK clients

## Prerequisites

### 1. Install Dependencies

```bash
pip install -r test_requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the project root or set these environment variables:

```bash
# Cognito test user credentials
TEST_EMAIL=leanpsilva@gmail.com
TEST_PASSWORD=Tifani%04

# Application URLs
BASE_URL=https://main.d3de0r2ujefnqj.amplifyapp.com
COGNITO_DOMAIN=juris-consult-455303857301-us-east-1.auth.us-east-1.amazoncognito.com

# AWS configuration
AWS_REGION=us-east-1
```

### 3. AWS Credentials

Ensure you have AWS credentials configured locally:

```bash
aws configure
# or set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY environment variables
```

### 4. Chrome Browser

UI tests require Chrome/Chromium. The tests use headless mode, so you don't need a display.

On Linux:
```bash
sudo apt-get install chromium-browser
```

On macOS:
```bash
brew install chromium
```

On Windows:
```bash
choco install chromium
```

## Running Tests

### Run All Tests

```bash
pytest tests/integration
```

### Run API Tests Only (No Browser Required)

```bash
pytest tests/integration/test_session_management.py -v
```

### Run UI Tests Only (Requires Browser)

```bash
pytest tests/integration/test_frontend_ui.py -v
```

### Run Specific Test Class

```bash
pytest tests/integration/test_session_management.py::TestSessionListing -v
```

### Run Specific Test

```bash
pytest tests/integration/test_session_management.py::TestSessionListing::test_list_sessions_returns_array -v
```

### Run with Markers

```bash
# Run only API tests
pytest -m api tests/integration

# Run only authentication tests
pytest -m auth tests/integration

# Run only slow tests
pytest -m slow tests/integration
```

### Run with Output

```bash
# Show detailed output and stop on first failure
pytest tests/integration -vv -x

# Show print statements
pytest tests/integration -vv -s

# Generate HTML report
pytest tests/integration --html=report.html --self-contained-html
```

## Test Scenarios Covered

### Session Management API

1. **List Sessions**
   - ✅ Returns array of sessions
   - ✅ Each session has required fields (sessionId, name, createdAt, updatedAt)
   - ✅ Sessions are sorted by updatedAt (newest first)

2. **Get Session Detail**
   - ✅ Returns metadata + full message history
   - ✅ Messages have required fields (role, content, timestamp)
   - ✅ Different sessions have different message content
   - ✅ Messages are in chronological order (oldest first)
   - ✅ Non-existent session returns 404

3. **Touch Session (Metadata Upsert)**
   - ✅ PUT creates new session with generated title
   - ✅ Title is generated from first message content
   - ✅ Subsequent PUTs preserve the original title
   - ✅ updatedAt timestamp is refreshed on each touch

4. **Delete Session**
   - ✅ DELETE removes session metadata
   - ✅ Deleted session no longer appears in list

### Frontend UI

1. **Authentication**
   - ✅ Unauthenticated users see Sign In button
   - ✅ Login redirects to chat interface
   - ✅ Credentials are validated via Cognito

2. **Chat Interface**
   - ✅ Chat input field is visible
   - ✅ User can type and send messages
   - ✅ Sent messages appear in chat history
   - ✅ Assistant responses appear in chat

3. **Session Selection**
   - ✅ Recent chats display in sidebar
   - ✅ Clicking a session loads its history
   - ✅ Session history displays with correct messages
   - ⚠️ **Bug**: Selecting different chats loads the same history (needs fix)

## Known Issues

### Session Selection Bug

**Issue**: When selecting different recent chats from the sidebar, the same conversation history is displayed regardless of which chat is selected.

**Status**: Under investigation. Test `test_can_select_session_from_sidebar` documents this behavior.

**Root Cause**: Race condition in `ChatPage.handleSessionSelect()` - the component remounts before `initialMessages` is updated.

**Fix**: Already deployed - ensure `setInitialMessages()` is called before `setSessionId()` so the component remounts with correct data.

## Debugging Tests

### Enable Verbose Logging

```bash
pytest tests/integration -vv -s --log-cli-level=DEBUG
```

### Run with Screenshots/Videos (UI Tests)

```bash
pytest tests/integration/test_frontend_ui.py -vv
# Screenshots and videos saved in `test-results/`
```

### Inspect Failures

When a test fails, pytest creates:
- `report.html` - Full test report
- Screenshots in `test-results/` (UI tests)
- Videos in `test-results/` (UI test failures)

## Continuous Integration

To run these tests in CI/CD:

```bash
# Install dependencies
pip install -r test_requirements.txt

# Run tests (CI=true disables parallelization)
CI=true pytest tests/integration --html=report.html --self-contained-html

# Upload report
# (optional) upload report.html to artifact storage
```

## Performance

Expected runtime:
- **API tests only**: ~30-60 seconds
- **UI tests only**: ~2-5 minutes (includes login + browser operations)
- **All tests**: ~5-7 minutes

## Adding New Tests

### Add an API Test

```python
class TestNewFeature:
    """Tests for new API feature."""

    def test_new_feature_works(
        self, authenticated_session: requests.Session, api_base_url: str
    ):
        """Describe what this test validates."""
        response = authenticated_session.get(f"{api_base_url}new-endpoint")
        
        assert response.status_code == 200
        data = response.json()
        assert "expected_field" in data
```

### Add a UI Test

```python
class TestNewUI:
    """Tests for new UI feature."""

    def test_new_ui_element_visible(self, driver: webdriver.Chrome):
        """Describe what this test validates."""
        wait = WebDriverWait(driver, 10)
        
        element = wait.until(
            EC.presence_of_element_located((By.XPATH, "//new-element"))
        )
        
        assert element.is_displayed()
```

## Troubleshooting

### "Cognito login failed"

- Verify `TEST_EMAIL` and `TEST_PASSWORD` are correct
- Check that the Cognito user exists and is active
- Ensure the Cognito user pool is not rate-limited

### "Chrome not found"

- Install Chromium/Chrome browser
- Or set `CHROME_PATH` environment variable to the Chrome executable path

### "Session not found" (API tests)

- Ensure at least one chat session exists in the user's account
- Run a quick chat first to create a session
- Or create a test session via `PUT /sessions/{testId}`

### "Timeout waiting for element"

- Increase `WebDriverWait` timeout (default 10s)
- Check browser console for JavaScript errors
- Verify the application is responding at `BASE_URL`

## References

- [Pytest Documentation](https://docs.pytest.org/)
- [Selenium Documentation](https://selenium.dev/documentation/)
- [AWS Bedrock AgentCore API](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-api.html)
- [Cognito User Pools](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-pre-sign-up.html)
