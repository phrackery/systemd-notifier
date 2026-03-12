#!/usr/bin/env python3
"""
D-Bus Lock/Unlock Signal Test Script
Tests if Python can receive lock/unlock signals from systemd-logind
"""

import os
import sys
import time
import signal

# Set required environment variables if not already set
if 'XDG_SESSION_ID' not in os.environ:
    os.environ['XDG_SESSION_ID'] = '2'
if 'DBUS_SESSION_BUS_ADDRESS' not in os.environ:
    os.environ['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=/run/user/1000/bus'

try:
    from gi.repository import Gio, GLib
except ImportError as e:
    print(f"ERROR: Cannot import Gio/GLib: {e}")
    print("Install with: sudo apt install python3-gi")
    sys.exit(1)

class LockSignalTest:
    def __init__(self):
        self.bus = None
        self.subscriptions = []
        self.session_id = os.environ.get('XDG_SESSION_ID', '')
        self.received_signals = []
        
    def connect_to_bus(self):
        """Connect to system D-Bus"""
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
            print(f"✓ Connected to system D-Bus")
            print(f"  Session ID: {self.session_id}")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to D-Bus: {e}")
            return False
    
    def on_lock_signal(self, conn, sender, path, iface, signal_name, params):
        """Handle Lock signal"""
        timestamp = time.strftime("%H:%M:%S")
        msg = f"[{timestamp}] 🔒 LOCK signal received!"
        print(f"\n{'='*50}")
        print(msg)
        print(f"  Path: {path}")
        print(f"  Interface: {iface}")
        print(f"  Signal: {signal_name}")
        print(f"{'='*50}\n")
        self.received_signals.append(('lock', timestamp))
    
    def on_unlock_signal(self, conn, sender, path, iface, signal_name, params):
        """Handle Unlock signal"""
        timestamp = time.strftime("%H:%M:%S")
        msg = f"[{timestamp}] 🔓 UNLOCK signal received!"
        print(f"\n{'='*50}")
        print(msg)
        print(f"  Path: {path}")
        print(f"  Interface: {iface}")
        print(f"  Signal: {signal_name}")
        print(f"{'='*50}\n")
        self.received_signals.append(('unlock', timestamp))
    
    def subscribe_to_signals(self):
        """Subscribe to Lock/Unlock signals"""
        if not self.session_id:
            print("✗ XDG_SESSION_ID not set!")
            return False
        
        # Construct session path - IMPORTANT: Session IDs may have underscores!
        # For example: "2" becomes "/org/freedesktop/login1/session/_32" (not "2"!)
        # Actually, looking at the loginctl output, session ID "2" maps to path "_32"
        # Let me query the actual path from loginctl
        import subprocess
        try:
            result = subprocess.run(['loginctl', 'show-session', self.session_id, '--property=Id'], 
                                  capture_output=True, text=True)
            actual_id = result.stdout.strip().replace('Id=', '')
            session_path = f"/org/freedesktop/login1/session/{actual_id}"
        except:
            session_path = f"/org/freedesktop/login1/session/{self.session_id}"
        
        print(f"\nSubscribing to signals at path: {session_path}")
        
        try:
            # Subscribe to Lock signal
            sub_id = self.bus.signal_subscribe(
                "org.freedesktop.login1",
                "org.freedesktop.login1.Session",
                "Lock",
                session_path,
                None,
                Gio.DBusSignalFlags.NONE,
                self.on_lock_signal
            )
            self.subscriptions.append(sub_id)
            print(f"✓ Subscribed to Lock signals (ID: {sub_id})")
            
            # Subscribe to Unlock signal
            sub_id = self.bus.signal_subscribe(
                "org.freedesktop.login1",
                "org.freedesktop.login1.Session",
                "Unlock",
                session_path,
                None,
                Gio.DBusSignalFlags.NONE,
                self.on_unlock_signal
            )
            self.subscriptions.append(sub_id)
            print(f"✓ Subscribed to Unlock signals (ID: {sub_id})")
            
            return True
        except Exception as e:
            print(f"✗ Failed to subscribe: {e}")
            return False
    
    def run(self, timeout_seconds=30):
        """Run the test"""
        print("\n" + "="*60)
        print("D-BUS LOCK/UNLOCK SIGNAL TEST")
        print("="*60)
        
        if not self.connect_to_bus():
            return 1
        
        if not self.subscribe_to_signals():
            return 1
        
        print("\n" + "-"*60)
        print(f"LISTENING FOR SIGNALS... (timeout: {timeout_seconds}s)")
        print("-"*60)
        print("\nInstructions:")
        print("1. Lock your screen (Super+L) or run: loginctl lock-session")
        print("2. You should see a 🔒 LOCK signal above")
        print("3. Unlock your screen")
        print("4. You should see a 🔓 UNLOCK signal above")
        print("\nWaiting for signals...\n")
        
        # Set up timeout
        def timeout_callback():
            print(f"\n⏱️  Timeout reached ({timeout_seconds}s)")
            self.print_summary()
            self.cleanup()
            sys.exit(0)
        
        GLib.timeout_add_seconds(timeout_seconds, timeout_callback)
        
        # Handle Ctrl+C
        def signal_handler(sig, frame):
            print("\n\nInterrupted by user")
            self.print_summary()
            self.cleanup()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Run main loop
        try:
            GLib.MainLoop().run()
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()
        
        return 0
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"Session ID: {self.session_id}")
        print(f"Signals received: {len(self.received_signals)}")
        if self.received_signals:
            for sig_type, timestamp in self.received_signals:
                icon = "🔒" if sig_type == "lock" else "🔓"
                print(f"  {icon} {sig_type.upper()} at {timestamp}")
        else:
            print("  ✗ No signals received!")
            print("\nPossible issues:")
            print("  - D-Bus connection failed")
            print("  - Wrong session ID (check XDG_SESSION_ID)")
            print("  - Session path doesn't match")
        print("="*60 + "\n")
    
    def cleanup(self):
        """Clean up subscriptions"""
        for sub_id in self.subscriptions:
            try:
                self.bus.signal_unsubscribe(sub_id)
            except:
                pass
        print("✓ Cleaned up D-Bus subscriptions")


if __name__ == "__main__":
    # Allow setting session ID from command line
    if len(sys.argv) > 1:
        os.environ['XDG_SESSION_ID'] = sys.argv[1]
    
    timeout = 30
    if len(sys.argv) > 2:
        timeout = int(sys.argv[2])
    
    print(f"Python: {sys.version}")
    print(f"Gio/GLib: Available")
    print(f"Session ID: {os.environ.get('XDG_SESSION_ID', 'NOT SET')}")
    
    test = LockSignalTest()
    sys.exit(test.run(timeout))
