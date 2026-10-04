from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


SENSITIVE = (
    "auth",
    "login",
    "password",
    "secret",
    "token",
    "payment",
    "billing",
    "migration",
    "schema",
    ".env",
    "config",
    "dockerfile",
    "requirements",
    "package.json",
    "lock",
)


@dataclass(frozen=True)
class DiffSummary:
    added: int
    removed: int
    files: tuple[str, ...]

    @property
    def diffstat(self) -> str:
        noun = "file" if len(self.files) == 1 else "files"
        return f"{len(self.files)} {noun} changed, +{self.added}/-{self.removed}"


def _significance(added: int, removed: int, files: list[str]) -> tuple[str, list[str]]:
    reasons: list[str] = []

    touched = [
        filename
        for filename in files
        if any(sensitive in filename.lower() for sensitive in SENSITIVE)
    ]
    if touched:
        reasons.append("touched " + ", ".join(touched[:3]))
    if added + removed > 150:
        reasons.append(f"{added + removed} lines changed")
    if len(files) > 8:
        reasons.append(f"{len(files)} files changed")
    if removed > 40 and removed > added * 2:
        reasons.append("mostly deletions")

    return ("review" if reasons else "routine"), reasons


def _git(cwd: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout


def _untracked_line_count(path: Path) -> int:
    try:
        data = path.read_bytes()
    except (OSError, ValueError):
        return 0
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def collect_diff(cwd: str | Path) -> DiffSummary:
    """Return the working tree diff from HEAD, including untracked files."""
    root = Path(cwd).resolve()
    try:
        top_level = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip())
        numstat = _git(top_level, "diff", "--numstat", "--no-renames", "HEAD", "--")
        untracked = _git(
            top_level,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        )
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        return DiffSummary(0, 0, ())

    added = 0
    removed = 0
    files: set[str] = set()
    for raw_line in numstat.decode("utf-8", errors="replace").splitlines():
        parts = raw_line.split("\t", 2)
        if len(parts) != 3:
            continue
        raw_added, raw_removed, filename = parts
        files.add(filename)
        if raw_added.isdigit():
            added += int(raw_added)
        if raw_removed.isdigit():
            removed += int(raw_removed)

    for raw_name in untracked.split(b"\0"):
        if not raw_name:
            continue
        filename = raw_name.decode("utf-8", errors="replace")
        files.add(filename)
        added += _untracked_line_count(top_level / filename)

    return DiffSummary(added, removed, tuple(sorted(files)))
