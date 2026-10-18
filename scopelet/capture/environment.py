"""
Environment inspection and safe metadata capture.
Strict allowlist policy ensures credentials, tokens, and private env variables are never captured.
"""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

# Strict allowlist of environment variable names that are safe to record.
# Anything not explicitly listed here is discarded.
ALLOWED_ENV_VARS = {
    "CI",
    "LANG",
    "LC_ALL",
    "NODE_ENV",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TERM",
    "TZ",
}


def get_safe_environment() -> Dict[str, str]:
    """
    Returns only allowlisted environment variables from the current process environment.
    All secrets, tokens, API keys, and custom env vars are excluded.
    """
    safe_env: dict[str, str] = {}
    for key, val in os.environ.items():
        if key.upper() in ALLOWED_ENV_VARS:
            safe_env[key] = val
    return safe_env


def get_runtime_info() -> Dict[str, str]:
    """
    Captures versions of active runtimes (Node, npm, Python).
    """
    info: dict[str, str] = {}

    if shutil.which("node"):
        try:
            res = subprocess.run(["node", "-v"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                info["node"] = res.stdout.strip()
        except Exception:
            pass

    if shutil.which("npm"):
        try:
            res = subprocess.run(["npm", "-v"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                info["npm"] = res.stdout.strip()
        except Exception:
            pass

    import sys
    info["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return info


def get_lockfile_hash(cwd: Path) -> Optional[str]:
    """
    Computes a SHA-256 hash of the project lockfile (package-lock.json, pnpm-lock.yaml, yarn.lock).
    """
    candidates = ["package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"]
    for fname in candidates:
        lockfile = cwd / fname
        if lockfile.exists() and lockfile.is_file():
            content = lockfile.read_bytes()
            return hashlib.sha256(content).hexdigest()
    return None


def get_git_commit(cwd: Path) -> Optional[str]:
    """
    Returns the current git commit SHA of the repository in cwd, if available.
    """
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None
