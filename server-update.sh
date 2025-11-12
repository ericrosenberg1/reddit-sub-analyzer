#!/bin/bash
# Server Update Script for Sub Search
# Run this on your server to pull latest changes and restart

set -e

echo "=== Sub Search Server Update ==="
echo ""

# Configuration (adjust these if needed)
APP_DIR="/opt/subsearch"
SERVICE_NAME="subsearch"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Step 1: Checking current directory...${NC}"
cd "$APP_DIR" || { echo "ERROR: Cannot access $APP_DIR"; exit 1; }
pwd

echo ""
echo -e "${YELLOW}Step 2: Cleaning up build artifacts...${NC}"
# Remove build artifacts
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
echo "✓ Cleaned up build artifacts"

echo ""
echo -e "${YELLOW}Step 3: Checking git status...${NC}"
git status

echo ""
echo -e "${YELLOW}Step 4: Fetching latest from GitHub...${NC}"
git fetch origin

echo ""
echo -e "${YELLOW}Step 5: Pulling latest changes...${NC}"
git pull origin main

echo ""
echo -e "${YELLOW}Step 6: Updating Python dependencies...${NC}"
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
echo "✓ Dependencies updated"

echo ""
echo -e "${YELLOW}Step 7: Checking service status...${NC}"
sudo systemctl status $SERVICE_NAME --no-pager || true

echo ""
echo -e "${YELLOW}Step 8: Restarting service...${NC}"
sudo systemctl restart $SERVICE_NAME

echo ""
echo -e "${YELLOW}Step 9: Verifying service is running...${NC}"
sleep 2
sudo systemctl status $SERVICE_NAME --no-pager

echo ""
echo -e "${GREEN}=== Update Complete! ===${NC}"
echo ""
echo "Next steps:"
echo "  • Check logs: sudo journalctl -u $SERVICE_NAME -f"
echo "  • Visit your site to verify the update"
echo ""
