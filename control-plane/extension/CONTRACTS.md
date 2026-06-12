# Selector Extension Contracts

## Region edit payload

The extension submits a single browser-region edit payload to the background worker. The background worker transforms it into an ambient event and a normal session chat request.

Required fields:

```text
sessionId
prompt
page.url
page.title
selection.mode
selection.bounds
selection.elements
visual fallback metadata when used
```

## Selection object

```text
mode: drag_region
bounds: viewport-relative x y width height
elements: array of selected target summaries
```

Each selected target should contain:

```text
tagName
selector
text
role
ariaLabel
testId
id
className
bounds
framework
componentName
sourceHint or sourceFile when available
```

## Confidence contract

The selector should classify evidence before submission.

```text
high: source hint or strong framework hint plus stable selector
medium: selector plus text role id or test id
low: visual fallback only or broad ambiguous region
```

Low confidence does not block submission. It changes the generated instruction so the agent knows that selected evidence is weak.

## History contract

History is local extension state. It is for developer convenience only.

Store:

```text
session id
page url/title
region bounds
target summaries
prompt text
ambient evidence id
task id
created timestamp
```

Do not store raw fallback image data in history by default.

## Source hint contract

Preferred app annotations:

```text
data-testid
```

Optional source annotations:

```text
data-jg-component
data-jg-framework
data-jg-source-file
data-jg-source-line
```

Optional global mapping:

```text
window.__JG_COMPONENT_SOURCE_MAP__[key]
```

## Session chat contract

The background worker submits the final instruction to:

```text
POST /api/sessions/{session_id}/chat
```

The existing control-plane prompt handler then emits `user_prompt_received`, routes the task, validates policy, and executes using the configured executor path.

## Ambient context contract

Before chat submission, the background worker attempts to persist the selection evidence to:

```text
POST /api/sessions/{session_id}/ambient/events
```

If this route is unavailable, chat still proceeds. Once the ambient router is mounted, the agent can use the evidence id in context packets.
