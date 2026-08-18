# Debug Session Switching Bug

## Symptoms
- Initial load: Shows correct messages
- Select different session: Still shows SAME messages instead of new ones
- Change conversation: Sometimes updates, but switching back/forth stays same

## Debug Steps

### Step 1: Check if API is returning different data

Open your browser's Developer Tools (F12) and go to **Network** tab.

1. Click different sessions in the sidebar
2. Look for requests to `/sessions/` endpoint
3. Compare the responses - they should have DIFFERENT messages for different sessionIds

**Expected**: Each sessionId returns different `messages` array
**If failing**: API is returning same data OR endpoint isn't being called

```
// Session A response should be different from Session B:
Session A:  {"sessionId": "uuid-a", "messages": [{"role": "user", "content": "Session A message"}]}
Session B:  {"sessionId": "uuid-b", "messages": [{"role": "user", "content": "Session B message"}]}
```

### Step 2: Check React state in browser console

Open Developer Tools **Console** tab and paste this code:

```javascript
// Monitor React state changes - add this to console
const originalFetch = window.fetch;
let callCount = 0;

window.fetch = function(...args) {
  const url = args[0];
  if (url.includes('/sessions/')) {
    callCount++;
    console.log(`\n🔄 FETCH #${callCount}: ${url}`);
    
    return originalFetch.apply(this, args).then(response => {
      response.clone().json().then(data => {
        console.log('   Response data:', data);
      });
      return response;
    });
  }
  return originalFetch.apply(this, args);
};

console.log('✅ Fetch monitor installed. Now click sessions and watch console.');
```

Now click different sessions and watch the console output:
- ✅ **GOOD**: Different sessionIds in URLs and different messages in responses
- ❌ **BAD**: Same sessionId repeated or same messages in responses

### Step 3: Check localStorage

In the Console tab, paste:

```javascript
// Check what sessionId is stored
const stored = localStorage.getItem('fast_current_session_id');
console.log('Stored sessionId:', stored);

// Clear it and reload if you want to test with fresh session
// localStorage.removeItem('fast_current_session_id');
```

**Expected**: sessionId should CHANGE when you click different sessions

### Step 4: Check if initialMessages prop is updating

In the Console tab, paste:

```javascript
// React component state monitoring
window.__debugMessages = [];

// Hook into React's state updates
const observer = setInterval(() => {
  const msgElements = document.querySelectorAll('[class*="message"]');
  const currentMessages = Array.from(msgElements)
    .map(el => el.textContent?.substring(0, 50))
    .filter(text => text && text.length > 5);
  
  const key = currentMessages.join('|');
  
  if (window.__lastKey !== key) {
    console.log('📝 Messages changed:', currentMessages.slice(0, 3));
    window.__lastKey = key;
  }
}, 1000);

console.log('✅ Message monitor started. Click sessions to see updates.');
```

**Expected**: Console should print "Messages changed" when you click different sessions
**If not happening**: Component not re-rendering or messages not in DOM

### Step 5: Check browser errors

Look at the Console tab for any JavaScript errors (red messages). Take a screenshot if you see any.

Common errors:
- `Cannot read property 'messages' of undefined`
- `sessionId is not defined`
- `initialMessages is null`

### Step 6: Manual inspection

1. Open Developer Tools → **Elements** tab
2. Click on a session in the sidebar
3. Find the message container (usually a `<div>` with class containing "message" or "chat")
4. Expand it and look for the message text
5. Now click a DIFFERENT session
6. **Do the messages in the DOM change?**
   - ✅ YES = Problem is elsewhere (maybe display logic)
   - ❌ NO = Component not re-rendering with new data

## What Each Result Means

| Check | Result | Meaning |
|-------|--------|---------|
| API returns different data | ✅ YES | Backend is working |
| API returns different data | ❌ NO | Backend bug or wrong sessionId sent |
| React state changes | ✅ YES | Parent component updating |
| React state changes | ❌ NO | handleSessionSelect not firing |
| initialMessages prop updates | ✅ YES | Props syncing correctly |
| initialMessages prop updates | ❌ NO | useState in ChatInterface not updating |
| DOM messages change | ✅ YES | Component re-rendering |
| DOM messages change | ❌ NO | Component still mounted with old key |

## Common Issues & Fixes

### Issue 1: API returns same data for all sessions
**Cause**: sessionId not being sent correctly, or backend caching
**Fix**: Check Network tab - URL should be `/sessions/{different-id}`

### Issue 2: React state updates but DOM doesn't change
**Cause**: Component not re-rendering, or key={sessionId} not working
**Fix**: Check that sessionId actually changes (localStorage check), and component has `key={sessionId}`

### Issue 3: Everything looks correct but still same messages
**Cause**: ChatInterface component is reading from wrong state source
**Fix**: Check if initialMessages prop matches what API returned

## Quick Copy-Paste Debug Bundle

Run all checks at once:

```javascript
console.log('=== SESSION SWITCHING DEBUG ===');
console.log('1. Stored sessionId:', localStorage.getItem('fast_current_session_id'));

// Monitor next fetch
const original = window.fetch;
window.fetch = function(...args) {
  if (args[0].includes('/sessions/')) {
    console.log('2. Fetching:', args[0]);
  }
  return original.apply(this, args).then(r => {
    if (args[0].includes('/sessions/')) {
      r.clone().json().then(d => {
        console.log('3. Got messages:', d.messages?.length, 'messages');
        console.log('   First message:', d.messages?.[0]?.content?.substring(0, 50));
      });
    }
    return r;
  });
};

// Monitor DOM
setInterval(() => {
  const text = Array.from(document.querySelectorAll('[class*="message"]'))
    .map(e => e.textContent?.substring(0, 40))
    .filter(t => t?.length > 5)
    .join(' | ');
  
  if (window.__lastText !== text) {
    console.log('4. DOM messages:', text.substring(0, 80));
    window.__lastText = text;
  }
}, 2000);

console.log('✅ Debug started. Click sessions and watch output.');
```

## After Debugging

Please report:
1. What does the API return? (Different data or same?)
2. Does React state update? (localStorage and prop changes?)
3. Does DOM update? (Messages in HTML change?)
4. Any console errors?

With this info, I can pinpoint exactly where the bug is!
