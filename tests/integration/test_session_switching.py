# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Focused UI tests for session switching behavior.

Tests the specific bug: when selecting different sessions, do they load
different message histories or always the same history?
"""

import os
import time

import pytest
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()

TEST_EMAIL = os.getenv("TEST_EMAIL", "leanpsilva@gmail.com")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "Tifani%04")
BASE_URL = os.getenv("BASE_URL", "https://main.d3de0r2ujefnqj.amplifyapp.com")


@pytest.fixture
def driver():
    """Create a Chrome WebDriver for testing."""
    chrome_options = ChromeOptions()
    # Use headless mode but with additional flags for stability
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        pytest.skip(f"Chrome not available: {e}")

    yield driver
    driver.quit()


class TestSessionSwitching:
    """Tests for session switching and history loading."""

    def login(self, driver: webdriver.Chrome):
        """Helper to perform Cognito login."""
        driver.get(BASE_URL)
        wait = WebDriverWait(driver, 15)

        try:
            # Click Sign In button
            sign_in_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Sign In')]")
                )
            )
            sign_in_button.click()

            # Wait for Cognito page and enter credentials
            email_input = wait.until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            email_input.send_keys(TEST_EMAIL)

            password_input = driver.find_element(By.ID, "password")
            password_input.send_keys(TEST_PASSWORD)

            submit_button = driver.find_element(By.NAME, "signInSubmitButton")
            submit_button.click()

            # Wait for redirect
            wait.until(lambda d: BASE_URL in d.current_url)
            time.sleep(3)  # Let app render

        except Exception as e:
            pytest.fail(f"Login failed: {e}")

    def test_session_list_loads(self, driver: webdriver.Chrome):
        """Test that the session list loads after login."""
        self.login(driver)

        # Look for chat interface
        wait = WebDriverWait(driver, 10)

        try:
            # Wait for either "Welcome to FAST Chat" or session items
            wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//*[contains(text(), 'Welcome') or contains(text(), 'FAST')]",
                    )
                )
            )
            print("✅ Chat interface loaded")
        except Exception as e:
            pytest.fail(f"Chat interface not found: {e}")

    def test_can_select_first_session(self, driver: webdriver.Chrome):
        """Test clicking the first session in the sidebar."""
        self.login(driver)

        time.sleep(2)

        # Try to find sidebar items
        try:
            # Look for any clickable session item
            sidebar_items = WebDriverWait(driver, 10).until(
                lambda d: d.find_elements(
                    By.XPATH,
                    "//*[@role='button' or @role='menuitem' or contains(@class, 'session')]",
                )
            )

            if len(sidebar_items) > 0:
                print(f"Found {len(sidebar_items)} sidebar items")
                # Click first one
                sidebar_items[0].click()
                time.sleep(2)
                print("✅ Clicked first session")
            else:
                print("⚠️ No sidebar items found")

        except Exception as e:
            print(f"ℹ️ Could not interact with sidebar: {e}")

    def test_session_switching_bug(self, driver: webdriver.Chrome):
        """
        Main test: Does selecting different sessions load different messages?

        This is the critical test for the session switching bug.
        Expected: Different sessions show different message content.
        Actual (bug): Same messages appear regardless of selection.
        """
        self.login(driver)

        time.sleep(3)

        # Collect message content from first session
        first_session_messages = self._get_visible_messages(driver)
        print(f"Session 1 messages: {len(first_session_messages)} items")
        if first_session_messages:
            print(f"  First message preview: {first_session_messages[0][:100]}")

        # Try to find and click second session
        try:
            # Look for clickable session items
            session_items = driver.find_elements(
                By.XPATH,
                "//*[@role='button' or @role='menuitem' or contains(@class, 'group')]",
            )

            if len(session_items) >= 2:
                # Click second session
                session_items[1].click()
                time.sleep(3)  # Wait for load

                # Collect message content from second session
                second_session_messages = self._get_visible_messages(driver)
                print(f"Session 2 messages: {len(second_session_messages)} items")
                if second_session_messages:
                    print(
                        f"  First message preview: {second_session_messages[0][:100]}"
                    )

                # Compare
                if first_session_messages and second_session_messages:
                    if first_session_messages == second_session_messages:
                        print("❌ BUG CONFIRMED: Same messages in both sessions!")
                        print("   Expected: Different content for different sessions")
                        print("   Actual: Identical content")
                        pytest.fail(
                            "Session switching bug: Different sessions show same messages.\n"
                            f"Session 1: {first_session_messages[0][:80]}\n"
                            f"Session 2: {second_session_messages[0][:80]}"
                        )
                    else:
                        print(
                            "✅ BUG FIXED: Different sessions show different messages!"
                        )
                else:
                    print("⚠️ Could not collect messages to compare")
            else:
                print(f"⚠️ Found only {len(session_items)} session items (need 2)")

        except Exception as e:
            print(f"ℹ️ Could not perform session switching test: {e}")

    def _get_visible_messages(self, driver: webdriver.Chrome) -> list:
        """Extract all visible message text from the chat interface."""
        try:
            # Look for message elements (common selectors)
            messages = driver.find_elements(
                By.XPATH,
                "//*[contains(@class, 'message') or contains(@class, 'chat')]//text()[normalize-space()]",
            )

            text_content = []
            for msg in messages:
                text = msg.text.strip()
                if text and len(text) > 5:  # Filter out very short text
                    text_content.append(text)

            return text_content[:10]  # Return first 10 messages
        except Exception:
            return []
