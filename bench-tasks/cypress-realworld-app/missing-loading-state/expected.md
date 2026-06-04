# Expected Resolution: missing-loading-state

## Problem
Loading spinner removed from TransactionList — blank screen during fetch.

## Expected Fix
- Restore the `if (isLoading)` guard that returns a `<CircularProgress>` spinner
- Include `data-test="transaction-loading"` for testability
- Place before the error check

## Files Expected to Change
- `src/components/TransactionList.tsx`

## Validation
- Unit tests pass (mock loading state → spinner renders)
