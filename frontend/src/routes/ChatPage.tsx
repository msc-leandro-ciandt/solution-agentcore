"use client"
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState, useRef } from "react"
import ChatInterface from "@/components/chat/ChatInterface"
import { ChatSidebar } from "@/components/chat/ChatSidebar"
import { Message } from "@/components/chat/types"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/hooks/useAuth"
import { GlobalContextProvider } from "@/app/context/GlobalContext"
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar"
import { useChatSessions } from "@/hooks/useChatSessions"
import { getSession, SessionSummary } from "@/services/sessionsService"

// Persists the active session ID across page reloads. Without this, a
// refresh would generate a brand new UUID and the (still-existing) previous
// conversation would appear to have vanished from the chat window — even
// though it's still stored in AgentCore Memory and listed in the sidebar.
const CURRENT_SESSION_STORAGE_KEY = "fast_current_session_id"

function loadPersistedSessionId(): string {
  try {
    return localStorage.getItem(CURRENT_SESSION_STORAGE_KEY) || crypto.randomUUID()
  } catch {
    // localStorage can throw in some restricted environments (e.g. private
    // browsing in some browsers) — fall back to an ephemeral session.
    return crypto.randomUUID()
  }
}

function persistSessionId(sessionId: string): void {
  try {
    localStorage.setItem(CURRENT_SESSION_STORAGE_KEY, sessionId)
  } catch {
    // Non-fatal — the session simply won't survive a reload this time.
  }
}

export default function ChatPage() {
  const { isAuthenticated, signIn, token: rawIdToken } = useAuth()
  // useAuth's mock (no-AuthProvider) branch returns `token: null`; normalize
  // to `undefined` so downstream hooks/functions only deal with one "absent" value.
  const idToken = rawIdToken ?? undefined

  const [sessionId, setSessionId] = useState<string>(() => {
    const persisted = loadPersistedSessionId()
    console.log(`[ChatPage] MOUNT: loadPersistedSessionId returned: ${persisted}`)
    return persisted
  })
  const [initialMessages, setInitialMessages] = useState<Message[]>([])
  const [isHydrating, setIsHydrating] = useState(false)

  // Track the previous sessionId to detect when it changes
  const prevSessionIdRef = useRef(sessionId)

  const { sessions, refresh: refreshSessions, remove: removeSession } = useChatSessions(idToken)

  // On mount, if the persisted session ID corresponds to a real past
  // conversation, hydrate the chat window with its history instead of
  // starting from an empty screen.
  //
  // NOTE: Sessions are created lazily via touchSession() (PUT /sessions/{id})
  // after the first message exchange. On initial mount, we don't know if
  // this session exists yet, so we don't try to load it. The sidebar will
  // handle listing existing sessions via listSessions().
  useEffect(() => {
    // Session loading is only needed when explicitly selecting from sidebar
    // (handleSessionSelect), not on initial mount. The first chat starts empty.
  }, [idToken])

  // When sessionId changes, update the ref. This helps track session transitions
  // and ensure initialMessages stays in sync with the active session.
  useEffect(() => {
    prevSessionIdRef.current = sessionId
  }, [sessionId])

  const handleNewChat = useCallback(() => {
    const newId = crypto.randomUUID()
    persistSessionId(newId)
    setSessionId(newId)
    setInitialMessages([])
  }, [])

  const handleSessionSelect = useCallback(
    async (session: SessionSummary) => {
      console.log(`[ChatPage] ========== SELECTING SESSION ==========`)
      console.log(`[ChatPage] Requested sessionId: ${session.sessionId}`)
      console.log(`[ChatPage] Session name: "${session.name}"`)
      console.log(`[ChatPage] Current state sessionId BEFORE: ${sessionId}`)

      if (!idToken) {
        console.error("[ChatPage] No idToken available")
        return
      }

      console.log(`[ChatPage] idToken available: ${idToken.substring(0, 20)}...`)

      // Keep isHydrating true to hide old ChatInterface during the transition
      setIsHydrating(true)
      try {
        console.log(`[ChatPage] Fetching session details for: ${session.sessionId}`)
        const detail = await getSession(session.sessionId, idToken)
        console.log(`[ChatPage] Got ${detail.messages.length} messages`)
        console.log(`[ChatPage] First message sample:`, detail.messages[0])

        const loadedMessages = detail.messages.map(m => ({
          role: m.role,
          content: m.content,
          timestamp: m.timestamp,
        }))

        console.log(`[ChatPage] Setting initialMessages with ${loadedMessages.length} items`)
        console.log(
          `[ChatPage] initialMessages content:`, loadedMessages.map(m => m.content.substring(0, 50))
        )
        console.log(
          `[ChatPage] localStorage BEFORE: ${localStorage.getItem(CURRENT_SESSION_STORAGE_KEY)}`
        )

        // Set messages FIRST, then sessionId. Because isHydrating is still true,
        // ChatInterface won't render yet. By the time it does (when isHydrating
        // becomes false), both initialMessages and sessionId will be in sync.
        setInitialMessages(loadedMessages)
        persistSessionId(session.sessionId)
        console.log(
          `[ChatPage] localStorage AFTER: ${localStorage.getItem(CURRENT_SESSION_STORAGE_KEY)}`
        )
        setSessionId(session.sessionId)
        console.log(`[ChatPage] State sessionId set to: ${session.sessionId}`)
        console.log(`[ChatPage] ========== SESSION SELECTED ==========`)

        // Now it's safe to show the new ChatInterface with fresh messages
        setIsHydrating(false)
      } catch (err) {
        console.error("[ChatPage] Failed to load session history:", err)
        console.error("[ChatPage] Error details:", {
          sessionId: session.sessionId,
          error: String(err),
          message: err instanceof Error ? err.message : "Unknown",
        })
        setInitialMessages([])
        setIsHydrating(false)
      }
    },
    [idToken, sessionId]
  )

  const handleSessionDelete = useCallback(
    async (session: SessionSummary) => {
      try {
        await removeSession(session.sessionId)
        if (session.sessionId === sessionId) {
          handleNewChat()
        }
      } catch (err) {
        console.error("Failed to delete session:", err)
      }
    },
    [removeSession, sessionId, handleNewChat]
  )

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-4xl">Please sign in</p>
        <Button onClick={() => signIn()}>Sign In</Button>
      </div>
    )
  }

  return (
    <GlobalContextProvider>
      <SidebarProvider>
        <ChatSidebar
          sessions={sessions}
          currentSessionId={sessionId}
          onSessionSelect={handleSessionSelect}
          onNewChat={handleNewChat}
          onSessionDelete={handleSessionDelete}
        />
        <SidebarInset>
          <div className="relative h-screen">
            <div className="absolute top-4 left-4 z-10">
              <SidebarTrigger />
            </div>
            {!isHydrating && (
              // Keying by sessionId forces ChatInterface to fully remount on
              // session switch, so its internal message/input state always
              // starts fresh for the newly selected (or newly created) session.
              <ChatInterface
                key={sessionId}
                sessionId={sessionId}
                initialMessages={initialMessages}
                idToken={idToken}
                onRequestNewChat={handleNewChat}
                onSessionTouched={refreshSessions}
              />
            )}
          </div>
        </SidebarInset>
      </SidebarProvider>
    </GlobalContextProvider>
  )
}
