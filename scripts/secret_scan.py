#!/usr/bin/env python3
"""
Secret Scan Utility (Must-Have 7).
Scans git-tracked files, log captures, and active Docker container logs
for sensitive credentials (API keys, tokens, auth headers, passwords).
Fails (exit 1) if any secret pattern or specific prohibited token is found unmasked.
"""

import os
import sys
import re
import json
import subprocess
from datetime import datetime, timezone
from typing import List, Dict, Any

# Prohibited patterns indicating leaked secrets or unmasked tokens
SECRET_PATTERNS = [
    (r'(?i)authorization:\s*bearer\s+[a-zA-Z0-9_\-\.]{15,}', "Authorization Bearer token"),
    (r'(?i)api[_-]?key["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-\.]{20,})["\']', "API Key assignment"),
    (r'(?i)secret["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-\.]{20,})["\']', "Secret assignment"),
    (r'(?i)password["\']?\s*[:=]\s*["\']([^"\'\s]{8,})["\']', "Hardcoded password"),
    (r'-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----', "Private key header")
]

# Patterns or files to ignore (e.g. this scanner script itself, git history metadata, binary assets)
IGNORED_FILES = {
    "scripts/secret_scan.py",
    "scripts\\secret_scan.py",
    ".env.example",
    "lemmy/lemmy.hjson",
    "lemmy\\lemmy.hjson"
}

IGNORED_EXTENSIONS = {
    ".pyc", ".png", ".jpg", ".jpeg", ".ico", ".pdf", ".db", ".sqlite", ".xlsx", ".zip"
}


def get_git_tracked_files() -> List[str]:
    """Retrieve list of files currently tracked by git."""
    try:
        res = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except Exception as exc:
        print(f"Warning: Failed to run git ls-files: {exc}. Scanning workspace directory instead.", file=sys.stderr)
        files = []
        for root, _, filenames in os.walk("."):
            if ".git" in root or ".venv" in root:
                continue
            for fname in filenames:
                files.append(os.path.relpath(os.path.join(root, fname), "."))
        return files


def scan_file_content(filepath: str, known_secrets: List[str] = None) -> List[Dict[str, Any]]:
    """Scan an individual file for secret patterns or specific known secret strings."""
    norm_path = filepath.replace("\\", "/")
    if any(norm_path.endswith(ig) for ig in IGNORED_FILES):
        return []
    if any(norm_path.endswith(ext) for ext in IGNORED_EXTENSIONS):
        return []

    if not os.path.exists(filepath):
        return []

    findings = []
    is_test_file = norm_path.startswith("tests/")

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                # Check for specific known test secrets if passed
                if known_secrets:
                    for s in known_secrets:
                        if s and len(s) >= 8 and s in line:
                            findings.append({
                                "file": filepath,
                                "line_number": line_no,
                                "type": "Specific Known Secret Match",
                                "snippet": line[:100].strip()
                            })

                # Check general regex patterns in non-test files
                if not is_test_file:
                    for pattern, desc in SECRET_PATTERNS:
                        if re.search(pattern, line):
                            # Verify it's not a documentation dummy or test placeholder
                            if any(safe in line for safe in ["example", "dummy", "placeholder", "xxx", "mock", "test_key", "valid_test_key"]):
                                continue
                            findings.append({
                                "file": filepath,
                                "line_number": line_no,
                                "type": desc,
                                "snippet": line[:100].strip()
                            })
    except Exception as exc:
        print(f"Error reading {filepath}: {exc}", file=sys.stderr)

    return findings


def scan_docker_logs() -> List[Dict[str, Any]]:
    """Scan Docker container logs for active IncuBrix containers."""
    findings = []
    containers = ["incubrix-api", "incubrix-mock"]
    for c_name in containers:
        try:
            res = subprocess.run(["docker", "logs", "--tail", "500", c_name], capture_output=True, text=True)
            if res.returncode == 0:
                for line_no, line in enumerate(res.stdout.splitlines(), 1):
                    for pattern, desc in SECRET_PATTERNS:
                        if re.search(pattern, line):
                            if any(safe in line for safe in ["example", "dummy", "mock"]):
                                continue
                            findings.append({
                                "source": f"docker:{c_name}",
                                "line_number": line_no,
                                "type": desc,
                                "snippet": line[:100].strip()
                            })
        except Exception:
            # Docker might not be running in all environments
            pass
    return findings


def run_secret_scan(known_secrets: List[str] = None) -> Dict[str, Any]:
    """Execute complete secret scan and save report."""
    os.makedirs("outputs/test_runs", exist_ok=True)
    tracked_files = get_git_tracked_files()

    all_findings = []
    for f in tracked_files:
        file_findings = scan_file_content(f, known_secrets=known_secrets)
        all_findings.extend(file_findings)

    docker_findings = scan_docker_logs()
    all_findings.extend(docker_findings)

    report = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "total_files_scanned": len(tracked_files),
        "total_findings": len(all_findings),
        "clean": len(all_findings) == 0,
        "findings": all_findings
    }

    report_path = "outputs/test_runs/secret_scan_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def main():
    report = run_secret_scan()
    print(f"Secret Scan complete: Scanned {report['total_files_scanned']} files.")
    if report["clean"]:
        print("RESULT: CLEAN - No leaked secrets or credentials detected.")
        sys.exit(0)
    else:
        print(f"RESULT: FAILED - Found {report['total_findings']} secret findings:")
        for finding in report["findings"]:
            print(f"  - [{finding.get('file') or finding.get('source')}:{finding.get('line_number')}] {finding['type']}: {finding['snippet']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
