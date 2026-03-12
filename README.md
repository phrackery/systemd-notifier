# systemd-notifier

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![systemd](https://img.shields.io/badge/systemd-supported-green.svg)](https://systemd.io/)

Send Telegram notifications right before your Linux computer locks the screen, goes to sleep, or shuts down. Works on Ubuntu, Arch Linux, and any systemd-based distribution.

## Features

🔔 **Pre-Event Notifications** - Get notified BEFORE events happen, not after  
🔒 **Screen Lock Detection** - Know when your screen is locked  
💤 **Sleep/Suspend Monitoring** - Get notified before and after sleep  
🔴 **Shutdown Warnings** - Never accidentally shut down without knowing  
⏱️ **Customizable Delays** - Set how many seconds before the event to notify  
🛡️ **Debouncing** - Prevents notification spam  
🌐 **Cross-Distribution** - Works on Ubuntu, Arch, and all systemd systems  
🔧 **Easy Configuration** - Config file or environment variables  
📱 **Rich Notifications** - Includes hostname, timestamp, and event details  

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/systemd-notifier.git
cd systemd-notifier

# Run the installer
./install.sh

# Edit configuration with your Telegram bot token
nano ~/.config/systemd-notifier/config.env

# Start the service
systemctl --user start system-notifier
systemctl --user enable system-notifier
```

## Demo

When your system is about to sleep, you'll receive a Telegram message like:

```
💤 System Event 💤

Event: SLEEP
Hostname: my-laptop
Time: 2024-01-01 14:30:00
Message: System going to sleep in 10s
```

## Requirements

- Linux with systemd (Ubuntu 18.04+, Arch Linux, etc.)
- Python 3.7 or higher
- D-Bus Python bindings
- curl
- A Telegram bot token and chat ID

## Installation

### Automated Installation (Recommended)

```bash
./install.sh
```

The installer will:
- Install required dependencies
- Copy files to appropriate locations
- Set up the systemd user service
- Guide you through configuration

### Manual Installation

See [INSTALL.md](INSTALL.md) for detailed step-by-step instructions.

### Using Environment Variables (Alternative to Config File)

Instead of using a config file, you can set environment variables:

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export PRE_EVENT_DELAY="10"
```

Then run the notifier directly:
```bash
~/.local/share/systemd-notifier/src/notifier.py
```

## Configuration

Edit `~/.config/systemd-notifier/config.env`:

```ini
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Timing (seconds before event to notify)
PRE_EVENT_DELAY=10

# Event toggles
event_notification:
  lock: true        # Notify on screen lock
  unlock: false     # Notify on unlock
  sleep: true       # Notify before sleep
  wake: true        # Notify on wake
  shutdown: true    # Notify before shutdown

# Debouncing
ENABLE_DEBOUNCE=true
DEBOUNCE_SECONDS=5
```

### Configuration Options

| Option | Description | Default | Notes |
|--------|-------------|---------|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot's API token | Required | Get from @BotFather |
| `TELEGRAM_CHAT_ID` | Target chat/user ID | Required | Use @userinfobot |
| `PRE_EVENT_DELAY` | Seconds to wait before notifying | 10 | Use 60 for 1 minute |
| `NOTIFY_ON_LOCK` | Notify on screen lock | true | |
| `NOTIFY_ON_UNLOCK` | Notify on screen unlock | false | Usually not needed |
| `NOTIFY_ON_SLEEP` | Notify before sleep | true | |
| `NOTIFY_ON_WAKE` | Notify on wake | true | |
| `NOTIFY_ON_SHUTDOWN` | Notify before shutdown | true | |
| `ENABLE_DEBOUNCE` | Prevent duplicate notifications | true | |
| `DEBOUNCE_SECONDS` | Minimum time between duplicates | 5 | |
| `LOG_LEVEL` | Verbosity (DEBUG/INFO/WARNING/ERROR) | INFO | |

## How It Works

1. **Event Detection**: Uses D-Bus to monitor signals from `systemd-logind`
   - `Lock` / `Unlock` - Screen lock events
   - `PrepareForSleep` - Sleep/hibernate events
   - `PrepareForShutdown` - Shutdown/reboot events

2. **Inhibitor Locks**: Takes "delay" locks to pause the system event
   - Gives time to send the notification
   - Default 5-second timeout (configurable via logind.conf)

3. **Pre-Event Delay**: Waits for configured seconds before notifying
   - Set `PRE_EVENT_DELAY=60` to get notified 1 minute before

4. **Telegram API**: Sends rich HTML-formatted messages via Bot API

5. **Debouncing**: Prevents multiple notifications for rapid events

## Usage Examples

### Get notified 1 minute before shutdown
```ini
PRE_EVENT_DELAY=60
NOTIFY_ON_SHUTDOWN=true
```

### Only notify on lock and sleep
```ini
NOTIFY_ON_LOCK=true
NOTIFY_ON_UNLOCK=false
NOTIFY_ON_SLEEP=true
NOTIFY_ON_WAKE=false
NOTIFY_ON_SHUTDOWN=false
```

### Disable debouncing (allow rapid notifications)
```ini
ENABLE_DEBOUNCE=false
```

## Managing the Service

```bash
# Check status
systemctl --user status system-notifier

# Start/stop/restart
systemctl --user start system-notifier
systemctl --user stop system-notifier
systemctl --user restart system-notifier

# Enable/disable auto-start
systemctl --user enable system-notifier
systemctl --user disable system-notifier

# View logs
journalctl --user -u system-notifier -f
```

## Supported Events

| Event | D-Bus Signal | When It Fires |
|-------|--------------|---------------|
| Lock | `org.freedesktop.login1.Session.Lock` | Screen is being locked |
| Unlock | `org.freedesktop.login1.Session.Unlock` | Screen is being unlocked |
| Sleep | `org.freedesktop.login1.Manager.PrepareForSleep` (active=true) | Before suspend |
| Wake | `org.freedesktop.login1.Manager.PrepareForSleep` (active=false) | After resume |
| Shutdown | `org.freedesktop.login1.Manager.PrepareForShutdown` | Before power off |

## Architecture

```
systemd-notifier/
├── src/
│   ├── notifier.py      # Main event monitor (Python/D-Bus)
│   └── telegram.sh      # Telegram sender script (Bash/curl)
├── systemd/
│   └── system-notifier.service  # systemd user service
├── config/
│   └── example.env      # Example configuration
├── install.sh           # Automated installer
└── uninstall.sh         # Uninstaller
```

## Troubleshooting

### Service won't start

Check logs:
```bash
journalctl --user -u system-notifier -n 50
```

### No notifications received

1. Verify bot token and chat ID
2. Ensure you've started a chat with the bot
3. Test manually:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d "chat_id=<CHAT_ID>" \
  -d "text=Test message"
```

### Events not detected

Check D-Bus connection:
```bash
dbus-monitor --system "type='signal',interface='org.freedesktop.login1.Manager'"
```

### Permission errors

Ensure config file has correct permissions:
```bash
chmod 600 ~/.config/systemd-notifier/config.env
```

### Lock/unlock detection not working

If you see `WARNING:root:XDG_SESSION_ID not set, lock/unlock monitoring unavailable`, the notifier can't detect screen lock events (sleep/shutdown still work fine).

**Quick fix:**
```bash
# Find your session ID
loginctl list-sessions

# Set it (replace X with your session number)
export XDG_SESSION_ID=X
./src/notifier.py
```

See [INSTALL.md](INSTALL.md) for detailed troubleshooting.

## Compatibility

✅ Ubuntu 18.04, 20.04, 22.04, 24.04  
✅ Arch Linux  
✅ Manjaro  
✅ Pop!_OS  
✅ Fedora  
✅ Debian 10+  
✅ Any systemd-based distribution  

Requires:
- systemd 221 or newer (for inhibitor locks)
- Python 3.7+
- D-Bus Python bindings

## Security Considerations

- Bot tokens are stored in `~/.config/systemd-notifier/config.env` with mode 600
- Service runs as user (not root)
- No elevated privileges required
- All communication with Telegram uses HTTPS

## Future Enhancements

Potential features for future versions:
- [ ] Windows support (via Win32 API)
- [ ] macOS support (via NSWorkspace notifications)
- [ ] Multiple notification backends (Discord, Slack, email)
- [ ] GUI configuration tool
- [ ] Battery level monitoring
- [ ] Network connectivity events
- [ ] Custom scripts per event

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by the need to prevent accidental shutdowns
- Built on top of systemd's excellent D-Bus APIs
- Thanks to the Telegram Bot API for reliable messaging

## Support

- 📖 [Installation Guide](INSTALL.md)
- 🐛 [Issue Tracker](../../issues)
- 💬 [Discussions](../../discussions)

---

Made with ❤️ by [your name](https://github.com/yourusername)
