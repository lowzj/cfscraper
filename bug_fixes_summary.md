# Bug Fixes Summary

## Bug 1: Export Route Duplication

**Issue**: The API router's `/export` prefix, combined with endpoints also defining `/export` in their paths, created redundant URL segments like `/api/v1/export/export/{export_id}`.

**Root Cause**: The export router was mounted with `/export` prefix in `app/api/routes/__init__.py`, but the DELETE endpoint at line 296 in `app/api/routes/export.py` also had `/export` in its path.

**Fix**: Updated the DELETE endpoint path from `/export/{export_id}` to `/{export_id}` since the prefix is already handled by the router mounting.

**Files Modified**:
- `app/api/routes/export.py` (line 296): Changed `@router.delete("/export/{export_id}")` to `@router.delete("/{export_id}")`

## Bug 2: Rate Limiting Middleware Ignores Dynamic Configuration

**Issue**: The `setup_rate_limiting` function was not being used and when manually adding the middleware, the `default_rule_id` parameter was not being passed, causing it to always use the hardcoded default value ("default_0").

**Root Cause**: 
1. The `RateLimitConfig` class was missing the `default_rule_id` attribute
2. The `setup_rate_limiting` function wasn't passing the `default_rule_id` parameter to the middleware constructor
3. The main application was manually adding the middleware instead of using the `setup_rate_limiting` function

**Fix**: 
1. Added `default_rule_id` parameter to `RateLimitConfig` class
2. Updated `setup_rate_limiting` function to pass the `default_rule_id` parameter
3. Modified `main.py` to use `setup_rate_limiting` function instead of manually adding the middleware

**Files Modified**:
- `app/core/rate_limit_middleware.py`:
  - Added `default_rule_id: str = "default_0"` parameter to `RateLimitConfig.__init__`
  - Added `self.default_rule_id = default_rule_id` to store the parameter
  - Updated `setup_rate_limiting` function to pass `default_rule_id=config.default_rule_id`
- `app/main.py`:
  - Updated imports to include `setup_rate_limiting` and `RateLimitConfig`
  - Replaced manual middleware addition with `setup_rate_limiting` function call
  - Created `RateLimitConfig` instance with proper configuration

## Impact

1. **Export URLs**: The DELETE export endpoint now correctly resolves to `/api/v1/export/{export_id}` instead of `/api/v1/export/export/{export_id}`
2. **Rate Limiting**: The rate limiting middleware now properly supports dynamic configuration of the default rule ID, allowing for more flexible rate limiting strategies
3. **Code Organization**: The `setup_rate_limiting` function is now properly integrated and used, improving maintainability

Both bugs have been fixed and the code has been verified to compile without syntax errors.