#!/usr/bin/env python3
"""
systemd-notifier - Send Telegram notifications before system events (lock, sleep, shutdown)

Works on Ubuntu, Arch Linux, and other systemd-based distributions.
Monitors D-Bus signals from systemd-logind and sends notifications via Telegram.

Author: systemd-notifier contributors
License: MIT
"""

import os
import sys
import json
import time
import socket
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from threading import Lock

# Try to import D-Bus libraries
try:
    from gi.repository import Gio, GLib
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False
    print("Warning: D-Bus libraries not found. Please install python-gobject (Arch) or python3-gi (Ubuntu)")

# Version
__version__ = "1.0.0"

# Configuration defaults
DEFAULT_CONFIG = {
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "NOTIFY_ON_LOCK": "true",
    "NOTIFY_ON_UNLOCK": "false",
    "NOTIFY_ON_SLEEP": "true",
    "NOTIFY_ON_WAKE": "true",
    "NOTIFY_ON_SHUTDOWN": "true",
    "PRE_EVENT_DELAY": "10",  # Seconds before event to send notification
    "ENABLE_DEBOUNCE": "true",
    "DEBOUNCE_SECONDS": "5",
    "LOG_LEVEL": "INFO",
    "NOTIFICATION_TIMEOUT": "30",  # Timeout for sending notification
}


@dataclass
class EventInfo:
    """Information about a system event"""
    event_type: str
    hostname: str
    timestamp: str
    message: str = ""
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "event_type": self.event_type,
            "hostname": self.hostname,
            "timestamp": self.timestamp,
            "message": self.message,
        }


class ConfigManager:
    """Manages configuration from file or environment variables"""
    
    def __init__(self):
        self.config: Dict[str, str] = {}
        self.config_file: Optional[Path] = None
        self._load_config()
    
    def _get_config_paths(self) -> list[Path]:
        """Get possible config file locations"""
        paths = []
        
        # XDG config directory
        xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        paths.append(Path(xdg_config) / "systemd-notifier" / "config.env")
        
        # Legacy location
        paths.append(Path.home() / ".config" / "systemd-notifier.env")
        
        # Current directory (for development)
        paths.append(Path.cwd() / "config.env")
        
        return paths
    
    def _load_config(self) -> None:
        """Load configuration from file and/or environment"""
        # Start with defaults
        self.config = DEFAULT_CONFIG.copy()
        
        # Try to load from config file
        for config_path in self._get_config_paths():
            if config_path.exists():
                self._load_from_file(config_path)
                self.config_file = config_path
                break
        
        # Environment variables override file settings
        self._load_from_environment()
        
        # Validate required settings
        self._validate()
    
    def _load_from_file(self, path: Path) -> None:
        """Load configuration from a .env file"""
        try:
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')  # Remove quotes
                        if key in DEFAULT_CONFIG:
                            self.config[key] = value
            logging.info(f"Loaded configuration from {path}")
        except Exception as e:
            logging.warning(f"Failed to load config from {path}: {e}")
    
    def _load_from_environment(self) -> None:
        """Load configuration from environment variables"""
        for key in DEFAULT_CONFIG.keys():
            env_value = os.environ.get(key)
            if env_value is not None:
                self.config[key] = env_value
                logging.debug(f"Loaded {key} from environment")
    
    def _validate(self) -> None:
        """Validate required configuration"""
        if not self.config.get("TELEGRAM_BOT_TOKEN"):
            logging.error("TELEGRAM_BOT_TOKEN is required")
            sys.exit(1)
        
        if not self.config.get("TELEGRAM_CHAT_ID"):
            logging.error("TELEGRAM_CHAT_ID is required")
            sys.exit(1)
        
        # Convert boolean strings
        for key in ["NOTIFY_ON_LOCK", "NOTIFY_ON_UNLOCK", "NOTIFY_ON_SLEEP", 
                    "NOTIFY_ON_WAKE", "NOTIFY_ON_SHUTDOWN", "ENABLE_DEBOUNCE"]:
            self.config[key] = str(self.config.get(key, "false")).lower() == "true"
        
        # Convert integers
        for key in ["PRE_EVENT_DELAY", "DEBOUNCE_SECONDS", "NOTIFICATION_TIMEOUT"]:
            try:
                self.config[key] = int(self.config.get(key, 0))
            except ValueError:
                logging.warning(f"Invalid integer value for {key}, using default")
                self.config[key] = int(DEFAULT_CONFIG[key])
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)
    
    def get_bool(self, key: str) -> bool:
        """Get boolean configuration value"""
        value = self.config.get(key, False)
        if isinstance(value, bool):
            return value
        return str(value).lower() in ('true', '1', 'yes', 'on')
    
    def get_int(self, key: str) -> int:
        """Get integer configuration value"""
        value = self.config.get(key, 0)
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0


class Debouncer:
    """Prevents duplicate notifications within a time window"""
    
    def __init__(self, window_seconds: float = 5.0):
        self.window = window_seconds
        self.last_event_time: Dict[str, float] = {}
        self.lock = Lock()
    
    def should_process(self, event_type: str) -> bool:
        """Check if event should be processed (not debounced)"""
        with self.lock:
            now = time.time()
            last_time = self.last_event_time.get(event_type, 0)
            
            if now - last_time < self.window:
                return False
            
            self.last_event_time[event_type] = now
            return True
    
    def reset(self, event_type: str) -> None:
        """Reset debouncer for an event type"""
        with self.lock:
            self.last_event_time.pop(event_type, None)


class TelegramNotifier:
    """Handles sending notifications to Telegram"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.bot_token = config.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = config.get("TELEGRAM_CHAT_ID")
        self.timeout = config.get_int("NOTIFICATION_TIMEOUT")
    
    def _format_message(self, event: EventInfo) -> str:
        """Format event information into a rich message"""
        emoji_map = {
            "lock": "🔒",
            "unlock": "🔓",
            "sleep": "💤",
            "wake": "☀️",
            "shutdown": "🔴",
            "hibernate": "❄️",
        }
        
        emoji = emoji_map.get(event.event_type.lower(), "📱")
        
        message = f"""{emoji} <b>System Event</b> {emoji}

<b>Event:</b> <code>{event.event_type.upper()}</code>
<b>Hostname:</b> <code>{event.hostname}</code>
<b>Time:</b> <code>{event.timestamp}</code>"""
        
        if event.message:
            message += f"\n<b>Message:</b> {event.message}"
        
        return message
    
    def send_notification(self, event: EventInfo) -> bool:
        """Send notification to Telegram"""
        message_text = self._format_message(event)
        
        # Use the telegram.sh script for sending
        script_dir = Path(__file__).parent
        telegram_script = script_dir / "telegram.sh"
        
        if telegram_script.exists():
            # Use bash script
            env = os.environ.copy()
            env["TELEGRAM_BOT_TOKEN"] = self.bot_token
            env["TELEGRAM_CHAT_ID"] = self.chat_id
            
            try:
                result = subprocess.run(
                    [str(telegram_script), message_text],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=env
                )
                return result.returncode == 0
            except Exception as e:
                logging.error(f"Failed to send notification via script: {e}")
                return False
        else:
            # Fallback to direct curl
            return self._send_via_curl(message_text)
    
    def _send_via_curl(self, message: str) -> bool:
        """Send message using curl directly"""
        import urllib.parse
        
        encoded_message = urllib.parse.quote(message)
        
        cmd = [
            "curl", "-s", "-X", "POST",
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            "-d", f"chat_id={self.chat_id}",
            "-d", f"text={encoded_message}",
            "-d", "parse_mode=HTML",
            "-d", "disable_notification=false",
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0 and '"ok":true' in result.stdout:
                logging.info("Notification sent successfully")
                return True
            else:
                logging.error(f"Failed to send notification: {result.stderr}")
                return False
        except Exception as e:
            logging.error(f"Failed to send notification: {e}")
            return False


class SystemEventMonitor:
    """Monitors system events via D-Bus"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.notifier = TelegramNotifier(config)
        self.debouncer = Debouncer(config.get_int("DEBOUNCE_SECONDS"))
        self.bus: Optional[Gio.DBusConnection] = None
        self.subscriptions: list[int] = []
        self.inhibit_fd: Optional[int] = None
        self.hostname = socket.gethostname()
        
        # Event tracking
        self.pending_notifications: Dict[str, bool] = {}
        
        if not HAS_DBUS:
            logging.error("D-Bus libraries are required but not installed")
            sys.exit(1)
    
    def _get_timestamp(self) -> str:
        """Get formatted timestamp"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _create_event(self, event_type: str, message: str = "") -> EventInfo:
        """Create event info"""
        return EventInfo(
            event_type=event_type,
            hostname=self.hostname,
            timestamp=self._get_timestamp(),
            message=message
        )
    
    def _should_notify(self, event_type: str) -> bool:
        """Check if we should send notification for this event type"""
        config_map = {
            "lock": "NOTIFY_ON_LOCK",
            "unlock": "NOTIFY_ON_UNLOCK",
            "sleep": "NOTIFY_ON_SLEEP",
            "wake": "NOTIFY_ON_WAKE",
            "shutdown": "NOTIFY_ON_SHUTDOWN",
            "hibernate": "NOTIFY_ON_SLEEP",
        }
        
        config_key = config_map.get(event_type.lower())
        if not config_key:
            return False
        
        return self.config.get_bool(config_key)
    
    def _send_notification_async(self, event: EventInfo) -> None:
        """Send notification asynchronously"""
        import threading
        
        def send():
            try:
                self.notifier.send_notification(event)
            except Exception as e:
                logging.error(f"Failed to send notification: {e}")
        
        thread = threading.Thread(target=send)
        thread.daemon = True
        thread.start()
    
    def _take_delay_lock(self, what: str = "sleep:shutdown") -> bool:
        """Take a delay inhibitor lock"""
        try:
            result = self.bus.call_sync(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager",
                "Inhibit",
                GLib.Variant("(ssss)", (what, "systemd-notifier", "Sending notification", "delay")),
                GLib.VariantType("(h)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            self.inhibit_fd = result.unpack()[0]
            logging.debug(f"Taken delay lock for: {what}")
            return True
        except Exception as e:
            logging.warning(f"Failed to take delay lock: {e}")
            return False
    
    def _release_delay_lock(self) -> None:
        """Release the delay inhibitor lock"""
        if self.inhibit_fd is not None:
            try:
                os.close(self.inhibit_fd)
                self.inhibit_fd = None
                logging.debug("Released delay lock")
            except Exception as e:
                logging.warning(f"Failed to release delay lock: {e}")
    
    def _handle_lock(self, conn, sender, path, iface, signal, params) -> None:
        """Handle screen lock event"""
        if not self._should_notify("lock"):
            return
        
        if self.config.get_bool("ENABLE_DEBOUNCE"):
            if not self.debouncer.should_process("lock"):
                logging.debug("Lock event debounced")
                return
        
        logging.info("Screen locked")
        
        # Wait for configured delay before sending
        delay = self.config.get_int("PRE_EVENT_DELAY")
        if delay > 0:
            logging.debug(f"Waiting {delay}s before sending notification")
            time.sleep(delay)
        
        event = self._create_event("lock", f"Screen locked in {delay}s")
        self._send_notification_async(event)
    
    def _handle_unlock(self, conn, sender, path, iface, signal, params) -> None:
        """Handle screen unlock event"""
        if not self._should_notify("unlock"):
            return
        
        if self.config.get_bool("ENABLE_DEBOUNCE"):
            if not self.debouncer.should_process("unlock"):
                logging.debug("Unlock event debounced")
                return
        
        logging.info("Screen unlocked")
        event = self._create_event("unlock", "Screen unlocked")
        self._send_notification_async(event)
    
    def _handle_prepare_for_sleep(self, conn, sender, path, iface, signal, params) -> None:
        """Handle sleep/hibernate preparation"""
        active = params.unpack()[0]
        
        if active:
            # System is about to sleep
            if not self._should_notify("sleep"):
                return
            
            if self.config.get_bool("ENABLE_DEBOUNCE"):
                if not self.debouncer.should_process("sleep"):
                    logging.debug("Sleep event debounced")
                    self._release_delay_lock()
                    return
            
            logging.info("System preparing for sleep")
            
            # Wait for configured delay before sending
            delay = self.config.get_int("PRE_EVENT_DELAY")
            if delay > 0:
                logging.debug(f"Waiting {delay}s before sending notification")
                time.sleep(delay)
            
            event = self._create_event("sleep", f"System going to sleep in {delay}s")
            self._send_notification_async(event)
            
            # Release lock to allow sleep
            self._release_delay_lock()
        else:
            # System is waking up
            if not self._should_notify("wake"):
                return
            
            logging.info("System woke up")
            event = self._create_event("wake", "System resumed from sleep")
            self._send_notification_async(event)
            
            # Re-acquire lock for next sleep
            self._take_delay_lock("sleep:shutdown")
    
    def _handle_prepare_for_shutdown(self, conn, sender, path, iface, signal, params) -> None:
        """Handle shutdown/reboot preparation"""
        active = params.unpack()[0]
        
        if not active:
            return
        
        if not self._should_notify("shutdown"):
            self._release_delay_lock()
            return
        
        if self.config.get_bool("ENABLE_DEBOUNCE"):
            if not self.debouncer.should_process("shutdown"):
                logging.debug("Shutdown event debounced")
                self._release_delay_lock()
                return
        
        logging.info("System preparing for shutdown")
        
        # Wait for configured delay before sending
        delay = self.config.get_int("PRE_EVENT_DELAY")
        if delay > 0:
            logging.debug(f"Waiting {delay}s before sending notification")
            time.sleep(delay)
        
        event = self._create_event("shutdown", f"System shutting down in {delay}s")
        self._send_notification_async(event)
        
        # Release lock to allow shutdown
        self._release_delay_lock()
    
    def _subscribe_to_signals(self) -> None:
        """Subscribe to D-Bus signals"""
        # Get session ID for lock/unlock signals
        session_id = os.environ.get('XDG_SESSION_ID', '').replace('_', '')
        
        # Subscribe to PrepareForSleep
        sub_id = self.bus.signal_subscribe(
            "org.freedesktop.login1",
            "org.freedesktop.login1.Manager",
            "PrepareForSleep",
            "/org/freedesktop/login1",
            None,
            Gio.DBusSignalFlags.NONE,
            self._handle_prepare_for_sleep
        )
        self.subscriptions.append(sub_id)
        
        # Subscribe to PrepareForShutdown
        sub_id = self.bus.signal_subscribe(
            "org.freedesktop.login1",
            "org.freedesktop.login1.Manager",
            "PrepareForShutdown",
            "/org/freedesktop/login1",
            None,
            Gio.DBusSignalFlags.NONE,
            self._handle_prepare_for_shutdown
        )
        self.subscriptions.append(sub_id)
        
        # Subscribe to Lock/Unlock signals if we have a session ID
        if session_id:
            session_path = f"/org/freedesktop/login1/session/{session_id}"
            
            sub_id = self.bus.signal_subscribe(
                "org.freedesktop.login1",
                "org.freedesktop.login1.Session",
                "Lock",
                session_path,
                None,
                Gio.DBusSignalFlags.NONE,
                self._handle_lock
            )
            self.subscriptions.append(sub_id)
            
            sub_id = self.bus.signal_subscribe(
                "org.freedesktop.login1",
                "org.freedesktop.login1.Session",
                "Unlock",
                session_path,
                None,
                Gio.DBusSignalFlags.NONE,
                self._handle_unlock
            )
            self.subscriptions.append(sub_id)
            
            logging.info(f"Monitoring session: {session_id}")
        else:
            logging.warning("XDG_SESSION_ID not set, lock/unlock monitoring unavailable")
    
    def start(self) -> None:
        """Start monitoring system events"""
        logging.info(f"Starting systemd-notifier v{__version__}")
        logging.info(f"Configuration file: {self.config.config_file or 'Not found, using environment/defaults'}")
        
        # Connect to system bus
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        except Exception as e:
            logging.error(f"Failed to connect to D-Bus system bus: {e}")
            sys.exit(1)
        
        # Take initial delay lock
        self._take_delay_lock("sleep:shutdown")
        
        # Subscribe to signals
        self._subscribe_to_signals()
        
        # Start main loop
        logging.info("Monitoring system events...")
        logging.info(f"Pre-event delay: {self.config.get_int('PRE_EVENT_DELAY')}s")
        logging.info(f"Debounce enabled: {self.config.get_bool('ENABLE_DEBOUNCE')}")
        
        try:
            GLib.MainLoop().run()
        except KeyboardInterrupt:
            logging.info("Shutting down...")
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop monitoring and cleanup"""
        logging.info("Stopping systemd-notifier")
        
        # Unsubscribe from signals
        for sub_id in self.subscriptions:
            try:
                self.bus.signal_unsubscribe(sub_id)
            except:
                pass
        
        # Release delay lock
        self._release_delay_lock()


def setup_logging(config: ConfigManager) -> None:
    """Setup logging configuration"""
    log_level = config.get("LOG_LEVEL", "INFO").upper()
    
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    """Main entry point"""
    config = ConfigManager()
    setup_logging(config)
    
    monitor = SystemEventMonitor(config)
    monitor.start()


if __name__ == "__main__":
    main()
