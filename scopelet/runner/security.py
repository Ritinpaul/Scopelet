"""
Security parameters and resource limit configurations for container and process isolation.
"""

from typing import Dict, Any

# Strict Docker security policy
DOCKER_SECURITY_CONFIG: Dict[str, Any] = {
    "network_mode": "none",
    "mem_limit": "512m",
    "nano_cpus": 500_000_000,  # 0.5 CPUs
    "pids_limit": 256,
    "read_only": True,
    "tmpfs": {
        "/tmp": "rw,noexec,nosuid,size=64m",
        "/home/node/.npm": "rw,noexec,nosuid,size=32m",
        "/app/node_modules/.cache": "rw,noexec,nosuid,size=64m",
    },
    "user": "node",
    "security_opt": ["no-new-privileges"],
    "cap_drop": ["ALL"],
}

# Local process isolation policy
LOCAL_PROCESS_POLICY = {
    "default_timeout_seconds": 60,
    "max_timeout_seconds": 300,
    "max_output_bytes": 10 * 1024 * 1024,  # 10 MB limit to avoid giant memory spikes
}
