# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Pytest fixtures for integration tests.

Handles Cognito authentication and browser setup for end-to-end testing.
"""

import os
from typing import Generator

import boto3
import pytest
from dotenv import load_dotenv

# Load environment variables from .env if it exists
load_dotenv()

# Test configuration
TEST_EMAIL = os.getenv("TEST_EMAIL", "leanpsilva@gmail.com")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "Tifani%04")
BASE_URL = os.getenv("BASE_URL", "https://main.d3de0r2ujefnqj.amplifyapp.com")
COGNITO_DOMAIN = os.getenv(
    "COGNITO_DOMAIN",
    "juris-consult-455303857301-us-east-1.auth.us-east-1.amazoncognito.com",
)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


@pytest.fixture(scope="session")
def aws_client():
    """AWS Bedrock AgentCore client for session management tests."""
    return boto3.client("bedrock-agentcore", region_name=AWS_REGION)


@pytest.fixture(scope="session")
def dynamodb_client():
    """DynamoDB client for session metadata tests."""
    return boto3.client("dynamodb", region_name=AWS_REGION)


@pytest.fixture(scope="session")
def id_token() -> Generator[str, None, None]:
    """
    Obtain a Cognito ID token for the test user via the authorization code flow.

    This is a real authentication token that can be used to call the API
    endpoints in tests. The token is cached per session.

    Requires TEST_EMAIL and TEST_PASSWORD environment variables.
    """
    try:
        import time

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError:
        pytest.skip("Selenium not installed - skipping browser-based auth")
        return

    # Use Selenium to perform the OAuth flow and extract the token
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)

    try:
        # Navigate to the app
        driver.get(BASE_URL)

        # Wait for the Sign In button and click it
        wait = WebDriverWait(driver, 10)
        sign_in_button = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(text(), 'Sign In')]")
            )
        )
        sign_in_button.click()

        # Handle Cognito login page
        # Wait for email input
        email_input = wait.until(EC.presence_of_element_located((By.ID, "username")))
        email_input.send_keys(TEST_EMAIL)

        # Find and fill password field
        password_input = driver.find_element(By.ID, "password")
        password_input.send_keys(TEST_PASSWORD)

        # Submit the form
        submit_button = driver.find_element(By.NAME, "signInSubmitButton")
        submit_button.click()

        # Wait for redirect back to the app
        wait.until(lambda d: BASE_URL in d.current_url)

        # Give the app time to store the token
        time.sleep(2)

        # Extract the ID token from localStorage via JavaScript
        id_token_value = driver.execute_script(
            """
            return new Promise((resolve) => {
                const token = localStorage.getItem('oidc.user:https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TMkf2d8Ah:35kp004i619fmt64pb5beo4dlj')
                if (token) {
                    const user = JSON.parse(token)
                    resolve(user.id_token)
                } else {
                    resolve(null)
                }
            })
            """
        )

        if not id_token_value:
            raise RuntimeError("Failed to extract ID token from localStorage")

        yield id_token_value

    finally:
        driver.quit()


@pytest.fixture
def authenticated_session(id_token: str):
    """
    Create a requests session with Cognito authentication headers.

    Args:
        id_token: The Cognito ID token from the id_token fixture.

    Returns:
        A requests.Session object with Authorization header set.
    """
    import requests

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {id_token}",
            "Content-Type": "application/json",
        }
    )
    return session


@pytest.fixture
def api_base_url() -> str:
    """Base URL for API calls (sessions endpoint)."""
    # The sessions API is at feedbackApiUrl from aws-exports.json
    # For now, we'll use a standard pattern based on the region
    return "https://n4oky36qz2.execute-api.us-east-1.amazonaws.com/prod/"
