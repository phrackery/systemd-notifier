#!/usr/bin/env bash
#
# systemd-notifier Uninstall Script
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Paths
INSTALL_DIR="$HOME/.local/share/systemd-notifier"
CONFIG_DIR="$HOME/.config/systemd-notifier"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo -e "${BLUE}[*]${NC} Uninstalling systemd-notifier..."

# Stop service
if systemctl --user is-active system-notifier &>/dev/null; then
    echo -e "${BLUE}[*]${NC} Stopping service..."
    systemctl --user stop system-notifier
fi

# Disable service
if systemctl --user is-enabled system-notifier &>/dev/null; then
    echo -e "${BLUE}[*]${NC} Disabling service..."
    systemctl --user disable system-notifier
fi

# Remove files
echo -e "${BLUE}[*]${NC} Removing files..."
rm -rf "$INSTALL_DIR"
rm -f "$SYSTEMD_DIR/system-notifier.service"

# Reload systemd
echo -e "${BLUE}[*]${NC} Reloading systemd daemon..."
systemctl --user daemon-reload

echo -e "${GREEN}[✓]${NC} Uninstallation complete!"
echo ""
echo -e "${YELLOW}[!]${NC} Configuration preserved at: $CONFIG_DIR/"
echo "    To remove configuration: rm -rf $CONFIG_DIR"
