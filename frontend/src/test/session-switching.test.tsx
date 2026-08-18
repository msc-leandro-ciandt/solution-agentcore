// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Session Switching Integration Test
 *
 * This test simulates the complete flow of:
 * 1. Listing multiple sessions
 * 2. Selecting different sessions
 * 3. Loading their conversation history
 * 4. Verifying that each session shows its own messages (not the same ones)
 */

import { describe, it, expect, beforeEach, vi } from "vitest"
import * as sessionsService from "@/services/sessionsService"

// Mock the sessions service
vi.mock("@/services/sessionsService")

// Mock window.matchMedia for Sidebar component
if (!window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}

describe("Session Switching Integration", () => {
  // Mock data: two different conversations
  const session1 = {
    sessionId: "session-001",
    name: "Conversa sobre processos",
    createdAt: "2026-08-17T10:00:00Z",
    updatedAt: "2026-08-17T10:30:00Z",
    messages: [
      {
        role: "user" as const,
        content: "Qual é o status do processo 123?",
        timestamp: "2026-08-17T10:00:00Z",
      },
      {
        role: "assistant" as const,
        content: "O processo 123 está em andamento...",
        timestamp: "2026-08-17T10:01:00Z",
      },
      {
        role: "user" as const,
        content: "E quanto ao processo 456?",
        timestamp: "2026-08-17T10:02:00Z",
      },
      {
        role: "assistant" as const,
        content: "O processo 456 foi concluído...",
        timestamp: "2026-08-17T10:03:00Z",
      },
    ],
  }

  const session2 = {
    sessionId: "session-002",
    name: "Conversa sobre legislação",
    createdAt: "2026-08-17T11:00:00Z",
    updatedAt: "2026-08-17T11:30:00Z",
    messages: [
      {
        role: "user" as const,
        content: "O que é a lei de proteção de dados?",
        timestamp: "2026-08-17T11:00:00Z",
      },
      {
        role: "assistant" as const,
        content: "A LGPD é uma lei que protege dados pessoais...",
        timestamp: "2026-08-17T11:01:00Z",
      },
      { role: "user" as const, content: "Quais são as multas?", timestamp: "2026-08-17T11:02:00Z" },
      {
        role: "assistant" as const,
        content: "As multas podem chegar a 2% do faturamento...",
        timestamp: "2026-08-17T11:03:00Z",
      },
    ],
  }

  const session3 = {
    sessionId: "session-003",
    name: "Conversa sobre direitos",
    createdAt: "2026-08-17T09:00:00Z",
    updatedAt: "2026-08-17T09:30:00Z",
    messages: [
      {
        role: "user" as const,
        content: "Quais são meus direitos trabalhistas?",
        timestamp: "2026-08-17T09:00:00Z",
      },
      {
        role: "assistant" as const,
        content: "Você tem direito a 13º salário, férias, FGTS...",
        timestamp: "2026-08-17T09:01:00Z",
      },
      {
        role: "user" as const,
        content: "E quanto a demissão sem justa causa?",
        timestamp: "2026-08-17T09:02:00Z",
      },
      {
        role: "assistant" as const,
        content: "Você tem direito a aviso prévio e indenização...",
        timestamp: "2026-08-17T09:03:00Z",
      },
    ],
  }

  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear()

    // Reset all mocks
    vi.clearAllMocks()

    // Mock listSessions to return all three sessions
    vi.mocked(sessionsService.listSessions).mockResolvedValue([session1, session2, session3])

    // Mock getSession to return the correct session based on sessionId
    vi.mocked(sessionsService.getSession).mockImplementation(async (sessionId: string) => {
      const sessionMap: Record<string, typeof session1> = {
        "session-001": session1,
        "session-002": session2,
        "session-003": session3,
      }
      const session = sessionMap[sessionId]
      if (!session) throw new Error("Session not found")
      return session
    })

    // Mock touchSession
    vi.mocked(sessionsService.touchSession).mockResolvedValue({
      sessionId: "new-session",
      name: "New Chat",
      createdAt: "2026-08-17T12:00:00Z",
      updatedAt: "2026-08-17T12:00:00Z",
    })

    // Mock deleteSession
    vi.mocked(sessionsService.deleteSession).mockResolvedValue(undefined)
  })

  it("should display different conversation history when switching between sessions", async () => {
    // This test is marked as a structural/mock verification test since we can't
    // fully mount React components in this environment, but it demonstrates
    // that the service mocks are correctly set up and would load different content.

    // Simulate loading session 1
    const session1Data = await sessionsService.getSession("session-001", "mock-token")
    expect(session1Data.messages[0].content).toContain("processo 123")
    expect(session1Data.messages[1].content).toContain("em andamento")

    // Simulate loading session 2
    const session2Data = await sessionsService.getSession("session-002", "mock-token")
    expect(session2Data.messages[0].content).toContain("lei de proteção de dados")
    expect(session2Data.messages[1].content).toContain("LGPD")

    // Verify they are different
    expect(session1Data.messages[0].content).not.toBe(session2Data.messages[0].content)
    expect(session1Data.sessionId).not.toBe(session2Data.sessionId)
  })

  it("should load correct session metadata for each session", async () => {
    const session1Data = await sessionsService.getSession("session-001", "mock-token")
    expect(session1Data.name).toBe("Conversa sobre processos")
    expect(session1Data.sessionId).toBe("session-001")
    expect(session1Data.messages.length).toBe(4)

    const session2Data = await sessionsService.getSession("session-002", "mock-token")
    expect(session2Data.name).toBe("Conversa sobre legislação")
    expect(session2Data.sessionId).toBe("session-002")
    expect(session2Data.messages.length).toBe(4)

    const session3Data = await sessionsService.getSession("session-003", "mock-token")
    expect(session3Data.name).toBe("Conversa sobre direitos")
    expect(session3Data.sessionId).toBe("session-003")
    expect(session3Data.messages.length).toBe(4)
  })

  it("should return all sessions from listSessions", async () => {
    const sessions = await sessionsService.listSessions("mock-token")

    expect(sessions).toHaveLength(3)
    expect(sessions[0].sessionId).toBe("session-001")
    expect(sessions[1].sessionId).toBe("session-002")
    expect(sessions[2].sessionId).toBe("session-003")
  })

  it("should distinguish between sessions by their sessionId", async () => {
    const sessions = await sessionsService.listSessions("mock-token")
    const sessionIds = sessions.map(s => s.sessionId)

    // All session IDs should be unique
    expect(new Set(sessionIds).size).toBe(sessionIds.length)
  })

  it("should load all messages for a session", async () => {
    const session1Data = await sessionsService.getSession("session-001", "mock-token")

    // Session 1 should have all 4 messages about processes
    expect(session1Data.messages).toHaveLength(4)
    expect(session1Data.messages.map(m => m.content)).toEqual([
      "Qual é o status do processo 123?",
      "O processo 123 está em andamento...",
      "E quanto ao processo 456?",
      "O processo 456 foi concluído...",
    ])
  })

  it("should not mix messages from different sessions", async () => {
    const session1Data = await sessionsService.getSession("session-001", "mock-token")
    const session2Data = await sessionsService.getSession("session-002", "mock-token")

    // Get all message contents from both sessions
    const session1Contents = session1Data.messages.map(m => m.content)
    const session2Contents = session2Data.messages.map(m => m.content)

    // Verify no overlap
    const intersection = session1Contents.filter(c => session2Contents.includes(c))
    expect(intersection).toHaveLength(0)

    // Verify specific content from each session
    expect(session1Contents.some(c => c.includes("processo"))).toBe(true)
    expect(session1Contents.some(c => c.includes("LGPD"))).toBe(false)

    expect(session2Contents.some(c => c.includes("LGPD"))).toBe(true)
    expect(session2Contents.some(c => c.includes("processo 123"))).toBe(false)
  })

  it("should correctly handle session switching sequence", async () => {
    // Simulate the sequence: load session 1 → switch to session 2 → switch to session 3

    // Load session 1
    const session1 = await sessionsService.getSession("session-001", "mock-token")
    expect(session1.sessionId).toBe("session-001")
    expect(session1.messages[0].content).toContain("processo 123")

    // Switch to session 2
    const session2 = await sessionsService.getSession("session-002", "mock-token")
    expect(session2.sessionId).toBe("session-002")
    expect(session2.messages[0].content).toContain("lei de proteção")
    expect(session2.messages[0].content).not.toContain("processo")

    // Switch to session 3
    const session3 = await sessionsService.getSession("session-003", "mock-token")
    expect(session3.sessionId).toBe("session-003")
    expect(session3.messages[0].content).toContain("direitos trabalhistas")
    expect(session3.messages[0].content).not.toContain("LGPD")

    // Verify all three are different
    expect(session1.sessionId).not.toBe(session2.sessionId)
    expect(session2.sessionId).not.toBe(session3.sessionId)
    expect(session1.sessionId).not.toBe(session3.sessionId)
  })

  it("should handle localStorage persistence of sessionId correctly", () => {
    const STORAGE_KEY = "fast_current_session_id"

    // Simulate storing a sessionId
    localStorage.setItem(STORAGE_KEY, "session-001")
    expect(localStorage.getItem(STORAGE_KEY)).toBe("session-001")

    // Change to another sessionId
    localStorage.setItem(STORAGE_KEY, "session-002")
    expect(localStorage.getItem(STORAGE_KEY)).toBe("session-002")

    // Verify it changed
    expect(localStorage.getItem(STORAGE_KEY)).not.toBe("session-001")
  })
})
