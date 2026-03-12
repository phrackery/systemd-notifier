# systemd-notifier Debug Session Summary

**Date:** March 11, 2026  
**Status:** IN PROGRESS - Lock/Unlock notifications not working yet  
**Branch:** main  
**Commit:** cf469b2

---

## Current Status

### What Works ✅
- Service starts and runs without crashing
- Configuration loads correctly from ~/.config/systemd-notifier/config.env
- Telegram API works (tested successfully with real token)
- D-Bus connection works
- Session path lookup works (Session ID 2 → /org/freedesktop/login1/session/_32)
- Sleep/Shutdown detection (not fully tested but should work)

### What's Broken ❌
- **Lock/Unlock notifications NOT being received**
- Service doesn't log anything when lock/unlock events occur
- No Telegram messages sent on lock/unlock

---

## Bugs Fixed (Already Deployed)

### Bug 1: Wrong session path construction
**File:** src/notifier.py, line 509
**Problem:** The code was constructing session path as `/org/freedesktop/login1/session/2` but actual path is `/org/freedesktop/login1/session/_32`

**Fix:** Added GetSession D-Bus call to query actual object path from logind
```python
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
```

**Verified:** ✅ Session path lookup works correctly now

### Bug 2: Missing PassEnvironment in systemd service
**File:** systemd/system-notifier.service
**Problem:** Systemd wasn't passing XDG_SESSION_ID to the service

**Fix:** Added `PassEnvironment=XDG_SESSION_ID DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR`

**Status:** ✅ Service file updated and deployed

---

## Debugging Tools Created

### test_dbus.py
**Location:** ~/Desktop/webprojects-opencode/systemd-notifier/test_dbus.py
**Purpose:** Standalone diagnostic script to test D-Bus signal reception
**Usage:**
```bash
cd ~/Desktop/webprojects-opencode/systemd-notifier
python3 test_dbus.py
# Then lock/unlock screen to see if signals are received
```

### Manual Test Commands
```bash
# Check session info
loginctl show-session 2

# Test lock/unlock manually
loginctl lock-session
loginctl unlock-session

# Monitor D-Bus signals manually
dbus-monitor --system "interface='org.freedesktop.login1.Session'"

# Test Telegram
cd ~/.local/share/systemd-notifier/src
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
./telegram.sh "Test message"
```

---

## Key Findings

### Session ID Mapping
- **Environment:** XDG_SESSION_ID=2
- **D-Bus Object Path:** /org/freedesktop/login1/session/_32
- **Interface:** org.freedesktop.login1.Session
- **Signals:** Lock(), Unlock()

### Service Status
```
Location: ~/.config/systemd/user/system-notifier.service
Status: Currently STOPPED (was killed during testing)
Needs: systemctl --user start system-notifier
```

### Configuration
```
File: ~/.config/systemd-notifier/config.env
TELEGRAM_BOT_TOKEN=8637402945:AAE-BHSUX8ceeg26H5nwJeTW6I2IT26AdFw
TELEGRAM_CHAT_ID=7635301901
PRE_EVENT_DELAY=0 (changed from 60 for lock events)
NOTIFY_ON_LOCK=true
NOTIFY_ON_UNLOCK=true
```

---

## What Still Needs Investigation

### Problem: No lock/unlock signals received
**Last test:** Manual Python test showed "XDG_SESSION_ID not set" even though it was exported

**Possible causes:**
1. D-Bus signal subscription not working correctly
2. Wrong interface/path being used for subscription
3. Signal handler not being called
4. Permission issues with D-Bus

**Next steps to try:**
1. Run test_dbus.py and verify it receives signals
2. Check if notifier.py is actually subscribing to correct path
3. Add extensive logging to see what's happening
4. Test with simpler signal subscription (no path filter)

---

## Files Modified

1. **src/notifier.py** - Fixed session path lookup
2. **systemd/system-notifier.service** - Added PassEnvironment
3. **test_dbus.py** - New diagnostic tool

All changes committed to GitHub.

---

## Quick Start for Next Session

```bash
# 1. Start the service
systemctl --user start system-notifier

# 2. Check if it's running
systemctl --user status system-notifier

# 3. Watch logs in real-time
journalctl --user -u system-notifier -f

# 4. Test lock/unlock
loginctl lock-session
# Check Telegram for notification
loginctl unlock-session
# Check Telegram for notification

# 5. If not working, run diagnostic
cd ~/Desktop/webprojects-opencode/systemd-notifier
python3 test_dbus.py
```

---

## Contact Info

- **Repository:** https://github.com/phrackery/systemd-notifier
- **Last commit:** cf469b2 - Fix lock/unlock monitoring: Query actual D-Bus session path from logind
- **Current branch:** main

---

## Notes for Next AI

1. The service was stopped/killed during testing - needs to be restarted
2. Telegram API is working correctly (tested manually)
3. Session path lookup is working correctly now
4. Main issue is signals not being received by the Python script
5. Consider adding more debug logging to the signal handlers
6. The test_dbus.py script can help isolate if it's a D-Bus issue or Python code issue

**Priority:** Get lock/unlock signal subscription working
