# Final Debug: Session 404 Issue

The 404 error is happening because sessions listed in the sidebar are NOT in DynamoDB when you try to load them.

## Test Steps (CRITICAL)

### 1. Open App Fresh

1. Go to: https://main.d3de0r2ujefnqj.amplifyapp.com
2. Login: leanpsilva@gmail.com / Tifani%04  
3. Open F12 Console
4. **CLEAR console** (cmd+K or Ctrl+L)

### 2. Send First Message

1. In chat input, type: **"Hello test"**
2. Send it (Enter)
3. **WAIT for response** to complete
4. **IMMEDIATELY look at console**

**LOOK FOR THESE LOGS:**
```
[ChatInterface] Touching session ABC-DEF-123 to create metadata...
[ChatInterface] Session touched successfully
```

If you see `Failed to touch session`, **STOP** and report the error.

### 3. Check Sidebar Now

1. Look at sidebar "Recent Chats"
2. **Should show ONE session** with auto-generated name

**If sidebar is empty** → session not created in DynamoDB → touchSession failed

### 4. Refresh Page

1. Press F5 to refresh
2. Look at sidebar
3. **Session should still be there** (proves it was saved)

### 5. List Sessions (Check Console)

Clear console again, then look for:
```
[SessionService] Got 1 sessions
[SessionService]   - <name> (ABC-DEF-123)
```

These are the sessions in DynamoDB.

### 6. Click That Session

1. Click the session in sidebar
2. **IMMEDIATELY look at console for:**
```
[ChatPage] Selecting session: ABC-DEF-123
[ChatPage] idToken available: eyJhbG...
[ChatPage] Fetching session details for: ABC-DEF-123
```

**Then one of:**
- ✅ `[ChatPage] Got X messages` → SUCCESS
- ❌ `[ChatPage] Failed to load session history:` → ERROR

### 7. Report Back

**COPY AND PASTE all these console logs:**

1. **Sending first message logs** (touchSession)
2. **Sidebar after refresh** (listSessions)
3. **Clicking session logs** (selectSession + error if any)

---

## What Each Result Means

| Observation | Meaning |
|---|---|
| `touchSession successful` but `listSessions empty` | Session created but not queryable by userId |
| `listSessions shows session` but `clicking returns 404` | userId mismatch between list and get |
| `idToken empty or undefined` | idToken not passing correctly |
| `Got X messages` | ✅ Everything working! |

---

## Possible Issues & Fixes

### Issue 1: `touchSession` never completes
**Cause**: idToken is undefined
**Check**: Is `[ChatInterface] Touching session` log appearing?
**Fix**: Need to verify idToken prop passing in ChatPage → ChatInterface

### Issue 2: `listSessions shows session` but `404 on click`
**Cause**: userId mismatch (different user claiming ownership)
**Check**: Are sessionIds the same in both list and get calls?
**Fix**: Backend Cognito authorization issue - need to check JWT claims

### Issue 3: Console shows nothing
**Cause**: Code not deployed yet or old version cached
**Fix**: Hard refresh (Cmd+Shift+R or Ctrl+Shift+R) and try again

---

## Console Filtering Tip

To see ONLY session-related logs, paste this in console:

```javascript
// Filter to show only [SessionService] and [ChatPage] logs
const oldLog = console.log;
console.log = function(...args) {
  const msg = String(args[0]);
  if (msg.includes('[SessionService]') || msg.includes('[ChatPage]')) {
    oldLog.apply(console, args);
  }
};
console.log('✅ Filtering ON - now only showing session logs');
```

---

## Expected Behavior After Fix

1. Send message → `[ChatInterface] Session touched successfully` ✅
2. Session appears in sidebar
3. Refresh → session still there
4. Click session → shows messages ✅
5. Switch between sessions → each shows different messages ✅

---

## Report Template

When you send me the logs, format like:

```
STEP 1: Sending first message
[logs here]

STEP 2: Sidebar after refresh
[logs here]

STEP 3: Clicking session
[logs here]

QUESTIONS:
- Did touchSession complete successfully? YES/NO
- Did session appear in sidebar? YES/NO  
- What error did you see when clicking? [error text]
```

This helps me pinpoint EXACTLY where it's failing!
