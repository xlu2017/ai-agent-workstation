# Expected Resolution: broken-form-validation

## Problem
The transaction form's amount validation was removed, allowing invalid (zero, negative, NaN) amounts to be submitted.

## Expected Fix
- Restore `validateAmount` function that checks `parseFloat(value) > 0`
- Restore `amountError` state and display it as helper text on the amount field
- Gate form submission on validation passing
- Disable submit button when amount is invalid

## Files Expected to Change
- `src/components/TransactionCreateStepTwo.tsx`

## Validation
- Unit tests for the component pass
- Cypress new-transaction tests pass
- Manual: entering "0", "-5", or "abc" shows error and blocks submit
