"""Check tracked files and reachable Git history without printing secret values.

This is a small project-specific guard, not a replacement for GitHub secret scanning.
Only Git-tracked files are read; local .env, databases and logs are never uploaded.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "Telegram bot token": re.compile(rb"\b\d{5,15}:[A-Za-z0-9_-]{30,}\b"),
    "GitHub token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "credential in URL": re.compile(rb"\b(?:https?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s/:]+:[^\s/@]+@"),
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def forbidden_path(name: str) -> bool:
    path = PurePosixPath(name)
    basename = path.name.lower()
    if basename.startswith(".env") and basename != ".env.example":
        return True
    if basename in {"id_rsa", "id_ed25519", "credentials.json", "service-account.json"}:
        return True
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".log", ".pem", ".key", ".p12", ".pfx", ".session"}:
        return True
    return any(part in {".venv", "venv", "logs", "temp", "data", "backups", ".codex", ".agents"} for part in path.parts)


def check_content(name: str, content: bytes, revision: str = "working tree") -> list[str]:
    findings = []
    for label, pattern in PATTERNS.items():
        for match in pattern.finditer(content):
            line = content.count(b"\n", 0, match.start()) + 1
            findings.append(f"{revision}: {name}:{line}: {label} (value hidden)")
    return findings


def scan_worktree() -> tuple[int, list[str]]:
    names = git("ls-files", "-z").decode().split("\0")
    findings = []
    count = 0
    for name in filter(None, names):
        if forbidden_path(name):
            findings.append(f"working tree: {name}: private/runtime path is tracked")
        path = ROOT / name
        if path.is_file() and not path.is_symlink():
            findings.extend(check_content(name, path.read_bytes()))
            count += 1
    return count, findings


def scan_history() -> tuple[int, list[str]]:
    # Check names from every commit as well as unique blob content: renaming an
    # unchanged blob to .env must not evade the private-path check.
    names = git("log", "--all", "--format=", "--name-only", "-z").decode().split("\0")
    findings = [
        f"history: {name}: private/runtime path was committed"
        for name in sorted({name.strip() for name in names if name.strip()})
        if forbidden_path(name)
    ]
    objects = {}
    for line in git("rev-list", "--objects", "--all").decode().splitlines():
        oid, _, name = line.partition(" ")
        objects[oid] = name or "<commit metadata>"
    count = 0
    # One persistent process keeps the complete-history audit fast on Windows.
    with subprocess.Popen(
        ["git", "cat-file", "--batch"], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    ) as process:
        assert process.stdin is not None and process.stdout is not None
        for oid, name in objects.items():
            process.stdin.write(oid.encode() + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().split()
            size = int(header[2])
            content = process.stdout.read(size)
            process.stdout.read(1)
            if header[1] in {b"blob", b"commit", b"tag"}:
                count += 1
                findings.extend(check_content(name, content, oid[:12]))
        process.stdin.close()
        process.wait()
    return count, findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Also check every reachable Git revision")
    args = parser.parse_args()
    files, findings = scan_worktree()
    print(f"Checked {files} tracked files.")
    if args.history:
        objects, historical = scan_history()
        findings.extend(historical)
        print(f"Checked {objects} historical content objects across all local refs.")
    for finding in sorted(set(findings)):
        print(finding)
    if findings:
        print("Review required. No secret values have been printed.")
        return 1
    print("No known credential patterns or private/runtime paths found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
