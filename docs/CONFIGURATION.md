# Configuration Guide

This document provides detailed information about configuring systemd-notifier.

## Configuration Methods

systemd-notifier supports two configuration methods:

### Method 1: Config File (Recommended)

Create `~/.config/systemd-notifier/config.env`:

```bash
mkdir -p ~/.config/systemd-notifier
cp config/example.env ~/.config/systemd-notifier/config.env
chmod 600 ~/.config/systemd-notifier/config.env
```

### Method 2: Environment Variables

Export variables in your shell profile:

```bash
# ~/.bashrc or ~/.zshrc
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

## Configuration File Format

The config file uses a simple key=value format:

```ini
# This is a comment
KEY=value
ANOTHER_KEY="quoted value"
```

Rules:
- One setting per line
- Comments start with #
- Values can be quoted or unquoted
- Boolean values: true/false, yes/no, 1/0

## Required Settings

### TELEGRAM_BOT_TOKEN

Your Telegram bot's API token from @BotFather.

**Format:** `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`

**How to get:**
1. Message @BotFather on Telegram
2. Send `/newbot`
3. Follow prompts to create bot
4. Save the token provided

**Example:**
```ini
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
```

### TELEGRAM_CHAT_ID

The chat ID where messages will be sent.

**Format:** Numeric ID (e.g., `123456789`) or channel name

**How to get:**

**Method 1 - Via @userinfobot:**
1. Message @userinfobot
2. It replies with your user ID

**Method 2 - Via API:**
1. Send a message to your bot
2. Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789`

**Method 3 - For Groups:**
1. Add bot to group
2. Send a message in group
3. Check getUpdates API
4. The chat ID will be negative (e.g., `-123456789`)

**Example:**
```ini
TELEGRAM_CHAT_ID=123456789
```

## Event Settings

### NOTIFY_ON_LOCK

Send notification when screen is locked.

**Type:** Boolean
**Default:** true
**Example:**
```ini
NOTIFY_ON_LOCK=true
```

### NOTIFY_ON_UNLOCK

Send notification when screen is unlocked.

**Type:** Boolean
**Default:** false
**Example:**
```ini
NOTIFY_ON_UNLOCK=false
```

### NOTIFY_ON_SLEEP

Send notification before system goes to sleep.

**Type:** Boolean
**Default:** true
**Example:**
```ini
NOTIFY_ON_SLEEP=true
```

### NOTIFY_ON_WAKE

Send notification when system wakes from sleep.

**Type:** Boolean
**Default:** true
**Example:**
```ini
NOTIFY_ON_WAKE=true
```

### NOTIFY_ON_SHUTDOWN

Send notification before system shuts down.

**Type:** Boolean
**Default:** true
**Example:**
```ini
NOTIFY_ON_SHUTDOWN=true
```

## Timing Settings

### PRE_EVENT_DELAY

Number of seconds BEFORE the event to send the notification.

**Type:** Integer (seconds)
**Default:** 10
**Range:** 0-300 (5 minutes)

**Examples:**
```ini
# Notify 10 seconds before (default)
PRE_EVENT_DELAY=10

# Notify 1 minute before
PRE_EVENT_DELAY=60

# Notify immediately (no delay)
PRE_EVENT_DELAY=0
```

**Note:** The delay uses a systemd inhibitor lock, so the system will wait for this duration (up to InhibitDelayMaxSec, typically 5 seconds) before proceeding with the event.

### NOTIFICATION_TIMEOUT

Maximum time to wait for Telegram API response.

**Type:** Integer (seconds)
**Default:** 30
**Example:**
```ini
NOTIFICATION_TIMEOUT=30
```

## Debounce Settings

### ENABLE_DEBOUNCE

Prevent multiple notifications for the same event type within a short time window.

**Type:** Boolean
**Default:** true
**Example:**
```ini
ENABLE_DEBOUNCE=true
```

**Use case:** If you rapidly lock/unlock your screen, you won't get spammed with notifications.

### DEBOUNCE_SECONDS

Minimum time between duplicate notifications for the same event type.

**Type:** Integer (seconds)
**Default:** 5
**Example:**
```ini
DEBOUNCE_SECONDS=5
```

## Logging Settings

### LOG_LEVEL

Control the verbosity of log output.

**Type:** String
**Options:** DEBUG, INFO, WARNING, ERROR
**Default:** INFO

**Examples:**
```ini
# Minimal logging (errors only)
LOG_LEVEL=ERROR

# Normal operation
LOG_LEVEL=INFO

# Debug mode (verbose)
LOG_LEVEL=DEBUG
```

**View logs:**
```bash
# Real-time
journalctl --user -u system-notifier -f

# Recent entries
journalctl --user -u system-notifier -n 100
```

## Advanced Settings

### TELEGRAM_MAX_RETRIES

Maximum number of retry attempts for failed Telegram API calls.

**Type:** Integer
**Default:** 3
**Example:**
```ini
TELEGRAM_MAX_RETRIES=3
```

### TELEGRAM_RETRY_DELAY

Initial delay between retry attempts (exponential backoff is used).

**Type:** Integer (seconds)
**Default:** 2
**Example:**
```ini
TELEGRAM_RETRY_DELAY=2
```

## Configuration Examples

### Basic Setup
```ini
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=123456789
```

### Power User (All Events)
```ini
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=123456789

NOTIFY_ON_LOCK=true
NOTIFY_ON_UNLOCK=true
NOTIFY_ON_SLEEP=true
NOTIFY_ON_WAKE=true
NOTIFY_ON_SHUTDOWN=true

PRE_EVENT_DELAY=30
ENABLE_DEBOUNCE=true
DEBOUNCE_SECONDS=10
```

### Minimal (Sleep Only)
```ini
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=123456789

NOTIFY_ON_LOCK=false
NOTIFY_ON_UNLOCK=false
NOTIFY_ON_SLEEP=true
NOTIFY_ON_WAKE=false
NOTIFY_ON_SHUTDOWN=false

PRE_EVENT_DELAY=0
```

### Early Warning (1 Minute Notice)
```ini
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=123456789

PRE_EVENT_DELAY=60

NOTIFY_ON_LOCK=true
NOTIFY_ON_SLEEP=true
NOTIFY_ON_SHUTDOWN=true
```

### Debug Mode
```ini
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=123456789

LOG_LEVEL=DEBUG
ENABLE_DEBOUNCE=false
PRE_EVENT_DELAY=0
```

## Environment Variable Priority

Environment variables take precedence over config file settings. This allows:

1. **Temporary overrides:**
```bash
LOG_LEVEL=DEBUG systemctl --user restart system-notifier
```

2. **Different settings per session:**
```bash
export NOTIFY_ON_LOCK=false
~/.local/share/systemd-notifier/src/notifier.py
```

## Configuration Reload

After changing configuration:

```bash
# Restart the service
systemctl --user restart system-notifier

# Or if running manually, just restart the process
```

## Troubleshooting Configuration

### Config not loading

Check file location and permissions:
```bash
ls -la ~/.config/systemd-notifier/config.env
# Should show: -rw------- (mode 600)
```

### Invalid values

Check journal for errors:
```bash
journalctl --user -u system-notifier -n 50 | grep -i error
```

### Test configuration

Run manually to see config loading:
```bash
~/.local/share/systemd-notifier/src/notifier.py 2>&1 | head -20
```

## Security Notes

- Keep your bot token secret - treat it like a password
- Set config.env permissions to 600 (readable only by owner)
- Don't commit config.env to version control
- Rotate bot tokens periodically if concerned about exposure
