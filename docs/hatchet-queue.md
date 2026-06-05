# Hatchet Queue Integration

The platform queue uses Hatchet as the durable scheduler for agent-session tasks.
The executor itself remains synchronous: Hatchet invokes a task, and that task
runs the selected executor adapter against one platform session worktree.

## Why Hatchet is used

Hatchet gives the platform a durable task layer for:

- queued session tasks
- worker concurrency slots
- retries and run history
- cancellation and observability through Hatchet
- a dashboard separate from the executor implementation

This keeps queue semantics outside `DirectExecutor` and `OpenHandsExecutorAdapter`.

## Runtime shape

```text
control plane submitter
  -> Hatchet task: platform-session-task
  -> platform worker process
  -> run_platform_task(input)
  -> OpenHandsExecutorAdapter or DirectExecutor
  -> /opt/workstation/sessions/<session_id>/events/events.jsonl
  -> TaskResult
```

## Files

```text
requirements-control-plane.txt
control-plane/platform_queue/models.py
control-plane/platform_queue/hatchet_client.py
control-plane/platform_queue/hatchet_tasks.py
control-plane/platform_queue/worker.py
control-plane/platform_queue/submitter.py
control-plane/platform_queue/executor_runner.py
```

## Host install

The worker should run on the host, not inside a generic container, because it
needs direct access to `/opt/workstation` worktrees, git metadata, tmux-adjacent
session files, and local OpenHands/LiteLLM endpoints.

```bash
cd ~/ai-workstation
python3 -m venv .venv-control-plane
. .venv-control-plane/bin/activate
pip install -r requirements-control-plane.txt
```

## Required Hatchet configuration

Configure Hatchet using the current Hatchet SDK environment variables for your
self-hosted or Hatchet Cloud instance. At minimum, that normally means a client
token plus endpoint/TLS settings appropriate for your deployment.

Example `.env` additions:

```bash
HATCHET_CLIENT_TOKEN=<set-from-hatchet>
PLATFORM_HATCHET_WORKER_NAME=platform-session-worker
PLATFORM_HATCHET_WORKER_SLOTS=2
```

Do not commit actual Hatchet tokens.

## Run the worker

```bash
cd ~/ai-workstation
. .venv-control-plane/bin/activate
set -a
. .env
set +a
python -m control-plane.platform_queue.worker
```

If module execution has trouble with the hyphen in `control-plane`, run it by
path instead:

```bash
PYTHONPATH=control-plane python control-plane/platform_queue/worker.py
```

## Submitter behavior

`platform_queue.submitter.submit_platform_task()` attempts to submit to Hatchet.
If Hatchet is unavailable or not configured, it records a local durable queue
record at:

```text
/opt/workstation/tasks/<task_id>/queue.json
```

That local fallback preserves intent, but it is not a real scheduler. Use the
Hatchet worker for production queueing.

## OpenHands-first default

The default queued executor is `openhands`. Use `direct` only for explicit
fallback or smoke-test tasks.
