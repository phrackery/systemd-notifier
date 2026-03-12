#!/usr/bin/env bash
#
# systemd-notifier Installation Script
# Automatically installs systemd-notifier on Ubuntu/Arch Linux systems
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="$HOME/.local/share/systemd-notifier"
CONFIG_DIR="$HOME/.config/systemd-notifier"
SYSTEMD_DIR="$HOME/.config/systemd/user"
REPO_URL="https://github.com/yourusername/systemd-notifier"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Function to detect the OS
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo "$ID"
    elif command -v lsb_release &>/dev/null; then
        lsb_release -is | tr '[:upper:]' '[:lower:]'
    else
        echo "unknown"
    fi
}

# Function to install dependencies on Ubuntu
install_deps_ubuntu() {
    print_status "Installing dependencies for Ubuntu..."
    
    local deps=("python3" "python3-dbus" "python3-gi" "curl")
    
    for dep in "${deps[@]}"; do
        if ! dpkg -l | grep -q "^ii  $dep "; then
            print_status "Installing $dep..."
            sudo apt-get update -qq
            sudo apt-get install -y -qq "$dep"
        fi
    done
    
    print_success "Dependencies installed"
}

# Function to install dependencies on Arch
install_deps_arch() {
    print_status "Installing dependencies for Arch Linux..."
    
    local deps=("python" "python-dbus" "python-gobject" "curl")
    
    for dep in "${deps[@]}"; do
        if ! pacman -Q "$dep" &>/dev/null; then
            print_status "Installing $dep..."
            sudo pacman -S --noconfirm "$dep"
        fi
    done
    
    print_success "Dependencies installed"
}

# Function to install dependencies
install_dependencies() {
    local os=$(detect_os)
    
    case "$os" in
        ubuntu|debian|pop|linuxmint|elementary|zorin)
            install_deps_ubuntu
            ;;
        arch|manjaro|endeavouros|garuda)
            install_deps_arch
            ;;
        *)
            print_warning "Unknown distribution: $os"
            print_warning "Please install dependencies manually:"
            print_warning "  - Python 3"
            print_warning "  - python-dbus (or python3-dbus)"
            print_warning "  - python-gobject (or python3-gi)"
            print_warning "  - curl"
            read -p "Press Enter to continue or Ctrl+C to cancel..."
            ;;
    esac
}

# Function to create directories
create_directories() {
    print_status "Creating directories..."
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$SYSTEMD_DIR"
    
    print_success "Directories created"
}

# Function to copy files
copy_files() {
    print_status "Copying files..."
    
    # Copy source files
    if [[ -d "$SCRIPT_DIR/src" ]]; then
        cp -r "$SCRIPT_DIR/src" "$INSTALL_DIR/"
    else
        print_error "Source directory not found: $SCRIPT_DIR/src"
        exit 1
    fi
    
    # Copy example config
    if [[ -f "$SCRIPT_DIR/config/example.env" ]]; then
        cp "$SCRIPT_DIR/config/example.env" "$CONFIG_DIR/"
    fi
    
    # Copy systemd service
    if [[ -f "$SCRIPT_DIR/systemd/system-notifier.service" ]]; then
        cp "$SCRIPT_DIR/systemd/system-notifier.service" "$SYSTEMD_DIR/"
    fi
    
    # Make scripts executable
    chmod +x "$INSTALL_DIR/src/notifier.py"
    chmod +x "$INSTALL_DIR/src/telegram.sh"
    
    print_success "Files copied"
}

# Function to setup configuration
setup_configuration() {
    print_status "Setting up configuration..."
    
    if [[ ! -f "$CONFIG_DIR/config.env" ]]; then
        cp "$CONFIG_DIR/example.env" "$CONFIG_DIR/config.env"
        chmod 600 "$CONFIG_DIR/config.env"
        print_success "Configuration file created: $CONFIG_DIR/config.env"
        print_warning "Please edit this file with your Telegram bot token and chat ID"
    else
        print_warning "Configuration file already exists: $CONFIG_DIR/config.env"
    fi
}

# Function to reload systemd
reload_systemd() {
    print_status "Reloading systemd daemon..."
    systemctl --user daemon-reload
    print_success "Systemd daemon reloaded"
}

# Function to prompt for configuration
prompt_configuration() {
    print_status "Configuration required"
    echo ""
    
    # Get bot token
    echo -n "Enter your Telegram Bot Token (from @BotFather): "
    read -s bot_token
    echo ""
    
    # Get chat ID
    echo -n "Enter your Telegram Chat ID: "
    read chat_id
    echo ""
    
    # Get pre-event delay
    echo -n "Enter pre-event delay in seconds [10]: "
    read delay
    delay=${delay:-10}
    
    # Write configuration
    cat > "$CONFIG_DIR/config.env" << EOF
# systemd-notifier Configuration
TELEGRAM_BOT_TOKEN=$bot_token
TELEGRAM_CHAT_ID=$chat_id
PRE_EVENT_DELAY=$delay
NOTIFY_ON_LOCK=true
NOTIFY_ON_UNLOCK=false
NOTIFY_ON_SLEEP=true
NOTIFY_ON_WAKE=true
NOTIFY_ON_SHUTDOWN=true
ENABLE_DEBOUNCE=true
DEBOUNCE_SECONDS=5
LOG_LEVEL=INFO
EOF
    
    chmod 600 "$CONFIG_DIR/config.env"
    print_success "Configuration saved"
}

# Function to display post-installation instructions
show_post_install() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}Installation Complete!${NC}"
    echo "=========================================="
    echo ""
    echo "Configuration file: $CONFIG_DIR/config.env"
    echo ""
    echo "Next steps:"
    echo "  1. Edit the configuration file if you haven't already:"
    echo "     nano $CONFIG_DIR/config.env"
    echo ""
    echo "  2. Start the service:"
    echo "     systemctl --user start system-notifier"
    echo ""
    echo "  3. Enable auto-start on login:"
    echo "     systemctl --user enable system-notifier"
    echo ""
    echo "  4. Check status:"
    echo "     systemctl --user status system-notifier"
    echo ""
    echo "  5. View logs:"
    echo "     journalctl --user -u system-notifier -f"
    echo ""
    echo "=========================================="
}

# Function to check if running interactively
check_interactive() {
    if [[ ! -t 0 ]]; then
        return 1
    fi
    return 0
}

# Function to uninstall
uninstall() {
    print_status "Uninstalling systemd-notifier..."
    
    # Stop and disable service
    if systemctl --user is-active system-notifier &>/dev/null; then
        systemctl --user stop system-notifier
        print_success "Service stopped"
    fi
    
    if systemctl --user is-enabled system-notifier &>/dev/null; then
        systemctl --user disable system-notifier
        print_success "Service disabled"
    fi
    
    # Remove files
    rm -rf "$INSTALL_DIR"
    rm -f "$SYSTEMD_DIR/system-notifier.service"
    
    print_status "Configuration preserved at: $CONFIG_DIR/config.env"
    print_status "To remove configuration: rm -rf $CONFIG_DIR"
    
    print_success "Uninstallation complete"
}

# Main installation function
main() {
    echo "=========================================="
    echo -e "${BLUE}systemd-notifier Installer${NC}"
    echo "=========================================="
    echo ""
    
    # Check for uninstall flag
    if [[ "${1:-}" == "--uninstall" ]] || [[ "${1:-}" == "-u" ]]; then
        uninstall
        exit 0
    fi
    
    # Check for help flag
    if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  -h, --help       Show this help message"
        echo "  -u, --uninstall  Uninstall systemd-notifier"
        echo ""
        echo "This script installs systemd-notifier which sends Telegram"
        echo "notifications before screen lock, sleep, or shutdown events."
        exit 0
    fi
    
    # Check if running as root
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should not be run as root"
        print_error "It will use sudo only when necessary"
        exit 1
    fi
    
    # Check prerequisites
    if ! command -v python3 &>/dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    print_status "Detected OS: $(detect_os)"
    
    # Install dependencies
    install_dependencies
    
    # Create directories
    create_directories
    
    # Copy files
    copy_files
    
    # Setup configuration
    if check_interactive; then
        echo ""
        read -p "Would you like to configure now? (Y/n): " configure_now
        if [[ ! "$configure_now" =~ ^[Nn]$ ]]; then
            prompt_configuration
        else
            setup_configuration
        fi
    else
        setup_configuration
    fi
    
    # Reload systemd
    reload_systemd
    
    # Show post-installation instructions
    show_post_install
}

# Run main function
main "$@"
