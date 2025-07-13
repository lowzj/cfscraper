# Bugs Fixed - Phase 3

## Bug Fix #1: AsyncIO Threading Issue in Selenium Scraper

### Problem Description
The `_apply_stealth_features` method in `app/scrapers/selenium_scraper.py` incorrectly called `asyncio.run(js_bypass_manager.get_stealth_scripts())` within a `ThreadPoolExecutor` context. This anti-pattern can lead to `RuntimeError` or unexpected behavior as it attempts to create a new event loop in a thread that is already managed by asyncio.

### Root Cause
- The `get_stealth_scripts()` method was unnecessarily async
- Using `asyncio.run()` inside a thread pool executor that's part of an existing asyncio application
- The async lock was protecting a simple read operation of a static list

### Solution
Made the `get_stealth_scripts()` method synchronous since it only returns a copy of a static list of JavaScript strings.

### Files Modified
- `app/utils/stealth_manager.py`: Lines 414-420
- `app/scrapers/selenium_scraper.py`: Lines 217-219

### Changes Made

**In `app/utils/stealth_manager.py`:**
- Changed `get_stealth_scripts()` from async to synchronous
- Removed unnecessary async lock (`self._lock`)
- Simplified `__init__` method

**In `app/scrapers/selenium_scraper.py`:**
- Removed `asyncio.run()` call
- Added safety check for driver initialization
- Direct synchronous call to `js_bypass_manager.get_stealth_scripts()`

### Code Changes
```python
# Before (problematic):
stealth_scripts = asyncio.run(js_bypass_manager.get_stealth_scripts())

# After (fixed):
stealth_scripts = js_bypass_manager.get_stealth_scripts()
```

### Impact
- Eliminates potential `RuntimeError` from event loop conflicts
- Improves performance by removing unnecessary async overhead
- Maintains thread safety without blocking async operations
- Code is now properly compatible with ThreadPoolExecutor usage

### Testing
- Both modified files compile successfully without syntax errors
- No other code dependencies affected (only one caller of the method)