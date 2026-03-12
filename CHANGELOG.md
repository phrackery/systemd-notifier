# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-01-01

### Added
- Initial release
- Screen lock/unlock detection via D-Bus
- Sleep/suspend and wake detection
- Shutdown/reboot detection
- Telegram notification support
- Configurable pre-event delay (default 10 seconds)
- Debouncing to prevent notification spam
- Support for config file or environment variables
- Automated installation script
- Comprehensive documentation
- systemd user service integration
- Retry logic for Telegram API failures
- Rich HTML-formatted notifications

### Features
- Cross-distribution support (Ubuntu, Arch, etc.)
- No root privileges required
- Works with both X11 and Wayland
- Event-specific notification toggles
- Customizable logging levels

## [Unreleased]

### Planned
- Windows support via Win32 API
- macOS support via NSWorkspace
- Discord/Slack notification backends
- GUI configuration tool
- Battery level monitoring
- Network connectivity events

