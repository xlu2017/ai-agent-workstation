# App Automation Provider Action Inventory

## Intent

This document records the checked-in app-automation provider action inventory
used by the recommend-next taxonomy scaffold.

The root taxonomy tracks only provider-neutral top-level actions. Provider names,
app names, and app-specific action IDs are represented as parameters or alias
metadata.

The authoritative category map is still:

```text
control-plane/execution/recommend_next_action_taxonomy.py
```

The supporting provider inventory and parameter schema is:

```text
control-plane/execution/recommend_next_app_automation_provider_inventory.py
```

## Core rule

Do this:

```text
action_name = email.create
params.email_provider = outlook
```

Do not do this at the root taxonomy level:

```text
action_name = outlook.create_email
```

Similarly:

```text
action_name = message.send
params.message_provider = slack

action_name = issue.create
params.issue_provider = github

action_name = calendar_event.create
params.calendar_provider = google_calendar
```

## Provider route support

The route inventory records which automation runtime providers can serve each
top-level action. This is route evidence only; it is not the root action name.

### Activepieces

```text
issue.create
message.send
email.search
calendar_event.create
spreadsheet_row.append
page.create
contact.create
```

### Composio

```text
issue.create
repository.search
message.send
email.search
email.create
email.send
calendar_event.create
spreadsheet_row.append
page.create
contact.create
```

### MCP servers

```text
issue.create
repository.search
email.search
```

### n8n

```text
message.send
email.send
calendar_event.create
spreadsheet_row.append
page.create
issue.create
contact.create
```

### Stagehand

```text
browser_task.perform
visual_browser_task.perform
```

### Browser Use

```text
browser_task.perform
visual_browser_task.perform
```

### Skyvern

```text
browser_task.perform
visual_browser_task.perform
```

## App-specific aliases

Checked-in app-specific catalog IDs normalize to top-level actions before the
root taxonomy lookup.

```text
github.create_issue -> issue.create
linear.create_issue -> issue.create
jira.create_issue -> issue.create

github.search_repo -> repository.search

gmail.search_email -> email.search
gmail.create_email -> email.create
gmail.send_email -> email.send
outlook.create_email -> email.create
outlook.send_email -> email.send

slack.send_message -> message.send
discord.send_message -> message.send

google_calendar.create_event -> calendar_event.create
outlook_calendar.create_event -> calendar_event.create

google_sheets.append_row -> spreadsheet_row.append
notion.create_page -> page.create
hubspot.create_contact -> contact.create
web.perform_task -> browser_task.perform
web.visual_task -> visual_browser_task.perform
```

## Deduplicated top-level action set

After provider overlap is removed, the scaffolded app-automation action set is:

```text
browser_task.perform
calendar_event.create
contact.create
email.create
email.search
email.send
issue.create
message.send
page.create
repository.search
spreadsheet_row.append
visual_browser_task.perform
```

## Four-category assignment

The root-level taxonomy assigns these top-level app-automation actions as:

```text
find_out_more:
  email.search
  repository.search

execute:
  browser_task.perform
  calendar_event.create
  contact.create
  email.create
  email.send
  issue.create
  message.send
  page.create
  spreadsheet_row.append
  visual_browser_task.perform
```

No app-automation top-level action is currently categorized as `ask_user` or
`stop`; those categories remain controller/status outcomes such as missing
approval, missing params, runtime not configured, or unknown action.

## Parameter schema examples

### email.create

```text
action_name = email.create
required params = to
optional params = subject, body, cc, bcc, email_provider, automation_vendor, catalog_action_id
provider examples = gmail, outlook
```

### email.search

```text
action_name = email.search
required params = query
optional params = limit, email_provider, automation_vendor, catalog_action_id
provider examples = gmail, outlook
```

### message.send

```text
action_name = message.send
required params = text
optional params = channel, recipient, message_provider, automation_vendor, catalog_action_id
provider examples = slack, discord, teams
```

### issue.create

```text
action_name = issue.create
required params = title
optional params = repo, team, project, body, description, issue_provider, automation_vendor, catalog_action_id
provider examples = github, linear, jira
```

## Scaffold status

This is documentation and taxonomy scaffold only. It does not expand live vendor
capabilities, change routing, execute app actions, or authorize side effects.
