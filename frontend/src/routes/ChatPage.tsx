"use client"
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState } from "react"
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

  const [sessionId, setSessionId] = useState<string>(() => loadPersistedSessionId())
  const [initialMessages, setInitialMessages] = useState<Message[]>([])
  const [isHydrating, setIsHydrating] = useState(false)

  const { sessions, refresh: refreshSessions, remove: removeSession } = useChatSessions(idToken)

  // On mount, if the persisted session ID corresponds to a real past
  // conversation, hydrate the chat window with its history instead of
  // starting from an empty screen.
  useEffect(() => {
    if (!idToken) return
    // Captured as a local const so TS's narrowing of `idToken` (from the
    // guard above) carries into the nested hydrate() closure below.
    const token = idToken
    let cancelled = false

    async function hydrate() {
      setIsHydrating(true)
      try {
        const detail = await getSession(sessionId, token)
        if (!cancelled) {
          setInitialMessages(
            detail.messages.map(m => ({
              role: m.role,
              content: m.content,
              timestamp: m.timestamp,
            }))
          )
        }
      } catch {
        // No stored session yet for this ID (e.g. brand new UUID, or the
        // session was deleted) — that's expected, just start with an empty chat.
      } finally {
        if (!cancelled) setIsHydrating(false)
      }
    }

    void hydrate()
    return () => {
      cancelled = true
    }
    // Only re-hydrate when the token first becomes available, not on every
    // sessionId change — session switches are handled explicitly by handleSessionSelect.
  }, [idToken])

  const handleNewChat = useCallback(() => {
    const newId = crypto.randomUUID()
    persistSessionId(newId)
    setSessionId(newId)
    setInitialMessages([])
  }, [])

  const handleSessionSelect = useCallback(
    async (session: SessionSummary) => {
      if (!idToken) return
      persistSessionId(session.sessionId)
      setSessionId(session.sessionId)
      setIsHydrating(true)
      try {
        const detail = await getSession(session.sessionId, idToken)
        setInitialMessages(
          detail.messages.map(m => ({
            role: m.role,
            content: m.content,
            timestamp: m.timestamp,
          }))
        )
      } catch (err) {
        console.error("Failed to load session history:", err)
        setInitialMessages([])
      } finally {
        setIsHydrating(false)
      }
    },
    [idToken]
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
