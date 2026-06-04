# Expected Resolution: flaky-e2e-test

## Problem
Notification tests use `cy.wait(500)` instead of proper Cypress waiting patterns, causing flakiness.

## Expected Fix
- Replace `cy.wait(500)` with `cy.intercept("GET", "/notifications*").as("getNotifications")`
- Add `cy.wait("@getNotifications")` to synchronize on API response
- Use `.should("be.visible")` assertions before click actions
- Add read-state assertion after marking as read

## Files Expected to Change
- `cypress/tests/ui/notifications.spec.ts`

## Validation
- `yarn cypress:run --spec cypress/tests/ui/notifications.spec.ts` passes 3/3 times
- No `cy.wait(<number>)` calls remain
