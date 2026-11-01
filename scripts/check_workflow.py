#!/usr/bin/env python3
"""Check indexed governance files without printing their contents or using a network."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 4 * 1024 * 1024
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b"),
    re.compile(rb"\bAIza[A-Za-z0-9_-]{35}\b"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)
LINK = re.compile(r"!?\[[^\]\n]*\]\(<?([^\s)<>]+)>?\)")


def git(*args: str) -> bytes:
    """Read Git metadata/index only; never execute source or load credentials."""
    return subprocess.check_output(["git", *args], cwd=ROOT)


def forbidden_path(name: str) -> bool:
    """Reject local credentials/artifacts even if force-added past .gitignore."""
    path = PurePosixPath(name)
    base = path.name
    if path.parts[0] in {".private", "mini-assistant", "research", "lab", "tmp", "photo editor"}:
        return True
    if any(part in {"secrets", ".credentials", ".spotify-credentials"} for part in path.parts):
        return True
    if base == ".env" or (base.startswith(".env.") and base != ".env.example"):
        return True
    if base in {"config.toml", "credentials.json", "authorized_keys"}:
        return True
    return base.startswith(("id_rsa", "id_ed25519")) or base.endswith(
        (".key", ".pem", ".pcap", ".pcapng", ".wav", ".mp3", ".onnx", ".gguf", ".img", ".bin", ".zip", ".tar.gz")
    )


def inspect_blob(name: str, data: bytes) -> list[str]:
    """Return generic reasons only, never matched credentials or payloads."""
    errors = []
    if forbidden_path(name):
        errors.append("private/local/artifact path is not allowed in this repository")
    if len(data) > MAX_BYTES:
        errors.append("file exceeds 4 MiB; review and store artifacts separately")
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        errors.append("possible credential detected; inspect locally, do not print it")
    return errors


def broken_links(name: str, data: bytes, indexed: set[str]) -> list[str]:
    """Check relative file links against the Git index, excluding fenced code."""
    content = re.sub(r"^(```|~~~).*?^\1[^\n]*$", "", data.decode("utf-8"), flags=re.M | re.S)
    errors = []
    for target in LINK.findall(content):
        link = urlsplit(target)
        if link.scheme or link.netloc or not link.path:
            continue
        # Normalize .. lexically; do not follow working-tree symlinks.
        parts = list(PurePosixPath(name).parent.parts)
        valid = not link.path.startswith("/")
        for part in PurePosixPath(unquote(link.path)).parts:
            if part == "..":
                if parts:
                    parts.pop()
                else:
                    valid = False
            elif part != ".":
                parts.append(part)
        resolved = "/".join(parts)
        if not valid or not (
            resolved in indexed or any(item.startswith(resolved + "/") for item in indexed)
        ):
            errors.append("relative Markdown link has no indexed target")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="check changed index entries only")
    args = parser.parse_args()
    indexed = {name.decode() for name in git("ls-files", "-z").split(b"\0") if name}
    names = indexed
    if args.staged:
        names = {
            name.decode()
            for name in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
            if name
        }
    # Deleting/renaming a target can break an unchanged document. Validate all
    # remaining Markdown links, even when only changed blobs need secret checks.
    checked = names | {name for name in indexed if name.endswith(".md")}
    failures = []
    for name in sorted(checked):
        # Reject unexpected paths before opening their potentially sensitive blobs.
        if forbidden_path(name):
            failures.append((name, "private/local/artifact path is not allowed in this repository"))
            continue
        size = int(git("cat-file", "-s", ":" + name))
        if size > MAX_BYTES:
            failures.append((name, "file exceeds 4 MiB"))
            continue
        data = git("show", ":" + name)
        errors = inspect_blob(name, data) if name in names else []
        if name.endswith(".md"):
            try:
                errors.extend(broken_links(name, data, indexed))
            except (UnicodeDecodeError, ValueError):
                errors.append("invalid UTF-8 Markdown or link")
        failures.extend((name, reason) for reason in errors)
    for name, reason in failures:
        print(f"FAIL {name}: {reason}", file=sys.stderr)
    if failures:
        return 1
    print(f"Workflow checks passed ({len(checked)} indexed files; no network/device access).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
