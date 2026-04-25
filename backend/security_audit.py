"""
security_audit.py - dependency and third-party asset audit helpers
"""
from __future__ import annotations

import re
import os
import subprocess
import sys
from pathlib import Path


EXTERNAL_URL_RE = re.compile(r"https://[^\s\"')>]+")


def _scan_external_assets(frontend_root):
    assets = {}
    for file_path in frontend_root.rglob("*"):
        if file_path.suffix.lower() not in {".html", ".css", ".js"}:
            continue
        matches = sorted(set(EXTERNAL_URL_RE.findall(file_path.read_text(encoding="utf-8"))))
        if matches:
            assets[file_path] = matches
    return assets


def _requirements_are_pinned(requirements_path):
    unpinned = []
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            unpinned.append(line)
    return unpinned


def build_security_audit_report(project_root, python_executable=None):
    project_root = Path(project_root)
    backend_root = project_root / "backend"
    frontend_root = project_root / "frontend"
    requirements_path = backend_root / "requirements.txt"
    cache_dir = backend_root / ".cache" / "pip-audit"
    temp_dir = backend_root / ".cache" / "tmp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    python_executable = python_executable or sys.executable

    lines = []
    exit_code = 0

    unpinned = _requirements_are_pinned(requirements_path)
    if unpinned:
        exit_code = 1
        lines.append("Unpinned Python dependencies:")
        for item in unpinned:
            lines.append(f" - {item}")
    else:
        lines.append("All Python dependencies are pinned in requirements.txt.")

    assets = _scan_external_assets(frontend_root)
    lines.append("")
    lines.append("External frontend assets:")
    if not assets:
        lines.append(" - none")
    else:
        for file_path, urls in sorted(assets.items()):
            rel_path = file_path.relative_to(project_root)
            lines.append(f" - {rel_path}")
            for url in urls:
                lines.append(f"   {url}")

    lines.append("")
    lines.append("pip-audit results:")
    env = dict(
        os.environ,
        TMPDIR=str(temp_dir),
        TEMP=str(temp_dir),
        TMP=str(temp_dir),
    )
    audit_proc = subprocess.run(
        [
            python_executable,
            "-m",
            "pip_audit",
            "--cache-dir",
            str(cache_dir),
            "--no-deps",
            "--disable-pip",
            "-r",
            str(requirements_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(backend_root),
        env=env,
    )
    output = (audit_proc.stdout or "").strip() or (audit_proc.stderr or "").strip()
    lines.append(output or "No output from pip-audit.")
    if audit_proc.returncode != 0:
        exit_code = audit_proc.returncode

    return "\n".join(lines), exit_code
