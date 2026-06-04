# Expected Resolution: accessibility-label-bug

## Problem
Icon-only buttons missing `aria-label` attributes — inaccessible to screen readers.

## Expected Fix
- Add `aria-label="Like transaction"` to the like IconButton
- Add `aria-label="Add comment"` to the comment IconButton
- Add `aria-label="View notifications"` to the notifications IconButton

## Files Expected to Change
- `src/components/TransactionDetail.tsx`
- `src/components/NavBar.tsx`

## Validation
- Unit tests pass
- Axe accessibility audit finds no unlabeled buttons
