# Manual Installation Guide

This guide provides step-by-step instructions for manually installing systemd-notifier without using the automated install script.

## Prerequisites

- systemd-based Linux distribution (Ubuntu, Arch, etc.)
- Python 3.7 or higher
- D-Bus Python bindings
- curl

### Distribution-Specific Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-dbus python3-gi curl
```

**Arch Linux:**
```bash
sudo pacman -S python python-dbus python-gobject curl
```

## Step 1: Create Directory Structure

```bash
mkdir -p ~/.local/share/systemd-notifier/src
mkdir -p ~/.config/systemd-notifier
mkdir -p ~/.config/systemd/user
```

## Step 2: Copy Source Files

Copy the following files from this repository:

```bash
# Copy Python notifier
cp src/notifier.py ~/.local/share/systemd-notifier/src/

# Copy Telegram script
cp src/telegram.sh ~/.local/share/systemd-notifier/src/

# Make them executable
chmod +x ~/.local/share/systemd-notifier/src/notifier.py
chmod +x ~/.local/share/systemd-notifier/src/telegram.sh
```

## Step 3: Copy Systemd Service

```bash
cp systemd/system-notifier.service ~/.config/systemd/user/
```

## Step 4: Configure

### Option A: Using Config File (Recommended)

1. Copy the example configuration:
```bash
cp config/example.env ~/.config/systemd-notifier/config.env
chmod 600 ~/.config/systemd-notifier/config.env
```

2. Edit the configuration file:
```bash
nano ~/.config/systemd-notifier/config.env
```

3. Set your Telegram credentials:
```ini
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### Option B: Using Environment Variables

Add to your `~/.bashrc`, `~/.zshrc`, or `~/.profile`:

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"
```

Then reload your shell configuration:
```bash
source ~/.bashrc  # or ~/.zshrc
```

## Step 5: Get Telegram Credentials

### Creating a Bot

1. Open Telegram and search for **@BotFather**
2. Start a conversation and send `/newbot`
3. Follow the prompts to name your bot
4. Save the bot token provided (format: `123456789:ABCdef...`)

### Getting Your Chat ID

**Method 1: Via BotFather and getUpdates**

1. Send a message to your new bot
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Look for `"chat":{"id":123456789` in the JSON response

**Method 2: Via @userinfobot**

1. Open Telegram and search for **@userinfobot**
2. Start the bot
3. It will reply with your user ID (use this as chat ID)

## Step 6: Test the Configuration

Before enabling the service, test it manually:

```bash
# Run the notifier directly (will exit after testing config)
~/.local/share/systemd-notifier/src/notifier.py
```

You should see output like:
```
2024-01-01 12:00:00 - INFO - Starting systemd-notifier v1.0.0
2024-01-01 12:00:00 - INFO - Monitoring system events...
```

Press Ctrl+C to exit.

## Step 7: Enable and Start the Service

### Reload systemd daemon
```bash
systemctl --user daemon-reload
```

### Start the service
```bash
systemctl --user start system-notifier
```

### Enable auto-start on login
```bash
systemctl --user enable system-notifier
```

## Step 8: Verify Installation

### Check service status
```bash
systemctl --user status system-notifier
```

### View logs
```bash
# Real-time logs
journalctl --user -u system-notifier -f

# All logs
journalctl --user -u system-notifier

# Logs since last boot
journalctl --user -u system-notifier -b
```

### Test notifications

**Test lock notification:**
```bash
loginctl lock-session
```

Then unlock and check your Telegram.

## Troubleshooting

### Service fails to start

1. Check the logs:
```bash
journalctl --user -u system-notifier -n 50
```

2. Verify D-Bus is running:
```bash
systemctl --user status dbus
```

3. Test Python D-Bus import:
```bash
python3 -c "from gi.repository import Gio, GLib; print('OK')"
```

### No Telegram notifications

1. Test Telegram script manually:
```bash
cd ~/.local/share/systemd-notifier/src
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
./telegram.sh "Test message"
```

2. Verify bot token and chat ID are correct
3. Check that you've started a conversation with the bot

### Permission denied errors

Ensure the scripts are executable:
```bash
chmod +x ~/.local/share/systemd-notifier/src/*.py
chmod +x ~/.local/share/systemd-notifier/src/*.sh
```

### Configuration not loading

Check file permissions on config.env:
```bash
ls -la ~/.config/systemd-notifier/config.env
```

Should be readable by your user (mode 600).

### Lock/unlock monitoring unavailable

If you see the warning: `WARNING:root:XDG_SESSION_ID not set, lock/unlock monitoring unavailable`

**Cause:** The notifier can't detect your desktop session ID, which is required to monitor screen lock/unlock events.

**Solution:**

1. **Find your session ID:**
```bash
loginctl list-sessions
```

2. **Set the environment variable:**
```bash
export XDG_SESSION_ID=<your_session_number>
```

For example, if your session ID is `2`:
```bash
export XDG_SESSION_ID=2
./src/notifier.py
```

3. **To make it permanent**, add to your shell profile:
```bash
# Get your session ID and add it to .bashrc
SESSION_ID=$(loginctl list-sessions | grep "$(whoami)" | grep "seat" | awk '{print $1}')
echo "export XDG_SESSION_ID=$SESSION_ID" >> ~/.bashrc
source ~/.bashrc
```

4. **When running as a systemd service**, this is handled automatically since systemd starts the service within your desktop session.

**Note:** Sleep, shutdown, and wake notifications will still work even without XDG_SESSION_ID set. Only lock/unlock monitoring requires it.

## Configuration Options

Edit `~/.config/systemd-notifier/config.env` to customize:

| Option | Description | Default |
|--------|-------------|---------|
| `PRE_EVENT_DELAY` | Seconds before event to notify | 10 |
| `NOTIFY_ON_LOCK` | Notify on screen lock | true |
| `NOTIFY_ON_UNLOCK` | Notify on screen unlock | false |
| `NOTIFY_ON_SLEEP` | Notify before sleep | true |
| `NOTIFY_ON_WAKE` | Notify on wake | true |
| `NOTIFY_ON_SHUTDOWN` | Notify before shutdown | true |
| `ENABLE_DEBOUNCE` | Prevent duplicate notifications | true |
| `DEBOUNCE_SECONDS` | Minimum time between duplicates | 5 |
| `LOG_LEVEL` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) | INFO |

## Updating

To update to a new version:

1. Stop the service:
```bash
systemctl --user stop system-notifier
```

2. Replace the source files with the new version

3. Start the service:
```bash
systemctl --user start system-notifier
```

Your configuration will be preserved.

## Uninstalling

1. Stop and disable the service:
```bash
systemctl --user stop system-notifier
systemctl --user disable system-notifier
```

2. Remove files:
```bash
rm -rf ~/.local/share/systemd-notifier
rm -f ~/.config/systemd/user/system-notifier.service
```

3. Reload systemd:
```bash
systemctl --user daemon-reload
```

4. Optionally remove configuration:
```bash
rm -rf ~/.config/systemd-notifier
```

## Getting Help

If you encounter issues not covered here:

1. Check the logs: `journalctl --user -u system-notifier -n 100`
2. Enable debug logging in config.env: `LOG_LEVEL=DEBUG`
3. Open an issue on GitHub with the log output
