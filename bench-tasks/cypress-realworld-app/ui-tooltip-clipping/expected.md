# Expected Resolution: ui-tooltip-clipping

## Problem
The tooltip on transaction amounts is clipped by the parent list container's `overflow: hidden`.

## Expected Fix
- Restore the `<Tooltip>` wrapper around the amount hint element.
- Ensure tooltip uses Material-UI's Popper (portal-based) so it renders outside the overflow container.
- Alternatively, add `PopperProps={{ disablePortal: false }}` or wrap with a custom portal.
- The list's `overflow: hidden` must remain intact for scroll behavior.

## Files Expected to Change
- `src/components/TransactionItem.tsx` — restore tooltip, adjust placement/portal

## Validation
- `yarn test` passes
- Cypress transaction feed tests pass
- Visual: tooltip fully visible above row on hover
