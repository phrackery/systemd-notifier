# Network Events Feature - Implementation Document

**Status:** Ready for Implementation  
**Priority:** High  
**Estimated Lines of Code:** ~400-500 lines  
**Estimated Time:** 2-3 hours  

---

## Overview

Implement network connectivity monitoring using NetworkManager D-Bus signals. Monitor WiFi, VPN, Ethernet connections and internet connectivity. Support both critical events (always notify) and optional events with 5-second debounce.

---

## User Requirements (DO NOT CHANGE)

1. ✅ All event types supported, with option for critical-only mode
2. ✅ VPN disconnect ALWAYS notifies (security critical, bypasses all settings)
3. ✅ Internet connectivity - BOTH link state AND actual reachability
4. ✅ Privacy: NO SSID in notifications
5. ✅ 5-second debounce on all non-critical events
6. ✅ Configuration: Critical mode vs all-events mode

---

## Files to Modify

### 1. `/home/phrackery/Desktop/webprojects-opencode/systemd-notifier/src/notifier.py`
**Primary implementation file**

Add these new classes and modify existing ones:

#### Step 1: Add Configuration Defaults (around line 37)

Add to `DEFAULT_CONFIG` dictionary:

```python
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
```

#### Step 2: Create Debounce Utility Class (after TelegramNotifier class)

```python
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
```

#### Step 3: Create InternetConnectivityChecker Class

```python
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
```

#### Step 4: Create NetworkMonitor Class (Main Implementation)

```python
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
            return self.config.get_bool("NOTIFY_ON_CRITICAL_NETWORK_EVENTS", True)
        
        # Check if all events mode is enabled
        if not self.config.get_bool("NOTIFY_ON_ALL_NETWORK_EVENTS", False):
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
            return self.config.get_bool(config_key, False)
        
        return False
```

#### Step 5: Integrate NetworkMonitor into SystemEventMonitor

Modify `SystemEventMonitor.__init__()`:

```python
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
```

Modify `SystemEventMonitor.start()`:

```python
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
```

Modify `SystemEventMonitor.stop()`:

```python
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
```

#### Step 6: Update TelegramNotifier and DiscordNotifier for new event types

Add emoji mappings for network events in both notifiers:

**In TelegramNotifier._format_message() and DiscordNotifier._format_message():**

Add to emoji_map:
```python
# Network events
"wifi_connected": "📶",
"wifi_disconnected": "📡",
"vpn_connected": "🔒",
"vpn_disconnected": "⚠️",
"eth_connected": "🔌",
"eth_disconnected": "🔌",
"internet_lost": "🔴",
"internet_unreachable": "🌐",
```

---

### 2. `/home/phrackery/Desktop/webprojects-opencode/systemd-notifier/config/example.env`

Add the following section at the end of the file:

```bash
# =============================================================================
# NETWORK MONITORING
# =============================================================================
# Monitor network connectivity events (WiFi, VPN, Ethernet, Internet)

# Enable network monitoring
ENABLE_NETWORK_MONITOR=false

# Event mode selection:
# - NOTIFY_ON_CRITICAL_NETWORK_EVENTS=true: Only VPN disconnect and Internet loss
# - NOTIFY_ON_ALL_NETWORK_EVENTS=true: Use individual toggles below
NOTIFY_ON_CRITICAL_NETWORK_EVENTS=true
NOTIFY_ON_ALL_NETWORK_EVENTS=false

# Individual event toggles (only used if NOTIFY_ON_ALL_NETWORK_EVENTS=true)
# WiFi events
NOTIFY_ON_WIFI_CONNECT=true
NOTIFY_ON_WIFI_DISCONNECT=false

# VPN events
NOTIFY_ON_VPN_CONNECT=false
NOTIFY_ON_VPN_DISCONNECT=true  # Always notifies (security critical)

# Ethernet events  
NOTIFY_ON_ETH_CONNECT=false
NOTIFY_ON_ETH_DISCONNECT=false

# Internet connectivity
NOTIFY_ON_INTERNET_LOST=true       # Link state lost (cable unplugged, WiFi disconnected)
NOTIFY_ON_INTERNET_UNREACHABLE=false  # Link up but cannot reach internet (requires ping)

# Network settings
NETWORK_DEBOUNCE_SECONDS=5         # Seconds to wait before notifying on disconnect
NETWORK_IGNORE_INTERFACES=lo,docker0,veth*  # Interfaces to ignore

# Internet reachability check settings (only used if NOTIFY_ON_INTERNET_UNREACHABLE=true)
CONNECTIVITY_CHECK_HOST=1.1.1.1    # Host to ping for reachability check
CONNECTIVITY_CHECK_INTERVAL=30     # Seconds between checks
```

---

### 3. `/home/phrackery/Desktop/webprojects-opencode/systemd-notifier/ROADMAP.md`

Update the status:

```markdown
## 🚧 Planned Features

### High Priority

#### ~~1. Discord Notification Backend~~ ✅ COMPLETED

#### 2. Network Events Monitoring 🔄 IN PROGRESS
**Status:** Implementation ready, needs coding  
**Priority:** High  
**Assigned:** Next available developer  

**Description:** Monitor network connectivity via NetworkManager D-Bus
- WiFi connect/disconnect (no SSID for privacy)
- VPN connect/disconnect (VPN disconnect always notifies for security)
- Ethernet connect/disconnect
- Internet connectivity (link state + reachability)
- 5-second debounce on non-critical events

**Configuration:**
- ENABLE_NETWORK_MONITOR
- NOTIFY_ON_CRITICAL_NETWORK_EVENTS (VPN disconnect, Internet loss)
- NOTIFY_ON_ALL_NETWORK_EVENTS (enables individual toggles)
- Individual event toggles for each event type

**Implementation Location:** notifier.py, example.env
```

---

## Testing Checklist

After implementation, verify:

- [ ] Configuration loads correctly from config.env
- [ ] NetworkManager detection works
- [ ] WiFi connect notification fires
- [ ] WiFi disconnect notification fires after 5-second debounce
- [ ] Rapid WiFi disconnect/connect (<5s) does NOT notify
- [ ] VPN connect notification fires (if enabled)
- [ ] VPN disconnect notification ALWAYS fires (even in critical-only mode)
- [ ] VPN disconnect notifies immediately (no debounce)
- [ ] Ethernet connect/disconnect notifications work
- [ ] Internet lost notification fires when link goes down
- [ ] Internet reachability check works (if enabled)
- [ ] Notifications work with both Telegram and Discord backends
- [ ] Both backends receive network notifications
- [ ] Service stops cleanly without errors
- [ ] No errors in journal logs

---

## Common Issues and Solutions

**Issue:** NetworkManager not detected
**Solution:** Check if NetworkManager is running: `systemctl status NetworkManager`

**Issue:** Permission denied on D-Bus
**Solution:** Most monitoring works without special permissions, but some properties may need PolicyKit. Check logs for specific errors.

**Issue:** False positives on WiFi disconnect
**Solution:** The 5-second debounce should handle this. If not, increase NETWORK_DEBOUNCE_SECONDS.

**Issue:** VPN notifications not firing
**Solution:** Ensure VPN is managed by NetworkManager. Some VPN clients (like OpenVPN client) don't integrate with NM.

---

## Notes for Next Developer

1. **VPN Security:** VPN disconnect notifications are ALWAYS sent regardless of configuration. This is a security requirement - user must know immediately if VPN drops.

2. **Privacy:** Do NOT include SSID in WiFi notifications. User specifically requested privacy.

3. **Debounce:** Only non-critical events use debounce. Critical events (VPN disconnect, internet lost) notify immediately.

4. **Both Connectivity Modes:**
   - Link state: Fast, reliable, uses NetworkManager signals
   - Reachability: Requires periodic ping, catches "connected but no internet" scenarios

5. **Error Handling:** All D-Bus operations must be wrapped in try/except. NetworkManager may not be available or may crash.

6. **Testing:** Test with actual WiFi/VPN connections. Don't rely solely on unit tests.

7. **Documentation:** Update CHANGELOG.md after implementation.

---

## Questions?

If unclear about requirements or implementation details:
1. Check the user requirements section above
2. Look at existing code patterns in notifier.py
3. Review the research in the task session (task_id: ses_31b15b826ffeUrI21Qxi2wlZzF)

**DO NOT PROCEED** if any requirements are unclear. Ask for clarification first.

---

**Ready to Implement:** Yes  
**Estimated Completion:** 2-3 hours  
**Files Modified:** 3 (notifier.py, example.env, ROADMAP.md)  
**New Classes:** 3 (DebouncedEventManager, InternetConnectivityChecker, NetworkMonitor)  
**Lines of Code:** ~400-500
