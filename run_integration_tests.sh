#!/bin/bash

# Integration Tests Runner Script
# Usage: ./run_integration_tests.sh [api|ui|all|specific-test]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | grep -v '#' | xargs)
else
    echo -e "${YELLOW}Warning: .env file not found${NC}"
    echo "Create one by copying .env.example"
fi

# Ensure pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}pytest not found. Installing dependencies...${NC}"
    pip install -r test_requirements.txt
fi

# Determine which tests to run
TEST_SUITE="${1:-all}"

case $TEST_SUITE in
    api)
        echo -e "${GREEN}Running API integration tests...${NC}"
        pytest tests/integration/test_session_management.py -v
        ;;
    ui)
        echo -e "${GREEN}Running UI integration tests...${NC}"
        pytest tests/integration/test_frontend_ui.py -v
        ;;
    all)
        echo -e "${GREEN}Running all integration tests...${NC}"
        pytest tests/integration -v
        ;;
    *)
        echo -e "${GREEN}Running test: $TEST_SUITE${NC}"
        pytest "tests/integration/$TEST_SUITE" -v
        ;;
esac

echo -e "${GREEN}✓ Test run completed${NC}"
