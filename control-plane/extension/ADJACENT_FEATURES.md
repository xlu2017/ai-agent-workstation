# Adjacent Selector Features

## Selection history

Store recent local region selections so a developer can replay the same target with a new request. History should keep page metadata, session id, region bounds, selected target summaries, evidence id, task id, and timestamp. Raw fallback images should not be retained by default.

## Source hints

Prefer app-provided source hints over brittle DOM traversal. Supported attributes include `data-jg-source-file`, `data-jg-source-line`, `data-jg-component`, `data-jg-framework`, `data-testid`, and `data-test`. Apps may also expose `window.__JG_COMPONENT_SOURCE_MAP__`.

## Confidence scoring

Classify selection evidence as high, medium, or low. Source hints and stable ids raise confidence. Fallback-only evidence remains low confidence but is still valid after user confirmation.

## Browser status feedback

After submission, the page should show whether the request was sent, whether ambient evidence was persisted, and whether the session task was accepted. The initial scaffold provides a toast primitive; later work can poll session status and live events.

## Prompt templates

Common browser-side request templates should cover visual polish, responsive fixes, accessibility, copy changes, interaction bugs, component extraction, loading and error states, and style matching.

## Visual fallback

Visual fallback is allowed only after explicit region selection and confirmation when no useful DOM target is found. The evidence must be marked as fallback and paired with exact region bounds.
