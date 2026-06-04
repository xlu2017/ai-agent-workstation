# Expected Resolution: disabled-submit-button

## Problem
Submit button disabled logic is inverted: `disabled={isValid || isSubmitting}` should be `disabled={!isValid || isSubmitting}`.

## Expected Fix
- Change `disabled={isValid || isSubmitting}` to `disabled={!isValid || isSubmitting}`

## Files Expected to Change
- `src/components/SignUpForm.tsx`

## Validation
- Unit tests pass
- Cypress auth spec passes (sign-up flow)
