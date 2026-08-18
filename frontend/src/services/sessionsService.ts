/**
 * Sessions Service
 * Lists, reads, "touches" (upserts metadata for), and deletes chat sessions.
 *
 * Backed by the same REST API as feedbackService.ts (see aws-exports.json's
 * feedbackApiUrl) — the /sessions routes live on the shared "FeedbackApi"
 * REST API created in infra-cdk/lib/backend-construct.ts, not a separate one.
 */

export interface SessionSummary {
  sessionId: string
  name: string
  createdAt: string
  updatedAt: string
}

export interface SessionMessage {
  role: "user" | "assistant"
  content: string
  timestamp: string
}

export interface SessionDetail extends SessionSummary {
  messages: SessionMessage[]
}

// Load API base URL from aws-exports.json (same base as feedbackService.ts)
let SESSIONS_API_BASE_URL = ""

async function loadApiBaseUrl(): Promise<string> {
  if (SESSIONS_API_BASE_URL) {
    return SESSIONS_API_BASE_URL
  }

  try {
    const response = await fetch("/aws-exports.json")
    const config = await response.json()
    if (!config.feedbackApiUrl) {
      throw new Error("Sessions API URL not configured")
    }
    // feedbackApiUrl already ends with a trailing slash (API Gateway stage URL)
    SESSIONS_API_BASE_URL = config.feedbackApiUrl
    return SESSIONS_API_BASE_URL
  } catch (error) {
    console.error("Failed to load API URL from aws-exports.json:", error)
    throw new Error("Sessions API URL not configured")
  }
}

function authHeaders(idToken: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${idToken}`,
  }
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`)
  }
  return response.json() as Promise<T>
}

/**
 * List the authenticated user's chat sessions, sorted by most recently updated.
 *
 * @param idToken - Cognito ID token for authentication.
 * @returns Promise resolving to the list of session summaries.
 */
export async function listSessions(idToken: string): Promise<SessionSummary[]> {
  const baseUrl = await loadApiBaseUrl()
  console.log(`[SessionService] Listing sessions for user...`)
  const response = await fetch(`${baseUrl}sessions`, {
    method: "GET",
    headers: authHeaders(idToken),
  })
  const result = await parseJsonOrThrow<SessionSummary[]>(response)
  console.log(`[SessionService] Got ${result.length} sessions`)
  result.forEach(s => console.log(`[SessionService]   - ${s.name} (${s.sessionId})`))
  return result
}

/**
 * Fetch a single session's metadata and full conversation history.
 *
 * @param sessionId - The session ID to fetch.
 * @param idToken - Cognito ID token for authentication.
 * @returns Promise resolving to the session's metadata and messages.
 */
export async function getSession(sessionId: string, idToken: string): Promise<SessionDetail> {
  const baseUrl = await loadApiBaseUrl()
  const url = `${baseUrl}sessions/${encodeURIComponent(sessionId)}`
  console.log(`[SessionService] Fetching session: ${sessionId}`)

  const response = await fetch(url, {
    method: "GET",
    headers: authHeaders(idToken),
  })
  const result = await parseJsonOrThrow<SessionDetail>(response)

  console.log(
    `[SessionService] Got ${result.messages?.length || 0} messages for session ${sessionId}`
  )
  if (result.messages && result.messages.length > 0) {
    console.log(
      `[SessionService] First message: "${result.messages[0].content?.substring(0, 50)}..."`
    )
  }

  return result
}

/**
 * Upsert session metadata ("touch"). On a session's first touch, the backend
 * generates a title from the provided messages; on later touches, only the
 * updatedAt timestamp is refreshed (the title is preserved).
 *
 * @param sessionId - The session ID to touch.
 * @param firstUserMessage - The conversation's first user message (used for
 *   title generation on first touch, and as the fallback title).
 * @param firstAssistantMessage - The conversation's first assistant response,
 *   optionally included to improve title generation.
 * @param idToken - Cognito ID token for authentication.
 * @returns Promise resolving to the upserted session summary.
 */
export async function touchSession(
  sessionId: string,
  firstUserMessage: string,
  firstAssistantMessage: string | undefined,
  idToken: string
): Promise<SessionSummary> {
  const baseUrl = await loadApiBaseUrl()
  const response = await fetch(`${baseUrl}sessions/${encodeURIComponent(sessionId)}`, {
    method: "PUT",
    headers: authHeaders(idToken),
    body: JSON.stringify({
      firstUserMessage,
      firstAssistantMessage,
    }),
  })
  return parseJsonOrThrow<SessionSummary>(response)
}

/**
 * Delete a chat session (metadata row, plus best-effort AgentCore Memory cleanup).
 *
 * @param sessionId - The session ID to delete.
 * @param idToken - Cognito ID token for authentication.
 * @returns Promise resolving once the deletion request completes.
 */
export async function deleteSession(sessionId: string, idToken: string): Promise<void> {
  const baseUrl = await loadApiBaseUrl()
  const response = await fetch(`${baseUrl}sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: authHeaders(idToken),
  })
  await parseJsonOrThrow<{ success: boolean }>(response)
}
