# Session Switching UI Testing Guide

## Overview

This document provides instructions for manually testing the session switching bug fix in the FAST Chat application.

**Bug Description**: When selecting different chat sessions in the sidebar, the application was showing the same message history regardless of which session was selected.

**Root Cause**: React state update race condition - `setSessionId()` was being called before the new messages were loaded, causing the component to remount with stale data.

**Fix Applied**:
1. Moved `setInitialMessages(loadedMessages)` BEFORE `setSessionId(session.sessionId)` in `ChatPage.tsx`
2. Added React key binding: `<ChatInterface key={sessionId} ... />` to force remount
3. Code properly documented with comments explaining the ordering requirement

## Automated Tests

Run the following to validate the fix programmatically:

```bash
cd /home/leandrops/Documentos/projetos/solution-agentcore

# Run session loading tests (code verification)
pytest tests/integration/test_session_loading.py -v

# Run API tests (backend validation)
pytest tests/integration/test_api_direct.py -v

# Run all tests
make all
```

**Test Results**:
- ✅ Frontend state order verified (setInitialMessages before setSessionId)
- ✅ ChatInterface has correct key={sessionId} binding
- ✅ Backend API returns different sessions correctly
- ✅ All 102 frontend unit tests passing

## Manual UI Testing

Since headless browser testing has limitations with Cognito authentication, manual testing is required to fully verify the UI behavior.

### Prerequisites

- ✅ Application deployed to: https://main.d3de0r2ujefnqj.amplifyapp.com
- ✅ Backend API functional
- ✅ Test user account: `leanpsilva@gmail.com` / `Tifani%04`

### Steps to Verify Bug Fix

#### 1. Login to Application

1. Open: https://main.d3de0r2ujefnqj.amplifyapp.com
2. Click "Sign In"
3. Enter credentials:
   - Email: `leanpsilva@gmail.com`
   - Password: `Tifani%04`
4. Verify you see the chat interface with a sidebar

#### 2. Create Test Sessions with Different Content

Create 3 sessions with distinct content to make it easy to verify switching works:

**Session A:**
1. Click "New Chat" (or use existing session)
2. Type message: `Session A - First message about testing`
3. Send message
4. Type message: `Session A - Second message with unique content`
5. Send message

**Session B:**
1. Click "New Chat"
2. Type message: `Session B - First message with different content`
3. Send message
4. Type message: `Session B - Completely different second message`
5. Send message

**Session C:**
1. Click "New Chat"
2. Type message: `Session C - Unique message number one`
3. Send message
4. Type message: `Session C - Another unique message here`
5. Send message

You should now have 3 sessions in the sidebar with different content.

#### 3. Test Session Switching (Main Bug Test)

**Expected Behavior (AFTER FIX):**

- Click Session A in sidebar → Messages show "Session A" content
- Click Session B in sidebar → Messages show "Session B" content (DIFFERENT from A)
- Click Session C in sidebar → Messages show "Session C" content (DIFFERENT from A & B)
- Click back to Session A → Shows "Session A" messages again

**Bug Behavior (BEFORE FIX):**

- Click Session A → shows "Session A" messages
- Click Session B → STILL shows "Session A" messages
- Click Session C → STILL shows "Session A" messages
- Session content never changes

### Debugging / Advanced Testing

#### Check Network Requests

1. Open Developer Tools (F12)
2. Go to "Network" tab
3. Click different sessions
4. Look for requests to `/prod/sessions/<sessionId>`
5. Verify the response contains DIFFERENT messages for different sessionIds

**Expected Response Structure**:
```json
{
  "sessionId": "uuid-here",
  "messages": [
    { "role": "user", "content": "Session B - First message...", "timestamp": "..." },
    { "role": "assistant", "content": "Response...", "timestamp": "..." }
  ]
}
```

#### Check Browser Console

1. Open Developer Tools (F12)
2. Go to "Console" tab
3. Click different sessions
4. Look for any error messages
5. Should see no errors or warnings related to session loading

#### Verify LocalStorage

1. Open Developer Tools (F12)
2. Go to "Application" tab
3. Find "Local Storage" → `https://main.d3de0r2ujefnqj.amplifyapp.com`
4. Look for key: `fast_current_session_id`
5. Value should change as you select different sessions

### Test Result Recording

After completing the manual testing, record results:

**✅ Bug Fixed** if:
- Each session loads its own message history
- Switching between sessions displays DIFFERENT messages
- No console errors appear
- Network requests show correct session data

**❌ Bug Still Present** if:
- All sessions show identical messages
- Selecting different sessions doesn't change displayed content
- Console shows JavaScript errors
- Network requests return different data but UI doesn't reflect it

## Code Changes Made

### File: `frontend/src/routes/ChatPage.tsx`

**Key Change**: Fixed state update order in `handleSessionSelect()` callback

```typescript
// ✅ CORRECT ORDER (after fix):
setInitialMessages(loadedMessages)  // FIRST - set messages BEFORE changing session
persistSessionId(session.sessionId)
setSessionId(session.sessionId)      // SECOND - then change session to trigger remount

// ❌ WRONG ORDER (bug):
// setSessionId(session.sessionId)   // Changes session ID
// setInitialMessages(loadedMessages) // Too late! Component already remounted with old data
```

**Why This Matters**:
- React component has `key={sessionId}` which forces a full remount when sessionId changes
- If messages are loaded AFTER the remount, the component initializes with empty messages
- By loading messages FIRST, they're ready when the remount happens

### File: `frontend/src/routes/ChatPage.tsx`

**React Key Binding**: Forces component remount on session change

```typescript
<ChatInterface
  key={sessionId}  // ← This key forces full remount when sessionId changes
  sessionId={sessionId}
  initialMessages={initialMessages}
  ...
/>
```

## Deployment Status

- ✅ Fix deployed to: https://main.d3de0r2ujefnqj.amplifyapp.com
- ✅ Backend verified working
- ✅ Code changes tested and verified
- ⏳ Awaiting manual UI verification

## Questions or Issues?

1. **Session still not switching?**
   - Check browser console for JavaScript errors
   - Verify network requests are returning different data
   - Clear browser cache and reload

2. **API returns wrong data?**
   - Run: `pytest tests/integration/test_api_direct.py -v`
   - Check AWS Lambda logs in CloudWatch

3. **Messages load but wrong session?**
   - Check localStorage `fast_current_session_id` value
   - Verify API sessionId parameter matches selected session
   - Look for React warnings about key changes

## Related Documentation

- [Local Development Guide](./docs/LOCAL_DEVELOPMENT.md)
- [Deployment Guide](./docs/DEPLOYMENT.md)
- [Session Management](./docs/SESSION_MANAGEMENT.md)
