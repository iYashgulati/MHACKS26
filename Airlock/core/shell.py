from __future__ import annotations

import os
import re
import shlex
from pathlib import PurePosixPath
from urllib.parse import urlparse

from Airlock.core.action import ShellInvocation


CONTROL_OPERATORS = {"|", "||", "&&", ";", "&", "(", ")"}
REDIRECT_OPERATORS = {">", ">>", "<", "<<", "2>", "2>>"}
URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def analyze_shell(command: str) -> tuple[
    tuple[ShellInvocation, ...], tuple[str, ...], tuple[str, ...], frozenset[str]
]:
    """Analyze a shell string without ever executing or rewriting it."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;()<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return (), (), tuple(URL_RE.findall(command)), frozenset({"unparseable_shell"})

    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in CONTROL_OPERATORS:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)

    invocations: list[ShellInvocation] = []
    paths: set[str] = set()
    urls = set(URL_RE.findall(command))
    facts: set[str] = set()

    for segment in segments:
        cleaned: list[str] = []
        next_is_redirect = False
        for token in segment:
            if next_is_redirect:
                paths.add(_normalize_path(token))
                next_is_redirect = False
            elif token in REDIRECT_OPERATORS or set(token) <= {">", "<"}:
                next_is_redirect = True
            else:
                cleaned.append(token)

        while cleaned and ASSIGNMENT_RE.match(cleaned[0]):
            cleaned.pop(0)
        if not cleaned:
            continue

        executable = os.path.basename(cleaned[0]).lower()
        arguments = tuple(cleaned[1:])
        lowered = tuple(item.lower() for item in arguments)
        invocations.append(ShellInvocation(executable, arguments, " ".join(segment)))

        if executable in {"sudo", "doas", "su"}:
            facts.add("privilege_escalation")
        if executable == "git" and "push" in lowered:
            facts.add("git_push")
            if any(item == "-f" or item.startswith("--force") for item in lowered):
                facts.add("force_push")
        if executable == "git" and "reset" in lowered and "--hard" in lowered:
            facts.add("hard_reset")
        if executable in {"npm", "pnpm", "yarn", "pip", "pip3", "poetry", "brew"}:
            if {"install", "add"}.intersection(lowered):
                facts.add("dependency_install")
        if executable == "rm":
            recursive = any(
                item in {"-r", "-rf", "-fr", "--recursive"}
                or (item.startswith("-") and "r" in item[1:])
                for item in lowered
            )
            if recursive:
                facts.add("recursive_delete")
                targets = [item for item in arguments if not item.startswith("-")]
                if any(item in {"/", "/*", "~", "$HOME", "${HOME}"} for item in targets):
                    facts.add("recursive_delete_root")
        if _is_production_command(executable, lowered):
            facts.add("production_command")

        for argument in arguments:
            if _looks_like_path(argument):
                paths.add(_normalize_path(argument))

    if re.search(
        r"\b(curl|wget)\b[^\n]*(?:\||&&|;)\s*(?:ba|z|fi)?sh\b",
        command,
        re.IGNORECASE,
    ):
        facts.add("download_and_execute")
    if urls:
        facts.add("external_network")
    if invocations and all(_is_safe_invocation(item) for item in invocations):
        facts.add("safe_shell")

    return tuple(invocations), tuple(sorted(paths)), tuple(sorted(urls)), frozenset(facts)


def extract_patch_paths(patch: str) -> tuple[str, ...]:
    paths: set[str] = set()
    for line in patch.splitlines():
        if line.startswith(("*** Add File: ", "*** Update File: ", "*** Delete File: ")):
            paths.add(_normalize_path(line.split(": ", 1)[1]))
        elif line.startswith(("+++ b/", "--- a/")):
            paths.add(_normalize_path(line[6:]))
    return tuple(sorted(paths))


def extract_urls(value: object) -> tuple[str, ...]:
    return tuple(sorted(set(URL_RE.findall(value)))) if isinstance(value, str) else ()


def network_hosts(urls: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({urlparse(url).hostname or "" for url in urls if urlparse(url).hostname}))


def _normalize_path(value: str) -> str:
    value = value.strip().replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    try:
        return str(PurePosixPath(value))
    except ValueError:
        return value


def _looks_like_path(value: str) -> bool:
    if value.startswith(("-", "http://", "https://")):
        return False
    return "/" in value or value.startswith(".") or bool(re.search(r"\.[A-Za-z0-9]{1,8}$", value))


def _is_production_command(executable: str, args: tuple[str, ...]) -> bool:
    words = {executable, *args}
    return bool(
        words.intersection({"deploy", "release", "publish"})
        or (executable == "terraform" and "apply" in args)
        or (executable == "kubectl" and {"apply", "delete"}.intersection(args))
        or (executable == "docker" and "push" in args)
    )


def _is_safe_invocation(invocation: ShellInvocation) -> bool:
    executable = invocation.executable
    args = tuple(item.lower() for item in invocation.arguments)
    if executable in {"ls", "pwd", "pytest"}:
        return True
    if executable == "git" and args and args[0] in {"status", "diff", "log"}:
        return True
    if executable in {"python", "python3"} and len(args) >= 2:
        return args[0] == "-m" and args[1] in {"pytest", "unittest"}
    if executable == "npm":
        return bool(args and (args[0] == "test" or args[:2] == ("run", "test")))
    if executable in {"cargo", "go"}:
        return bool(args and args[0] == "test")
    return False
