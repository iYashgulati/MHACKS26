# Photon bridge

The bridge sends Airlock approval requests and Claude completion reports to the
iMessage conversation configured by `MY_PHONE`.

## Run

```bash
bun install
bun run server.ts
```

Keep the server running while using Claude Code from the repository root. The
project hooks then:

- request phone approval for risky `PreToolUse` actions;
- accept `yes`, `no`, questions, or redirects such as `no, clear node_modules instead`;
- reply with `Complete` and Claude's final response when Claude finishes.

The completion endpoint also understands `StopFailure`, but Claude Code 2.0.27
does not support that hook event. Add it to `.claude/settings.json` after
upgrading Claude Code if API-error notifications are needed.

The bridge forwards Claude's actual final response directly, so completion
delivery does not depend on another model request. Older Claude versions that
omit the response from the Stop payload recover it from the session transcript.
Repository-wide dirty-tree statistics are not included because they do not
identify changes made by the just-completed task.

## Verify

From the repository root:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

From this directory:

```bash
bunx tsc --noEmit
```
