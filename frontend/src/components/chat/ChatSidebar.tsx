"use client"

import { MessageSquare, Plus, Trash2 } from "lucide-react"
import { SessionSummary } from "@/services/sessionsService"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"

type ChatSidebarProps = {
  sessions: SessionSummary[]
  currentSessionId?: string
  onSessionSelect: (session: SessionSummary) => void
  onNewChat: () => void
  onSessionDelete: (session: SessionSummary) => void
}

export function ChatSidebar({
  sessions,
  currentSessionId,
  onSessionSelect,
  onNewChat,
  onSessionDelete,
}: ChatSidebarProps) {
  return (
    <Sidebar>
      <SidebarHeader className="p-4 space-y-2">
        <Button onClick={onNewChat} className="w-full justify-start gap-2">
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Recent Chats</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {sessions.map(session => (
                <SidebarMenuItem
                  key={session.sessionId}
                  className="group/session-item flex items-center"
                >
                  <SidebarMenuButton
                    onClick={() => onSessionSelect(session)}
                    isActive={currentSessionId === session.sessionId}
                    className="w-full justify-start gap-2"
                  >
                    <MessageSquare className="h-4 w-4" />
                    <span className="truncate">{session.name}</span>
                  </SidebarMenuButton>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 shrink-0 opacity-0 group-hover/session-item:opacity-100"
                    aria-label={`Delete chat "${session.name}"`}
                    onClick={event => {
                      event.stopPropagation()
                      onSessionDelete(session)
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  )
}
