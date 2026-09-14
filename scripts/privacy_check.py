from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "业务编号": re.compile(r"\bBX\d{8,}\b", re.IGNORECASE),
    "Windows 用户路径": re.compile(r"\b[A-Za-z]:\\Users\\[^\\\r\n]+", re.IGNORECASE),
    "中国大陆身份证号": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "中国大陆手机号": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "疑似银行卡号": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    "电子邮箱": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "疑似密钥": re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
    "私钥": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
}
SKIP_PATHS = {"scripts/privacy_check.py"}


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _git(*args: str, check: bool = True) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).stdout


def _decode(payload: bytes) -> str | None:
    if b"\0" in payload[:8192]:
        return None
    return payload.decode("utf-8", errors="replace")


def _paths(scope: str) -> list[str]:
    if scope == "tracked":
        payload = _git("ls-files", "-z")
    elif scope == "staged":
        payload = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        tracked = _git("ls-files", "-z")
        untracked = _git("ls-files", "--others", "--exclude-standard", "-z")
        payload = tracked + untracked
    return sorted({item.decode("utf-8") for item in payload.split(b"\0") if item})


def _content(path: str, staged: bool) -> bytes:
    if staged:
        return _git("show", f":{path}")
    return (ROOT / path).read_bytes()


def _scan(label: str, path: str, payload: bytes) -> list[str]:
    if path in SKIP_PATHS:
        return []
    text = _decode(payload)
    if text is None:
        return []
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in PATTERNS.items():
            if pattern.search(line):
                findings.append(f"{label}:{path}:{line_number}: {kind}")
    return findings


def scan_worktree(scope: str) -> list[str]:
    findings: list[str] = []
    for path in _paths(scope):
        try:
            findings.extend(_scan(scope, path, _content(path, scope == "staged")))
        except (OSError, subprocess.CalledProcessError):
            continue
    return findings


def scan_history() -> list[str]:
    findings: list[str] = []
    commits = _git("rev-list", "--all").decode().splitlines()
    for commit in commits:
        paths = _git("ls-tree", "-r", "--name-only", "-z", commit).split(b"\0")
        for raw_path in paths:
            if not raw_path:
                continue
            path = raw_path.decode("utf-8")
            try:
                payload = _git("show", f"{commit}:{path}")
            except subprocess.CalledProcessError:
                continue
            findings.extend(_scan(commit[:12], path, payload))
    return findings


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    parser = argparse.ArgumentParser(description="扫描可能误提交的报销隐私和凭据")
    parser.add_argument("--scope", choices=("tracked", "staged", "all", "history"), default="all")
    args = parser.parse_args(argv)
    findings = scan_history() if args.scope == "history" else scan_worktree(args.scope)
    if findings:
        print("隐私扫描未通过：", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"隐私扫描通过（scope={args.scope}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
