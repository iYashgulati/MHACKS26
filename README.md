# Airlock

Airlock is a provider-neutral runtime policy layer for coding agents. It receives a
tool call before execution, normalizes it, evaluates deterministic policy, and
returns `ALLOW`, `REQUIRE_APPROVAL`, or `BLOCK`.

The model proposes an action; Airlock owns the permission decision.

## Run it

Python 3.11+ and PyYAML are required.

```bash
python -m pip install -e .

echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' \
  | python -m Airlock.hook --provider claude
```

For Claude Code, `REQUIRE_APPROVAL` is returned as Claude's native `ask`
decision. Claude displays the approval prompt in its own interface, so the hook
does not need direct terminal access.

Different provider payloads normalize into the same internal `Action`:

```bash
echo '{"tool":"run_shell_command","args":{"cmd":"npm install express"}}' \
  | python -m Airlock.hook --provider gemini

echo '{"type":"shell","input":{"command":"cat .env"}}' \
  | python -m Airlock.hook --provider codex
```

Use `--output hook` to emit a native provider hook response. Claude uses its
native approval UI as the local stand-in for the future Photon implementation.
The optional `--approval terminal` mode remains available for environments
where hook processes can access `/dev/tty`.

Decisions are appended to `.airlock/audit.jsonl` without raw tool input or file
contents. Use `--no-audit` to disable this or `--audit-log PATH` to move it.

## Test

```bash
python -m unittest discover -s tests -v
```

Run the non-executing judge demo with:

```bash
python -m Airlock.demo
```

## Architecture

```text
provider hook JSON
       ↓
Claude / Codex / Gemini adapter
       ↓
normalized Action + deterministic shell facts
       ↓
composable rules from Airlock/policies/airlock.yaml
       ↓
ALLOW | REQUIRE_APPROVAL | BLOCK
       ↓
provider-native hook response + append-only audit record
```

Photon and SpacetimeDB belong behind the approval and audit interfaces. They can
replace terminal approval and JSONL persistence without changing the security
engine.

Non-activating hook configuration examples live in `Airlock/config/`. Copy the
relevant example into the provider's project settings only after reviewing the
command. They are examples rather than active repository hooks so cloning this
project cannot silently install a trusted execution hook.
