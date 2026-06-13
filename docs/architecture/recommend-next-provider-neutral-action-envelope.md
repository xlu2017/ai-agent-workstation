# Recommend-Next Provider-Neutral Action Envelope

## Intent

Recommend-next should track only top-level provider-neutral actions. App-specific
providers, account systems, and execution vendors are parameters or route
metadata.

The scaffold files are:

```text
control-plane/execution/recommend_next_action_envelope_schema.py
control-plane/execution/recommend_next_action_alias_normalizer.py
control-plane/execution/recommend_next_app_automation_provider_inventory.py
```

## Canonical envelope shape

```text
action_name: provider-neutral top-level action
params: provider/app-specific values and user inputs
source_action_name: original alias or catalog action, if any
catalog_action_id: app-automation catalog ID, if any
automation_vendor: execution vendor route hint, if any
decision_type: execute | find_out_more | ask_user | stop
```

## Examples

Create or draft an email through Gmail:

```text
action_name = email.create
params.email_provider = gmail
params.to = user-provided recipient
```

Create or draft an email through Outlook:

```text
action_name = email.create
params.email_provider = outlook
params.to = user-provided recipient
```

Send a Slack message:

```text
action_name = message.send
params.message_provider = slack
params.channel = user-provided channel
params.text = user-provided message
```

Create a GitHub issue:

```text
action_name = issue.create
params.issue_provider = github
params.repo = user-provided repository
params.title = user-provided title
```

## Alias normalization

Legacy or app-specific catalog IDs may still enter the platform from existing
catalogs. They normalize before root-taxonomy lookup.

```text
gmail.create_email -> email.create
outlook.create_email -> email.create
gmail.send_email -> email.send
outlook.send_email -> email.send
slack.send_message -> message.send
discord.send_message -> message.send
github.create_issue -> issue.create
linear.create_issue -> issue.create
jira.create_issue -> issue.create
```

The normalized alias carries:

```text
source_action_name = original app-specific action
catalog_action_id = original app-specific action, when applicable
params.<provider_parameter> = inferred provider name, when absent
```

## Non-goals

This scaffold does not:

```text
call recommend-next
change runtime routing
execute app actions
validate credentials
authorize side effects
replace app-automation executor contracts
```

It only defines the intended envelope shape so later controller integration can
normalize aliases consistently before checking the root taxonomy.
