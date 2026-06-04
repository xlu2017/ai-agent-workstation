# Expected Resolution: stale-notification-badge

## Problem
After marking a notification as read, the badge count doesn't update until page refresh.

## Expected Fix
- After successful API patch, update local notifications state (mark item as read)
- Decrement unread count state variable
- Badge component reactively reflects the count

## Files Expected to Change
- `src/containers/NotificationsContainer.tsx`

## Validation
- Unit tests pass
- Cypress notification test: badge decrements after reading
