# Airlock

Guardrails for AI coding agents. Approve risky actions from your phone instead of watching your terminal.

Claude Code can work unattended for an hour which can lead to unwanted changes and potential data leaks.

# Architecture

Claude Code
↓ PreToolUse hook (stdin JSON)
adapter → normalize → policy engine
↓ allow ↓ require approval ↓ block
silent POST /approval :8787 notify only
↓
iMessage → you → reply
↓
resolve promise → agent proceeds or stops


Claude Code's `PreToolUse` hook allows for the classification of certain hooks and allows some hooks to be denied when needed.

Shell commands are parsed with `shlex` — never executed — and reduced to facts like `force_push`, `recursive_delete`, `privilege_escalation`, `download_and_execute`. Every rule in `policies/airlock.yaml` is evaluated based on risk score and a decision of  require approval, or block is reached. Policies contains our deterministic algorithm for common hooks

Bridge (TypeScript/Bun). Holds a Spectrum connection to iMessage. On "require approval" the Python side POSTs `/approval` and that HTTP request blocks.

# Photon

Allows user to communicate with claude API on their phone and get notifications about tasks and approve or reject tasks as needed.

#Running the project
Users have to text the relevant number for this project and user info such as name and phone number is necessary to establish authentication.

Users can update and manage task information within the message channel with the agent.


