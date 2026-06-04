# Expected Resolution: backend-input-sanitization

## Problem
Transaction notes stored without sanitization — HTML/script injection possible.

## Expected Fix
- Add sanitization before DB insert: strip HTML tags from note
- Use regex `/<[^>]*>/g` replacement or a library like `sanitize-html`
- Store sanitized text in `description` field

## Files Expected to Change
- `backend/transaction-routes.ts`

## Validation
- Backend tests pass
- Submitting `<script>alert(1)</script>` as note stores plain text only
