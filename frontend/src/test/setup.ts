// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Test setup file for vitest
 * Configures testing environment and imports necessary testing utilities
 */

import "@testing-library/jest-dom"

// jsdom does not implement window.matchMedia. The shadcn Sidebar component
// (used by ChatPage's ChatSidebar, added for the chat history feature) calls
// it via useIsMobile() on every render, so it must be mocked globally rather
// than per-test.
if (typeof window !== "undefined" && !window.matchMedia) {
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
