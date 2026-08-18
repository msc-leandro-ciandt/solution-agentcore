"use client"

import { useCallback, useEffect, useState } from "react"
import { deleteSession, listSessions, SessionSummary } from "@/services/sessionsService"

/**
 * Manages the authenticated user's list of chat sessions for the sidebar:
 * fetches the list on mount/token change, and exposes refresh/remove helpers.
 *
 * @param idToken - Cognito ID token. Sessions are only fetched once this is
 *   available (the hook no-ops while the user is still authenticating).
 * @returns The current sessions list, a loading flag, and refresh/remove functions.
 */
export function useChatSessions(idToken: string | undefined) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!idToken) return
    setIsLoading(true)
    try {
      const list = await listSessions(idToken)
      setSessions(list)
    } catch (err) {
      console.error("Failed to load chat sessions:", err)
    } finally {
      setIsLoading(false)
    }
  }, [idToken])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const remove = useCallback(
    async (sessionId: string) => {
      if (!idToken) return
      await deleteSession(sessionId, idToken)
      setSessions(prev => prev.filter(s => s.sessionId !== sessionId))
    },
    [idToken]
  )

  return { sessions, isLoading, refresh, remove }
}
