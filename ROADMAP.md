# Systemd Notifier - Feature Roadmap

This document tracks planned features, enhancements, and improvements for systemd-notifier. Use this as a reference when implementing new features.

**Last Updated:** 2024-03-12  
**Current Version:** 1.0.0+

---

## ✅ Implemented Features

### v1.0.0 (Initial Release)
- [x] Screen lock/unlock detection via D-Bus
- [x] Sleep/suspend and wake detection
- [x] Shutdown/reboot detection
- [x] Telegram notification support
- [x] Configurable pre-event delay
- [x] Debouncing to prevent notification spam
- [x] Support for config file or environment variables
- [x] Automated installation script
- [x] Comprehensive documentation
- [x] systemd user service integration
- [x] Retry logic for Telegram API failures
- [x] Rich HTML-formatted notifications

### v1.1.0 (Session Detection Fix)
- [x] Fix: Auto-detect graphical session (not relying on XDG_SESSION_ID)
- [x] Fix: Service file improvements for better session context

### v1.2.0 (CLI & Customization)
- [x] `--test` flag: Send test notification
- [x] `--status` flag: Show configuration and service status
- [x] `--version` flag: Show version information
- [x] Custom scripts per event (async execution)
- [x] Notification templates with HTML support
- [x] Environment variables passed to custom scripts

---

## 🚧 Planned Features

### High Priority

#### ~~1. Discord/Slack Notification Backends~~ ✅ COMPLETED
Discord backend implemented. Slack still pending.

#### 2. Network Events Monitoring ✅ COMPLETED
**Status:** Implemented  
**Priority:** High  
**Completed:** 2024-03-14

**Description:**
Add support for Discord and Slack webhooks as alternative notification backends. Allow users to send notifications to multiple platforms simultaneously.

**Requirements:**
- Add `BACKEND` config option (values: `telegram`, `discord`, `slack`, `multi`)
- Discord webhook support (POST to webhook URL)
- Slack webhook support (POST to webhook URL)
- Support for multiple backends (e.g., send to both Telegram and Discord)
- Maintain backward compatibility (default to Telegram)
- Update example.env with configuration examples

**Configuration Example:**
```bash
BACKEND=multi
BACKENDS=telegram,discord

# Telegram (existing)
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

**Implementation Notes:**
- Create `DiscordNotifier` and `SlackNotifier` classes similar to `TelegramNotifier`
- Abstract base class `NotificationBackend` for common interface
- Template variables should work across all backends
- Consider rate limiting when using multiple backends

---

#### 2. Battery Level Monitoring (Laptops)
**Status:** Not Started  
**Priority:** High  
**Complexity:** Medium

**Description:**
Monitor battery status and send notifications for critical battery levels, full charge, and power state changes.

**Requirements:**
- Monitor via D-Bus (UPower interface) or `/sys/class/power_supply/`
- Configurable battery thresholds (default: warn at 20%, critical at 10%)
- Notifications for:
  - Battery low (below threshold)
  - Battery critical (immediate action needed)
  - Battery fully charged
  - AC power connected
  - AC power disconnected
- Option to inhibit sleep when battery is critical
- Only run on systems with battery (auto-detect)

**Configuration Example:**
```bash
ENABLE_BATTERY_MONITOR=true
BATTERY_WARNING_LEVEL=20
BATTERY_CRITICAL_LEVEL=10
NOTIFY_ON_BATTERY_LOW=true
NOTIFY_ON_BATTERY_CRITICAL=true
NOTIFY_ON_BATTERY_FULL=true
NOTIFY_ON_POWER_CONNECTED=true
NOTIFY_ON_POWER_DISCONNECTED=false
```

**Implementation Notes:**
- Use UPower D-Bus interface: `org.freedesktop.UPower`
- Check for battery presence before starting monitor
- Poll battery status every 60 seconds (configurable)
- Debounce to prevent spam when hovering near threshold

---

#### ~~3. Network Connectivity Events~~ ✅ COMPLETED
**Status:** Implemented  
**Priority:** High  
**Completed:** 2024-03-14

**Description:**
Monitor network interface changes and send notifications for WiFi connections, disconnections, VPN status changes, and IP address changes.

**Features Implemented:**
- ✅ WiFi connected/disconnected (no SSID for privacy)
- ✅ VPN connected/disconnected (VPN disconnect always notifies for security)
- ✅ Ethernet connected/disconnected
- ✅ Internet lost (link state)
- ✅ Internet unreachable (reachability check via ping)
- ✅ 5-second debounce on non-critical events
- ✅ Critical-only mode vs all-events mode
- ✅ NetworkManager D-Bus integration
- ✅ Graceful handling when NetworkManager unavailable

**Configuration:**
See `config/example.env` for all network monitoring options.

---

### Medium Priority

#### 4. Quiet Hours / Do Not Disturb
**Status:** Not Started  
**Priority:** Medium  
**Complexity:** Low

**Description:**
Suppress notifications during specified time ranges (e.g., nighttime hours).

**Requirements:**
- Configurable quiet hours (start time, end time)
- Per-event quiet hour overrides
- Support for multiple quiet periods
- Timezone handling (use system timezone)
- Option to allow critical notifications (battery critical, shutdown) during quiet hours

**Configuration Example:**
```bash
ENABLE_QUIET_HOURS=true
QUIET_HOURS_START=23:00
QUIET_HOURS_END=07:00
QUIET_HOURS_ALLOW_CRITICAL=true  # Allow battery critical, shutdown during quiet hours

# Per-event override
QUIET_HOURS_EXCLUDE_EVENTS=shutdown,battery_critical
```

**Implementation Notes:**
- Parse time strings (24-hour format)
- Handle wrap-around (e.g., 23:00 to 07:00 crosses midnight)
- Check quiet hours before sending any notification
- Log when notifications are suppressed

---

#### 5. Conditional Notifications
**Status:** Not Started  
**Priority:** Medium  
**Complexity:** Medium

**Description:**
Only send notifications when certain conditions are met (e.g., uptime threshold, specific users, time since last event).

**Requirements:**
- Uptime-based conditions (e.g., only notify shutdown if uptime > 24h)
- Time-since-last-event conditions (e.g., only notify lock if unlocked > 5 min)
- User-specific conditions (e.g., only for certain logged-in users)
- Process-based conditions (e.g., only if specific process is running)
- Configurable per event type

**Configuration Example:**
```bash
# Only notify on shutdown if system has been up for more than 24 hours
SHUTDOWN_MIN_UPTIME_HOURS=24

# Only notify on lock if it's been more than 5 minutes since unlock
LOCK_MIN_SINCE_UNLOCK_MINUTES=5

# Only notify when specific user is logged in
CONDITIONAL_USERS=alice,bob

# Only notify if specific process is running
LOCK_ONLY_IF_PROCESS_RUNNING=firefox
```

**Implementation Notes:**
- Read `/proc/uptime` for system uptime
- Track event timestamps in memory
- Check conditions before sending notification
- Conditions should not block custom scripts

---

#### 6. Notification History & Statistics
**Status:** Not Started  
**Priority:** Medium  
**Complexity:** Low

**Description:**
Track notification history and provide statistics via CLI command.

**Requirements:**
- Track count of notifications per event type
- Track last notification timestamp per event type
- Store data in JSON file (~/.local/share/systemd-notifier/stats.json)
- Add `--stats` CLI command to view statistics
- Show daily/weekly/monthly notification counts

**CLI Example:**
```bash
$ notifier.py --stats
📊 Notification Statistics
==================================

Total Notifications: 47

By Event Type:
  Lock:      23 notifications
  Unlock:    21 notifications
  Sleep:     2 notifications
  Wake:      2 notifications
  Shutdown:  1 notification

Last Notifications:
  Lock:      2024-01-15 14:30:00 (5 minutes ago)
  Sleep:     2024-01-14 23:15:00 (1 day ago)
  Shutdown:  2024-01-10 18:00:00 (5 days ago)

This Week: 45 notifications
Last Week: 89 notifications
```

**Implementation Notes:**
- Append to JSON file on each notification
- Rotate/trim old entries (keep last 1000)
- Don't fail if stats file is corrupted
- Stats gathering should not block notifications

---

#### 7. Log Rotation & Management
**Status:** Not Started  
**Priority:** Medium  
**Complexity:** Low

**Description:**
Prevent log files and journal entries from growing indefinitely.

**Requirements:**
- Configurable log retention period (default: 30 days)
- Auto-cleanup old journal entries for the service
- Optional file-based logging with rotation
- Archive or delete old logs

**Configuration Example:**
```bash
LOG_RETENTION_DAYS=30
ENABLE_FILE_LOGGING=false
FILE_LOG_PATH=/var/log/systemd-notifier.log
FILE_LOG_MAX_SIZE=10MB
FILE_LOG_BACKUP_COUNT=5
```

**Implementation Notes:**
- Use systemd journal vacuum: `journalctl --vacuum-time=30d`
- Run cleanup weekly via systemd timer (optional)
- Use Python's RotatingFileHandler if file logging enabled

---

### Lower Priority

#### 8. GUI Configuration Tool
**Status:** Not Started  
**Priority:** Low  
**Complexity:** High

**Description:**
Simple GTK-based GUI for configuring systemd-notifier settings.

**Requirements:**
- Edit all configuration options via GUI
- Test notification button
- Service start/stop/restart buttons
- Status indicator (green/red for running/stopped)
- Template preview
- Script picker with validation

**Implementation Notes:**
- Use GTK3 or GTK4 with Python bindings
- Package as optional component
- Don't require GUI dependencies for base installation
- Save config atomically (write to temp, then move)

---

#### 9. Windows Support
**Status:** Not Started  
**Priority:** Low  
**Complexity:** High

**Description:**
Port systemd-notifier to Windows using Win32 API for system event monitoring.

**Requirements:**
- Detect lock/unlock via WTSRegisterSessionNotification
- Detect sleep/wake via WM_POWERBROADCAST
- Detect shutdown via WM_QUERYENDSESSION
- Cross-platform abstraction layer
- Windows service support (instead of systemd)

**Implementation Notes:**
- Create platform abstraction: `PlatformMonitor` base class
- Linux implementation: `SystemdMonitor`
- Windows implementation: `WindowsMonitor`
- Use pywin32 or ctypes for Win32 API calls
- Separate repository or branch?

---

#### 10. macOS Support
**Status:** Not Started  
**Priority:** Low  
**Complexity:** High

**Description:**
Port systemd-notifier to macOS using NSWorkspace notifications.

**Requirements:**
- Detect lock/unlock via NSWorkspace notifications
- Detect sleep/wake via IOKit power management
- Detect shutdown via NSWorkspace notifications
- LaunchAgent support (instead of systemd)

**Implementation Notes:**
- Use PyObjC for macOS API access
- Create `MacOSMonitor` implementation
- LaunchAgent plist for auto-start
- Consider using macOS notifications (Notification Center) as backend

---

#### 11. Email Notifications
**Status:** Not Started  
**Priority:** Low  
**Complexity:** Medium

**Description:**
Add email as a notification backend option.

**Requirements:**
- SMTP configuration (server, port, username, password)
- Support for TLS/SSL
- Configurable recipient(s)
- Email subject template
- Email body template (HTML or plain text)

**Configuration Example:**
```bash
ENABLE_EMAIL=false
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=app-password
EMAIL_TO=admin@example.com,backup@example.com
EMAIL_SUBJECT_TEMPLATE="[System Alert] {event_type} on {hostname}"
```

---

#### 12. Pushover/Pushbullet Support
**Status:** Not Started  
**Priority:** Low  
**Complexity:** Low

**Description:**
Add support for Pushover and Pushbullet push notification services.

**Requirements:**
- Pushover API integration
- Pushbullet API integration
- Priority levels for Pushover

---

## 🔧 Technical Improvements

### Code Quality
- [ ] Add type hints throughout codebase
- [ ] Add unit tests with pytest
- [ ] Add integration tests for D-Bus interactions
- [ ] Code coverage reporting
- [ ] Linting with flake8/pylint

### Documentation
- [ ] API documentation for extending backends
- [ ] Troubleshooting guide with common issues
- [ ] Video tutorial/gif demonstrations
- [ ] Migration guide for major version updates

### Packaging
- [ ] Debian/Ubuntu .deb package
- [ ] Arch Linux AUR package
- [ ] Fedora/RPM package
- [ ] Snap package
- [ ] Flatpak package

---

## 🎯 Implementation Guidelines

### When Adding a New Feature:

1. **Update this roadmap** - Mark the feature as "In Progress"
2. **Update CHANGELOG.md** - Add to [Unreleased] section
3. **Update example.env** - Add configuration examples
4. **Update README.md** - Document the feature
5. **Add tests** - Unit tests for new functionality
6. **Test thoroughly** - Test edge cases and error conditions
7. **Update version** - Bump version in `notifier.py` if significant

### Code Standards:

- Follow existing code style (PEP 8)
- Add docstrings to all new functions/classes
- Use type hints where possible
- Handle errors gracefully with logging
- Don't break backward compatibility
- Update DEFAULT_CONFIG with new options

### Configuration Pattern:

```python
# In DEFAULT_CONFIG
"NEW_FEATURE_ENABLED": "false",
"NEW_FEATURE_SETTING": "default_value",

# In code
if self.config.get_bool("NEW_FEATURE_ENABLED"):
    setting = self.config.get("NEW_FEATURE_SETTING")
```

---

## 📊 Priority Legend

- **High:** Core functionality, highly requested, significant user value
- **Medium:** Useful additions, moderate complexity
- **Low:** Nice-to-have, high complexity, or niche use cases

---

## 🤝 Contributing

When implementing a feature from this roadmap:

1. Comment on the feature or create an issue to claim it
2. Create a feature branch: `git checkout -b feature/battery-monitoring`
3. Implement with tests and documentation
4. Update this roadmap to mark as completed
5. Submit a pull request

---

**Questions or suggestions?** Open an issue or discussion on GitHub.
