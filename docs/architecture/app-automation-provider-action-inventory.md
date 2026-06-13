# App Automation Provider Action Inventory

## Intent

This document records the checked-in app-automation provider action inventory
used by the recommend-next taxonomy scaffold.

The provider inventory is route-level evidence. The authoritative category map is
still the root taxonomy:

```text
control-plane/execution/recommend_next_action_taxonomy.py
```

The supporting provider inventory is:

```text
control-plane/execution/recommend_next_app_automation_provider_inventory.py
```

## Provider support

### Activepieces

Route support:

```text
github.create_issue
slack.send_message
gmail.search_email
google_calendar.create_event
google_sheets.append_row
notion.create_page
linear.create_issue
jira.create_issue
discord.send_message
hubspot.create_contact
```

Local vendored adapter support:

```text
google_sheets.append_row
jira.create_issue
discord.send_message
slack.send_message
```

### Composio

Route support:

```text
github.create_issue
github.search_repo
slack.send_message
gmail.search_email
google_calendar.create_event
google_sheets.append_row
notion.create_page
linear.create_issue
jira.create_issue
discord.send_message
hubspot.create_contact
```

Local vendored adapter support:

```text
gmail.search_email
slack.send_message
google_calendar.create_event
notion.create_page
linear.create_issue
hubspot.create_contact
```

### MCP servers

Route support:

```text
github.create_issue
github.search_repo
gmail.search_email
```

Local vendored adapter support:

```text
github.search_repo
github.create_issue
```

### n8n

Route support:

```text
slack.send_message
google_calendar.create_event
google_sheets.append_row
notion.create_page
jira.create_issue
discord.send_message
hubspot.create_contact
```

Local vendored adapter support:

```text
slack.send_message
google_sheets.append_row
jira.create_issue
discord.send_message
```

### Stagehand

Route support:

```text
web.perform_task
web.visual_task
```

Local vendored adapter support:

```text
web.perform_task
web.visual_task
```

### Browser Use

Route support:

```text
web.perform_task
web.visual_task
```

Local vendored adapter support:

```text
web.perform_task
web.visual_task
```

### Skyvern

Route support:

```text
web.perform_task
web.visual_task
```

Local vendored adapter support:

```text
web.visual_task
web.perform_task
```

## Deduplicated total action set

After provider overlap is removed, the checked-in app-automation action set is:

```text
discord.send_message
github.create_issue
github.search_repo
gmail.search_email
google_calendar.create_event
google_sheets.append_row
hubspot.create_contact
jira.create_issue
linear.create_issue
notion.create_page
slack.send_message
web.perform_task
web.visual_task
```

## Four-category assignment

The root-level taxonomy assigns these deduplicated app-automation actions as:

```text
find_out_more:
  github.search_repo
  gmail.search_email

execute:
  discord.send_message
  github.create_issue
  google_calendar.create_event
  google_sheets.append_row
  hubspot.create_contact
  jira.create_issue
  linear.create_issue
  notion.create_page
  slack.send_message
  web.perform_task
  web.visual_task
```

No app-automation provider action ID is currently categorized as `ask_user` or
`stop`; those categories are reserved for controller/status outcomes such as
missing approval, missing params, runtime not configured, or unknown action.

## Scaffold status

This is documentation and taxonomy scaffold only. It does not expand live vendor
capabilities, change routing, execute app actions, or authorize side effects.
