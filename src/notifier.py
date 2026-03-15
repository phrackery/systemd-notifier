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
    # Custom scripts for each event (async execution)
    "CUSTOM_SCRIPT_LOCK": "",
    "CUSTOM_SCRIPT_UNLOCK": "",
    "CUSTOM_SCRIPT_SLEEP": "",
    "CUSTOM_SCRIPT_WAKE": "",
    "CUSTOM_SCRIPT_SHUTDOWN": "",
    # Notification template (HTML supported)
    "NOTIFICATION_TEMPLATE": "",  # Empty = use default format
    # Backend configuration (telegram, discord, or both)
    "BACKEND": "telegram",  # Options: telegram, discord, both
    # Discord webhook configuration
    "DISCORD_WEBHOOK_URL": "",
    "DISCORD_USERNAME": "Systemd Notifier",  # Display name for the bot
    "DISCORD_AVATAR_URL": "",  # Optional: URL to avatar image
    # Network monitoring configuration
    "ENABLE_NETWORK_MONITOR": "false",
    "NOTIFY_ON_CRITICAL_NETWORK_EVENTS": "true",  # Always notify on VPN disconnect, internet lost
    "NOTIFY_ON_ALL_NETWORK_EVENTS": "false",  # If true, use individual toggles below
    "NOTIFY_ON_WIFI_CONNECT": "true",
    "NOTIFY_ON_WIFI_DISCONNECT": "false",
    "NOTIFY_ON_VPN_CONNECT": "false",
    "NOTIFY_ON_VPN_DISCONNECT": "true",
    "NOTIFY_ON_ETH_CONNECT": "false",
    "NOTIFY_ON_ETH_DISCONNECT": "false",
    "NOTIFY_ON_INTERNET_LOST": "true",  # Link state lost
    "NOTIFY_ON_INTERNET_UNREACHABLE": "false",  # Link up but no actual internet
    "NETWORK_DEBOUNCE_SECONDS": "5",
    "NETWORK_IGNORE_INTERFACES": "lo,docker0,veth*",
    "CONNECTIVITY_CHECK_HOST": "1.1.1.1",  # For internet reachability checks
    "CONNECTIVITY_CHECK_INTERVAL": "30",  # Seconds between checks
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
        """Format event information into a rich message with template support"""
        emoji_map = {
            "lock": "🔒",
            "unlock": "🔓",
            "sleep": "💤",
            "wake": "☀️",
            "shutdown": "🔴",
            "hibernate": "❄️",
            # Network events
            "wifi_connected": "📶",
            "wifi_disconnected": "📡",
            "vpn_connected": "🔒",
            "vpn_disconnected": "⚠️",
            "eth_connected": "🔌",
            "eth_disconnected": "🔌",
            "internet_lost": "🔴",
            "internet_unreachable": "🌐",
        }
        
        emoji = emoji_map.get(event.event_type.lower(), "📱")
        
        # Check if custom template is configured
        template = self.config.get("NOTIFICATION_TEMPLATE", "").strip()
        
        if template:
            # Use custom template with variable substitution
            try:
                message = template.format(
                    emoji=emoji,
                    event_type=event.event_type.upper(),
                    hostname=event.hostname,
                    timestamp=event.timestamp,
                    message=event.message,
                )
            except (KeyError, ValueError) as e:
                logging.warning(f"Invalid notification template: {e}. Using default format.")
                # Fall back to default format
                message = self._format_default_message(event, emoji)
        else:
            # Use default format
            message = self._format_default_message(event, emoji)
        
        return message
    
    def _format_default_message(self, event: EventInfo, emoji: str) -> str:
        """Format message using the default template"""
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


class DiscordNotifier:
    """Handles sending notifications to Discord via webhook"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.webhook_url = config.get("DISCORD_WEBHOOK_URL", "")
        self.username = config.get("DISCORD_USERNAME", "Systemd Notifier")
        self.avatar_url = config.get("DISCORD_AVATAR_URL", "")
        self.timeout = config.get_int("NOTIFICATION_TIMEOUT")
    
    def _get_color_for_event(self, event_type: str) -> int:
        """Get Discord embed color for event type"""
        color_map = {
            "lock": 0x3498db,      # Blue
            "unlock": 0x2ecc71,    # Green
            "sleep": 0x9b59b6,     # Purple
            "wake": 0xf1c40f,      # Yellow
            "shutdown": 0xe74c3c,  # Red
            "hibernate": 0x1abc9c, # Teal
            "test": 0x95a5a6,      # Gray
            # Network events
            "wifi_connected": 0x3498db,      # Blue
            "wifi_disconnected": 0xe67e22,   # Orange
            "vpn_connected": 0x2ecc71,       # Green
            "vpn_disconnected": 0xe74c3c,    # Red
            "eth_connected": 0x3498db,       # Blue
            "eth_disconnected": 0xe67e22,    # Orange
            "internet_lost": 0xe74c3c,       # Red
            "internet_unreachable": 0xf39c12, # Yellow
        }
        return color_map.get(event_type.lower(), 0x3498db)

    def _get_emoji_for_event(self, event_type: str) -> str:
        """Get emoji for event type"""
        emoji_map = {
            "lock": "🔒",
            "unlock": "🔓",
            "sleep": "💤",
            "wake": "☀️",
            "shutdown": "🔴",
            "hibernate": "❄️",
            "test": "🧪",
            # Network events
            "wifi_connected": "📶",
            "wifi_disconnected": "📡",
            "vpn_connected": "🔒",
            "vpn_disconnected": "⚠️",
            "eth_connected": "🔌",
            "eth_disconnected": "🔌",
            "internet_lost": "🔴",
            "internet_unreachable": "🌐",
        }
        return emoji_map.get(event_type.lower(), "📱")
    
    def _format_message(self, event: EventInfo) -> str:
        """Format event information for Discord"""
        emoji = self._get_emoji_for_event(event.event_type)
        
        message = f"{emoji} **{event.event_type.upper()}** on `{event.hostname}`"
        
        if event.message:
            message += f"\n> {event.message}"
        
        return message
    
    def send_notification(self, event: EventInfo) -> bool:
        """Send notification to Discord via webhook"""
        if not self.webhook_url:
            logging.error("Discord webhook URL not configured")
            return False
        
        # Build Discord embed
        color = self._get_color_for_event(event.event_type)
        emoji = self._get_emoji_for_event(event.event_type)
        
        embed = {
            "title": f"{emoji} System Event: {event.event_type.upper()}",
            "color": color,
            "fields": [
                {
                    "name": "Hostname",
                    "value": f"`{event.hostname}`",
                    "inline": True
                },
                {
                    "name": "Time",
                    "value": f"`{event.timestamp}`",
                    "inline": True
                }
            ],
            "footer": {
                "text": "systemd-notifier"
            },
            "timestamp": datetime.now().isoformat()
        }
        
        if event.message:
            embed["fields"].append({
                "name": "Message",
                "value": event.message,
                "inline": False
            })
        
        # Build payload
        payload = {
            "username": self.username,
            "embeds": [embed]
        }
        
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url
        
        # Send via curl
        try:
            import json
            
            json_payload = json.dumps(payload)
            
            cmd = [
                "curl", "-s", "-X", "POST",
                "-H", "Content-Type: application/json",
                "-d", json_payload,
                self.webhook_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            # Discord returns empty string on success
            if result.returncode == 0:
                if result.stdout.strip() == "" or "rate limit" not in result.stdout.lower():
                    logging.info("Discord notification sent successfully")
                    return True
                else:
                    logging.warning(f"Discord rate limit or error: {result.stdout}")
                    return False
            else:
                logging.error(f"Discord webhook failed: {result.stderr}")
                return False
                
        except Exception as e:
            logging.error(f"Failed to send Discord notification: {e}")
            return False


class MultiNotifier:
    """Wrapper to send notifications to multiple backends"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.notifiers = []
        self._init_notifiers()
    
    def _init_notifiers(self):
        """Initialize notifiers based on BACKEND configuration"""
        backend = self.config.get("BACKEND", "telegram").lower()
        
        if backend in ("telegram", "both"):
            if self.config.get("TELEGRAM_BOT_TOKEN") and self.config.get("TELEGRAM_CHAT_ID"):
                self.notifiers.append(TelegramNotifier(self.config))
                logging.info("Telegram backend enabled")
            else:
                logging.warning("Telegram backend selected but not configured")
        
        if backend in ("discord", "both"):
            if self.config.get("DISCORD_WEBHOOK_URL"):
                self.notifiers.append(DiscordNotifier(self.config))
                logging.info("Discord backend enabled")
            else:
                logging.warning("Discord backend selected but not configured")
        
        if not self.notifiers:
            logging.error("No notification backends configured!")
            # Default to Telegram for backward compatibility
            self.notifiers.append(TelegramNotifier(self.config))
    
    def send_notification(self, event: EventInfo) -> bool:
        """Send notification to all configured backends"""
        results = []
        for notifier in self.notifiers:
            try:
                result = notifier.send_notification(event)
                results.append(result)
            except Exception as e:
                logging.error(f"Failed to send notification via {type(notifier).__name__}: {e}")
                results.append(False)
        
        # Return True if at least one succeeded
        return any(results)


class DebouncedEventManager:
    """Manages debounced events with cancellation support"""
    
    def __init__(self):
        self.pending_events: Dict[str, int] = {}
    
    def schedule(self, event_id: str, callback: Callable, delay_seconds: int = 5) -> None:
        """Schedule an event to fire after delay, canceling any existing timer"""
        # Cancel existing timer
        if event_id in self.pending_events:
            GLib.source_remove(self.pending_events[event_id])
        
        # Schedule new timer
        def on_timeout():
            callback()
            self.pending_events.pop(event_id, None)
            return False  # Don't repeat
        
        timer_id = GLib.timeout_add_seconds(delay_seconds, on_timeout)
        self.pending_events[event_id] = timer_id
    
    def cancel(self, event_id: str) -> None:
        """Cancel a pending event"""
        if event_id in self.pending_events:
            GLib.source_remove(self.pending_events[event_id])
            self.pending_events.pop(event_id, None)
    
    def cancel_all(self) -> None:
        """Cancel all pending events"""
        for timer_id in self.pending_events.values():
            GLib.source_remove(timer_id)
        self.pending_events.clear()


class InternetConnectivityChecker:
    """Periodically checks if internet is actually reachable"""
    
    def __init__(self, config: ConfigManager, notifier: MultiNotifier):
        self.config = config
        self.notifier = notifier
        self.target_host = config.get("CONNECTIVITY_CHECK_HOST", "1.1.1.1")
        self.check_interval = config.get_int("CONNECTIVITY_CHECK_INTERVAL", 30)
        self.timer_id: Optional[int] = None
        self.last_state: Optional[bool] = None  # True = reachable, False = unreachable
        self.hostname = socket.gethostname()
    
    def start(self) -> None:
        """Start periodic connectivity checks"""
        if not self.config.get_bool("NOTIFY_ON_INTERNET_UNREACHABLE"):
            return
        
        logging.info(f"Starting internet connectivity checks (target: {self.target_host})")
        self._schedule_check()
    
    def stop(self) -> None:
        """Stop connectivity checks"""
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None
    
    def _schedule_check(self) -> None:
        """Schedule next connectivity check"""
        self.timer_id = GLib.timeout_add_seconds(self.check_interval, self._check_and_schedule)
    
    def _check_and_schedule(self) -> bool:
        """Check connectivity and reschedule"""
        self._check_connectivity()
        return True  # Continue scheduling
    
    def _check_connectivity(self) -> None:
        """Check if internet is reachable via ping"""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", self.target_host],
                capture_output=True,
                timeout=5
            )
            is_reachable = result.returncode == 0
            
            # Detect state change
            if self.last_state is not None and self.last_state != is_reachable:
                if not is_reachable:
                    # Internet became unreachable
                    self._notify_unreachable()
            
            self.last_state = is_reachable
            
        except Exception as e:
            logging.debug(f"Connectivity check failed: {e}")
            if self.last_state:
                self._notify_unreachable()
            self.last_state = False
    
    def _notify_unreachable(self) -> None:
        """Send notification that internet is unreachable"""
        event = EventInfo(
            event_type="internet_unreachable",
            hostname=self.hostname,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message=f"Internet is unreachable (cannot reach {self.target_host})"
        )
        self.notifier.send_notification(event)


class NetworkMonitor:
    """Monitors network connectivity via NetworkManager D-Bus"""
    
    def __init__(self, config: ConfigManager, notifier: MultiNotifier):
        self.config = config
        self.notifier = notifier
        self.hostname = socket.gethostname()
        self.debounce_manager = DebouncedEventManager()
        self.connectivity_checker: Optional[InternetConnectivityChecker] = None
        
        # Track active connections
        self.active_connections: Dict[str, Dict] = {}
        self.last_network_state: Optional[int] = None
        
        # D-Bus connection
        self.bus: Optional[Gio.DBusConnection] = None
        self.subscriptions: list[int] = []
    
    def start(self) -> None:
        """Start monitoring network events"""
        if not self.config.get_bool("ENABLE_NETWORK_MONITOR"):
            logging.info("Network monitoring disabled")
            return
        
        logging.info("Starting network monitoring...")
        
        # Connect to system bus
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        except Exception as e:
            logging.error(f"Failed to connect to D-Bus for network monitoring: {e}")
            return
        
        # Check if NetworkManager is available
        if not self._check_network_manager():
            logging.warning("NetworkManager not available, network monitoring disabled")
            return
        
        # Subscribe to signals
        self._subscribe_to_signals()
        
        # Start internet connectivity checker if enabled
        if self.config.get_bool("NOTIFY_ON_INTERNET_UNREACHABLE"):
            self.connectivity_checker = InternetConnectivityChecker(self.config, self.notifier)
            self.connectivity_checker.start()
        
        logging.info("Network monitoring active")
    
    def stop(self) -> None:
        """Stop monitoring and cleanup"""
        logging.info("Stopping network monitoring...")
        
        # Cancel all debounced events
        self.debounce_manager.cancel_all()
        
        # Stop connectivity checker
        if self.connectivity_checker:
            self.connectivity_checker.stop()
        
        # Unsubscribe from signals
        for sub_id in self.subscriptions:
            try:
                self.bus.signal_unsubscribe(sub_id)
            except:
                pass
        
        self.subscriptions.clear()
    
    def _check_network_manager(self) -> bool:
        """Check if NetworkManager service is available"""
        try:
            result = self.bus.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "NameHasOwner",
                GLib.Variant("(s)", ("org.freedesktop.NetworkManager",)),
                GLib.VariantType("(b)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            return result.unpack()[0]
        except Exception as e:
            logging.warning(f"Failed to check NetworkManager availability: {e}")
            return False
    
    def _subscribe_to_signals(self) -> None:
        """Subscribe to NetworkManager D-Bus signals"""
        # Subscribe to ActiveConnection StateChanged
        sub_id = self.bus.signal_subscribe(
            "org.freedesktop.NetworkManager",
            "org.freedesktop.NetworkManager.Connection.Active",
            "StateChanged",
            None,  # All paths
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_connection_state_changed
        )
        self.subscriptions.append(sub_id)
        logging.debug("Subscribed to ActiveConnection StateChanged")
        
        # Subscribe to NetworkManager StateChanged (for internet connectivity)
        sub_id = self.bus.signal_subscribe(
            "org.freedesktop.NetworkManager",
            "org.freedesktop.NetworkManager",
            "StateChanged",
            "/org/freedesktop/NetworkManager",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_network_state_changed
        )
        self.subscriptions.append(sub_id)
        logging.debug("Subscribed to NetworkManager StateChanged")
    
    def _on_connection_state_changed(self, conn, sender, path, iface, signal, params) -> None:
        """Handle connection state changes"""
        try:
            new_state, reason = params.unpack()
            # States: 0=Unknown, 1=Activating, 2=Activated, 3=Deactivating, 4=Deactivated
            
            if new_state == 2:  # ACTIVATED
                self._handle_connection_activated(path)
            elif new_state == 4:  # DEACTIVATED
                self._handle_connection_deactivated(path)
                
        except Exception as e:
            logging.error(f"Error handling connection state change: {e}")
    
    def _handle_connection_activated(self, path: str) -> None:
        """Handle connection activated"""
        try:
            # Get connection properties
            props = self._get_connection_properties(path)
            if not props:
                return
            
            conn_id = props.get("Id", "Unknown")
            conn_type = props.get("Type", "unknown")
            is_vpn = props.get("Vpn", False)
            
            # Store connection info
            self.active_connections[path] = {
                "id": conn_id,
                "type": conn_type,
                "vpn": is_vpn,
                "activated_at": time.time()
            }
            
            # Determine event type
            if is_vpn:
                event_type = "vpn_connected"
                event_name = "VPN Connected"
            elif conn_type == "802-11-wireless":
                event_type = "wifi_connected"
                event_name = "WiFi Connected"
            elif conn_type == "802-3-ethernet":
                event_type = "eth_connected"
                event_name = "Ethernet Connected"
            else:
                return  # Unknown type, skip
            
            # Check if we should notify
            if not self._should_notify(event_type, critical=False):
                return
            
            # Cancel any pending disconnect notification
            disconnect_event_id = f"disconnect_{path}"
            self.debounce_manager.cancel(disconnect_event_id)
            
            # Send notification (connect events are not debounced)
            event = EventInfo(
                event_type=event_type,
                hostname=self.hostname,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                message=f"{event_name}"
            )
            self.notifier.send_notification(event)
            
        except Exception as e:
            logging.error(f"Error handling connection activation: {e}")
    
    def _handle_connection_deactivated(self, path: str) -> None:
        """Handle connection deactivated"""
        try:
            # Get stored connection info
            conn_info = self.active_connections.pop(path, None)
            if not conn_info:
                return
            
            conn_id = conn_info.get("id", "Unknown")
            conn_type = conn_info.get("type", "unknown")
            is_vpn = conn_info.get("vpn", False)
            
            # Determine event type
            if is_vpn:
                event_type = "vpn_disconnected"
                event_name = "VPN Disconnected"
                is_critical = True  # VPN disconnect is always critical
            elif conn_type == "802-11-wireless":
                event_type = "wifi_disconnected"
                event_name = "WiFi Disconnected"
                is_critical = False
            elif conn_type == "802-3-ethernet":
                event_type = "eth_disconnected"
                event_name = "Ethernet Disconnected"
                is_critical = False
            else:
                return
            
            # Check if we should notify
            if not self._should_notify(event_type, critical=is_critical):
                return
            
            # Create notification event
            event = EventInfo(
                event_type=event_type,
                hostname=self.hostname,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                message=f"{event_name}"
            )
            
            if is_critical:
                # Critical events (VPN disconnect) - notify immediately
                self.notifier.send_notification(event)
            else:
                # Non-critical events - debounce
                disconnect_event_id = f"disconnect_{path}"
                self.debounce_manager.schedule(
                    disconnect_event_id,
                    lambda: self.notifier.send_notification(event),
                    delay_seconds=self.config.get_int("NETWORK_DEBOUNCE_SECONDS", 5)
                )
            
        except Exception as e:
            logging.error(f"Error handling connection deactivation: {e}")
    
    def _on_network_state_changed(self, conn, sender, path, iface, signal, params) -> None:
        """Handle overall network state changes"""
        try:
            new_state = params.unpack()[0]
            # States: 0=Unknown, 10=Asleep, 20=Disconnected, 40=Connecting, 60=ConnectedLocal, 70=ConnectedGlobal
            
            # Check for internet connectivity loss
            if self.last_network_state is not None:
                if self.last_network_state >= 60 and new_state == 20:
                    # Transition from connected to disconnected
                    if self._should_notify("internet_lost", critical=True):
                        event = EventInfo(
                            event_type="internet_lost",
                            hostname=self.hostname,
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            message="Internet connection lost (link state)"
                        )
                        self.notifier.send_notification(event)
            
            self.last_network_state = new_state
            
        except Exception as e:
            logging.error(f"Error handling network state change: {e}")
    
    def _get_connection_properties(self, path: str) -> Optional[Dict]:
        """Get properties of an active connection"""
        try:
            result = self.bus.call_sync(
                "org.freedesktop.NetworkManager",
                path,
                "org.freedesktop.DBus.Properties",
                "GetAll",
                GLib.Variant("(s)", ("org.freedesktop.NetworkManager.Connection.Active",)),
                GLib.VariantType("(a{sv})"),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            
            props = result.unpack()[0]
            return {
                "Id": props.get("Id", "Unknown"),
                "Type": props.get("Type", "unknown"),
                "Vpn": props.get("Vpn", False)
            }
        except Exception as e:
            logging.warning(f"Failed to get connection properties for {path}: {e}")
            return None
    
    def _should_notify(self, event_type: str, critical: bool = False) -> bool:
        """Check if we should send notification for this event type"""
        # VPN disconnect is ALWAYS notified (security critical)
        if event_type == "vpn_disconnected":
            return True
        
        # Critical events follow NOTIFY_ON_CRITICAL_NETWORK_EVENTS
        if critical:
            return self.config.get_bool("NOTIFY_ON_CRITICAL_NETWORK_EVENTS")
        
        # Check if all events mode is enabled
        if not self.config.get_bool("NOTIFY_ON_ALL_NETWORK_EVENTS"):
            return False
        
        # Check individual toggle
        config_map = {
            "wifi_connected": "NOTIFY_ON_WIFI_CONNECT",
            "wifi_disconnected": "NOTIFY_ON_WIFI_DISCONNECT",
            "vpn_connected": "NOTIFY_ON_VPN_CONNECT",
            "vpn_disconnected": "NOTIFY_ON_VPN_DISCONNECT",
            "eth_connected": "NOTIFY_ON_ETH_CONNECT",
            "eth_disconnected": "NOTIFY_ON_ETH_DISCONNECT",
            "internet_lost": "NOTIFY_ON_INTERNET_LOST",
            "internet_unreachable": "NOTIFY_ON_INTERNET_UNREACHABLE",
        }
        
        config_key = config_map.get(event_type)
        if config_key:
            return self.config.get_bool(config_key)
        
        return False


class SystemEventMonitor:
    """Monitors system events via D-Bus"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.notifier = MultiNotifier(config)
        self.debouncer = Debouncer(config.get_int("DEBOUNCE_SECONDS"))
        self.bus: Optional[Gio.DBusConnection] = None
        self.subscriptions: list[int] = []
        self.inhibit_fd: Optional[int] = None
        self.hostname = socket.gethostname()

        # Event tracking
        self.pending_notifications: Dict[str, bool] = {}

        # Network monitoring
        self.network_monitor: Optional[NetworkMonitor] = None

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
    
    def _run_custom_script(self, event: EventInfo) -> None:
        """Execute custom script for an event asynchronously"""
        import threading
        
        script_map = {
            "lock": "CUSTOM_SCRIPT_LOCK",
            "unlock": "CUSTOM_SCRIPT_UNLOCK",
            "sleep": "CUSTOM_SCRIPT_SLEEP",
            "wake": "CUSTOM_SCRIPT_WAKE",
            "shutdown": "CUSTOM_SCRIPT_SHUTDOWN",
        }
        
        config_key = script_map.get(event.event_type.lower())
        if not config_key:
            return
        
        script_path = self.config.get(config_key, "")
        if not script_path:
            return
        
        if not os.path.exists(script_path):
            logging.warning(f"Custom script not found: {script_path}")
            return
        
        def run_script():
            try:
                # Set environment variables for the script
                env = os.environ.copy()
                env["EVENT_TYPE"] = event.event_type
                env["EVENT_HOSTNAME"] = event.hostname
                env["EVENT_TIMESTAMP"] = event.timestamp
                env["EVENT_MESSAGE"] = event.message
                
                result = subprocess.run(
                    [script_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env
                )
                
                if result.returncode == 0:
                    logging.debug(f"Custom script executed successfully: {script_path}")
                else:
                    logging.warning(f"Custom script failed (exit {result.returncode}): {script_path}")
                    if result.stderr:
                        logging.warning(f"Script stderr: {result.stderr}")
                        
            except subprocess.TimeoutExpired:
                logging.error(f"Custom script timed out after 30s: {script_path}")
            except Exception as e:
                logging.error(f"Failed to execute custom script {script_path}: {e}")
        
        # Run asynchronously (non-blocking)
        thread = threading.Thread(target=run_script)
        thread.daemon = True
        thread.start()
        logging.info(f"Executing custom script for {event.event_type}: {script_path}")
    
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
    
    def _get_graphical_session_id(self) -> Optional[str]:
        """Find the actual graphical session ID by querying logind.
        
        The systemd user service runs in its own session (e.g., session 4), but
        lock/unlock events are sent to the graphical session (e.g., session 3).
        We need to find the session that has a seat assigned (seat0).
        """
        try:
            # Call ListSessions to get all sessions for this user
            result = self.bus.call_sync(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager",
                "ListSessions",
                None,
                GLib.VariantType("(a(susso))"),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            
            sessions = result.unpack()[0]
            current_uid = os.getuid()
            
            for session in sessions:
                session_id, uid, username, seat, path = session
                uid = int(uid)
                
                # Only consider sessions for current user
                if uid != current_uid:
                    continue
                
                # Find the session with a seat (graphical session)
                # The seat field is non-empty for graphical sessions
                if seat:
                    logging.info(f"Found graphical session: {session_id} on seat {seat}")
                    return session_id
            
            # Fallback: use XDG_SESSION_ID if available
            env_session = os.environ.get('XDG_SESSION_ID', '')
            if env_session:
                logging.warning(f"No graphical session found, falling back to XDG_SESSION_ID={env_session}")
                return env_session
                
            logging.error("No graphical session found and XDG_SESSION_ID not set")
            return None
            
        except Exception as e:
            logging.error(f"Failed to query sessions from logind: {e}")
            # Fallback to environment variable
            return os.environ.get('XDG_SESSION_ID', '')
    
    def _subscribe_to_signals(self) -> None:
        """Subscribe to D-Bus signals"""
        # Get the actual graphical session ID for lock/unlock signals
        # IMPORTANT: Do NOT strip underscores! Session IDs like "_32" need the underscore
        session_id = self._get_graphical_session_id() or ''
        
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
            # Query logind to get the actual session object path
            # Session ID (e.g., "2") maps to different object path (e.g., "/org/freedesktop/login1/session/_32")
            try:
                result = self.bus.call_sync(
                    "org.freedesktop.login1",
                    "/org/freedesktop/login1",
                    "org.freedesktop.login1.Manager",
                    "GetSession",
                    GLib.Variant("(s)", (session_id,)),
                    GLib.VariantType("(o)"),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None
                )
                session_path = result.unpack()[0]
                logging.info(f"Session {session_id} -> D-Bus path: {session_path}")
            except Exception as e:
                # Fallback to default path construction
                session_path = f"/org/freedesktop/login1/session/{session_id}"
                logging.warning(f"Could not query session path from logind: {e}. Using fallback: {session_path}")
            
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

        # Initialize and start network monitor
        if self.config.get_bool("ENABLE_NETWORK_MONITOR"):
            self.network_monitor = NetworkMonitor(self.config, self.notifier)
            self.network_monitor.start()

        # Take initial delay lock
        self._take_delay_lock("sleep:shutdown")

        # Subscribe to signals
        self._subscribe_to_signals()

        # Start main loop
        logging.info("Monitoring system events...")
        logging.info(f"Pre-event delay: {self.config.get_int('PRE_EVENT_DELAY')}s")
        logging.info(f"Debounce enabled: {self.config.get_bool('ENABLE_DEBOUNCE')}")
        if self.config.get_bool("ENABLE_NETWORK_MONITOR"):
            logging.info("Network monitoring enabled")

        try:
            GLib.MainLoop().run()
        except KeyboardInterrupt:
            logging.info("Shutting down...")
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop monitoring and cleanup"""
        logging.info("Stopping systemd-notifier")

        # Stop network monitor
        if self.network_monitor:
            self.network_monitor.stop()

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


def send_test_notification(config: ConfigManager) -> bool:
    """Send a test notification to verify backend configuration"""
    from datetime import datetime
    
    print("📱 Systemd Notifier - Test Mode")
    print("=" * 50)
    
    backend = config.get("BACKEND", "telegram").lower()
    print(f"Backend: {backend}")
    print(f"Configuration file: {config.config_file or 'Environment variables'}")
    print()
    
    # Create test event
    test_event = EventInfo(
        event_type="test",
        hostname=socket.gethostname(),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message="This is a test notification from systemd-notifier!"
    )
    
    results = []
    
    # Test Telegram if configured
    if backend in ("telegram", "both"):
        print("🔔 Testing Telegram backend...")
        if config.get("TELEGRAM_BOT_TOKEN") and config.get("TELEGRAM_CHAT_ID"):
            print(f"  Bot token: {'*' * 10}{config.get('TELEGRAM_BOT_TOKEN')[-5:]}")
            print(f"  Chat ID: {config.get('TELEGRAM_CHAT_ID')}")
            
            telegram_notifier = TelegramNotifier(config)
            telegram_success = telegram_notifier.send_notification(test_event)
            
            if telegram_success:
                print("  ✅ Telegram test notification sent successfully!")
                results.append(True)
            else:
                print("  ❌ Telegram test failed")
                results.append(False)
        else:
            print("  ⚠️  Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
            results.append(False)
        print()
    
    # Test Discord if configured
    if backend in ("discord", "both"):
        print("💬 Testing Discord backend...")
        if config.get("DISCORD_WEBHOOK_URL"):
            webhook_url = config.get("DISCORD_WEBHOOK_URL")
            # Mask webhook URL for display
            if "/" in webhook_url:
                parts = webhook_url.rsplit("/", 2)
                masked_url = f"{parts[0]}/.../{parts[-1][:10]}..."
                print(f"  Webhook URL: {masked_url}")
            
            discord_notifier = DiscordNotifier(config)
            discord_success = discord_notifier.send_notification(test_event)
            
            if discord_success:
                print("  ✅ Discord test notification sent successfully!")
                results.append(True)
            else:
                print("  ❌ Discord test failed")
                results.append(False)
        else:
            print("  ⚠️  Discord not configured (set DISCORD_WEBHOOK_URL)")
            results.append(False)
        print()
    
    # Summary
    print("=" * 50)
    if any(results):
        print("✅ At least one backend is working correctly!")
        print("\nTroubleshooting for failed backends:")
        if backend in ("telegram", "both") and not results[0] if backend == "telegram" else results[1] if len(results) > 1 else False:
            print("  Telegram:")
            print("    1. Verify your bot token is correct")
            print("    2. Make sure you've started a chat with your bot")
            print("    3. Check your chat ID is correct")
        if backend in ("discord", "both") and not results[-1]:
            print("  Discord:")
            print("    1. Verify your webhook URL is correct")
            print("    2. Make sure the webhook hasn't been deleted")
            print("    3. Check the Discord channel permissions")
        return True
    else:
        print("❌ All backends failed or not configured")
        print("\nConfiguration issues:")
        if backend in ("telegram", "both"):
            print("  - TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set for Telegram")
        if backend in ("discord", "both"):
            print("  - DISCORD_WEBHOOK_URL must be set for Discord")
        return False


def show_status(config: ConfigManager) -> None:
    """Show service status and configuration"""
    import subprocess
    
    print("📊 Systemd Notifier Status")
    print("=" * 50)
    
    # Configuration
    print("\n📋 Configuration:")
    print(f"  Config file: {config.config_file or 'Not found'}")
    print(f"  Log level: {config.get('LOG_LEVEL', 'INFO')}")
    print(f"  Pre-event delay: {config.get_int('PRE_EVENT_DELAY')}s")
    
    # Event notifications
    print("\n🔔 Event Notifications:")
    print(f"  Lock: {'✅' if config.get_bool('NOTIFY_ON_LOCK') else '❌'}")
    print(f"  Unlock: {'✅' if config.get_bool('NOTIFY_ON_UNLOCK') else '❌'}")
    print(f"  Sleep: {'✅' if config.get_bool('NOTIFY_ON_SLEEP') else '❌'}")
    print(f"  Wake: {'✅' if config.get_bool('NOTIFY_ON_WAKE') else '❌'}")
    print(f"  Shutdown: {'✅' if config.get_bool('NOTIFY_ON_SHUTDOWN') else '❌'}")
    
    # Custom scripts
    print("\n📜 Custom Scripts:")
    scripts = {
        "Lock": config.get("CUSTOM_SCRIPT_LOCK", ""),
        "Unlock": config.get("CUSTOM_SCRIPT_UNLOCK", ""),
        "Sleep": config.get("CUSTOM_SCRIPT_SLEEP", ""),
        "Wake": config.get("CUSTOM_SCRIPT_WAKE", ""),
        "Shutdown": config.get("CUSTOM_SCRIPT_SHUTDOWN", ""),
    }
    has_scripts = False
    for event, script in scripts.items():
        if script:
            print(f"  {event}: {script}")
            has_scripts = True
    if not has_scripts:
        print("  None configured")
    
    # Template
    template = config.get("NOTIFICATION_TEMPLATE", "").strip()
    if template:
        print("\n📝 Custom Template: Yes")
    else:
        print("\n📝 Custom Template: No (using default)")
    
    # Service status
    print("\n🔧 Service Status:")
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "system-notifier"],
            capture_output=True,
            text=True
        )
        is_active = result.returncode == 0
        status = "✅ Running" if is_active else "❌ Not running"
        print(f"  Status: {status}")
        
        if is_active:
            # Get service info
            result = subprocess.run(
                ["systemctl", "--user", "status", "system-notifier", "--no-pager"],
                capture_output=True,
                text=True
            )
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Active:' in line:
                    print(f"  {line.strip()}")
                    break
    except Exception as e:
        print(f"  Error checking status: {e}")
    
    # Backend configuration
    backend = config.get("BACKEND", "telegram").lower()
    print(f"\n🔌 Backend: {backend}")
    
    # Telegram config check
    if backend in ("telegram", "both"):
        print("\n📱 Telegram Configuration:")
        if config.get("TELEGRAM_BOT_TOKEN"):
            token_preview = '*' * 10 + config.get("TELEGRAM_BOT_TOKEN")[-5:]
            print(f"  Bot Token: {token_preview}")
        else:
            print("  Bot Token: ❌ Not set")
        
        if config.get("TELEGRAM_CHAT_ID"):
            print(f"  Chat ID: {config.get('TELEGRAM_CHAT_ID')}")
        else:
            print("  Chat ID: ❌ Not set")
    
    # Discord config check
    if backend in ("discord", "both"):
        print("\n💬 Discord Configuration:")
        if config.get("DISCORD_WEBHOOK_URL"):
            webhook_url = config.get("DISCORD_WEBHOOK_URL")
            # Mask webhook URL for display
            if "/" in webhook_url:
                parts = webhook_url.rsplit("/", 2)
                masked_url = f"{parts[0]}/.../{parts[-1][:10]}..."
                print(f"  Webhook URL: {masked_url}")
        else:
            print("  Webhook URL: ❌ Not set")
        
        print(f"  Username: {config.get('DISCORD_USERNAME', 'Systemd Notifier')}")
        
        if config.get("DISCORD_AVATAR_URL"):
            print(f"  Avatar URL: Set")
        else:
            print(f"  Avatar URL: Using default")
    
    # Network monitoring
    print("\n🌐 Network Monitoring:")
    if config.get_bool("ENABLE_NETWORK_MONITOR"):
        print(f"  Status: ✅ Enabled")
        print(f"  Mode: {'All Events' if config.get_bool('NOTIFY_ON_ALL_NETWORK_EVENTS') else 'Critical Only'}")
        print(f"  Debounce: {config.get_int('NETWORK_DEBOUNCE_SECONDS')}s")
        
        if config.get_bool("NOTIFY_ON_ALL_NETWORK_EVENTS"):
            print("\n  Event Toggles:")
            print(f"    WiFi Connect: {'✅' if config.get_bool('NOTIFY_ON_WIFI_CONNECT') else '❌'}")
            print(f"    WiFi Disconnect: {'✅' if config.get_bool('NOTIFY_ON_WIFI_DISCONNECT') else '❌'}")
            print(f"    VPN Connect: {'✅' if config.get_bool('NOTIFY_ON_VPN_CONNECT') else '❌'}")
            print(f"    VPN Disconnect: {'✅' if config.get_bool('NOTIFY_ON_VPN_DISCONNECT') else '❌'} (Always)")
            print(f"    Ethernet Connect: {'✅' if config.get_bool('NOTIFY_ON_ETH_CONNECT') else '❌'}")
            print(f"    Ethernet Disconnect: {'✅' if config.get_bool('NOTIFY_ON_ETH_DISCONNECT') else '❌'}")
            print(f"    Internet Lost: {'✅' if config.get_bool('NOTIFY_ON_INTERNET_LOST') else '❌'}")
            print(f"    Internet Unreachable: {'✅' if config.get_bool('NOTIFY_ON_INTERNET_UNREACHABLE') else '❌'}")
    else:
        print(f"  Status: ❌ Disabled")
        print(f"  Enable with: ENABLE_NETWORK_MONITOR=true")
    
    print("\n" + "=" * 50)
    print("Run with --test to send a test notification")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="systemd-notifier - Send Telegram notifications for system events",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    Start the notifier daemon
  %(prog)s --test             Send a test notification
  %(prog)s --status           Show configuration and service status
        """
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a test notification and exit"
    )
    
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show configuration and service status"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = ConfigManager()
    setup_logging(config)
    
    if args.test:
        success = send_test_notification(config)
        sys.exit(0 if success else 1)
    
    elif args.status:
        show_status(config)
        sys.exit(0)
    
    else:
        # Normal operation - start the monitor
        monitor = SystemEventMonitor(config)
        monitor.start()


if __name__ == "__main__":
    main()
