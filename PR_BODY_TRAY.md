## Summary

This PR implements the high-priority enhancements from `tray_app_enhancements.md`:

- **Connection pooling**: API client now uses `requests.Session` with connection pooling for better performance
- **Automatic retries**: Added exponential backoff retry strategy for transient failures (500, 502, 503, 504)
- **Adaptive polling**: Poll interval adjusts based on dashboard availability (fast when active, slow with backoff when down)
- **Enhanced notifications**: Success/error notifications for all service and model operations
- **Improved logging**: Added file logging with detailed error tracking and diagnostics
- **Type hints**: Full type annotations throughout the codebase
- **Busy state**: Icon changes to orange during pending operations

## Changes

### `api_client.py`
- Added `requests.Session` with connection pooling (10 connections)
- Implemented `urllib3.Retry` with exponential backoff (0.5s, 1s, 2s)
- Added detailed error recording with timestamps
- Added `close()` method for proper resource cleanup
- Full type hints and docstrings

### `ai_tray.py`
- Adaptive polling: 5s (fast), 10s (normal), 30-60s (backoff when down)
- Enhanced notifications with ✓/✗ prefixes for success/error
- File logging to `tray_app.log`
- Busy icon (orange) during pending operations
- Connection restoration logging
- Proper API session cleanup on exit

## Test plan

- [ ] Start tray app with dashboard running - should show green icon
- [ ] Stop dashboard - icon should turn red after 3 failures, then auto-restart
- [ ] Start/stop a service - should show notification
- [ ] Unload a model - should show notification
- [ ] Check `tray_app.log` for detailed logs

🤖 Generated with [Claude Code](https://claude.com/claude-code)
