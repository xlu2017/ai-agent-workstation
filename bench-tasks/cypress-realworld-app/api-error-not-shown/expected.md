# Expected Resolution: api-error-not-shown

## Problem
API errors on transaction creation are silently swallowed — empty catch block.

## Expected Fix
- Restore catch block that extracts error message from response
- Restore `error` state variable
- Render an Alert/Snackbar component when error is set
- Include data-test attribute for e2e testing

## Files Expected to Change
- `src/containers/TransactionCreateContainer.tsx`

## Validation
- Unit tests pass
- Cypress new-transaction error scenario passes
- Manual: force a 422 response → error message visible
