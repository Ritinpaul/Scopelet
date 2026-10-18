"""
Unified Isolated Execution Runner facade.
Seamlessly routes execution to Docker container isolation or hardened local sandbox
with persistent SQLite caching.
"""

from pathlib import Path
from typing import Optional, Dict, Literal
from .result import ExecutionResult
from .cache import ExecutionCache, compute_tree_hash
from .local_runner import LocalIsolatedRunner
from .docker_runner import DockerRunner


class IsolatedRunner:
    """
    Facade managing deterministic test execution, backend selection,
    and candidate result caching.
    """

    def __init__(
        self,
        cache_db_path: Optional[Path] = None,
        prefer_docker: bool = True,
    ):
        self.prefer_docker = prefer_docker
        default_db = Path.cwd() / ".scopelet" / "cache.db"
        self.cache = ExecutionCache(cache_db_path or default_db)
        self.local_runner = LocalIsolatedRunner()
        self.docker_runner = DockerRunner()

    def run(
        self,
        command: str,
        cwd: Path,
        env_override: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        use_cache: bool = True,
        force_backend: Optional[Literal["docker", "local_sandbox"]] = None,
    ) -> ExecutionResult:
        """
        Executes a command under isolation, checking the SQLite cache first.
        """
        target_cwd = cwd.resolve()
        tree_hash = compute_tree_hash(target_cwd)

        # Determine backend
        backend_name: Literal["docker", "local_sandbox"]
        if force_backend:
            backend_name = force_backend
        elif self.prefer_docker and self.docker_runner.is_available():
            backend_name = "docker"
        else:
            backend_name = "local_sandbox"

        # Check cache
        env_hash = "default"
        if env_override:
            import hashlib
            env_hash = hashlib.sha256(str(sorted(env_override.items())).encode()).hexdigest()[:12]

        if use_cache:
            cached_result = self.cache.get(
                tree_hash=tree_hash,
                command=command,
                env_hash=env_hash,
                backend=backend_name,
            )
            if cached_result:
                return cached_result

        # Execute on selected backend
        if backend_name == "docker":
            result = self.docker_runner.run(
                command=command,
                cwd=target_cwd,
                env_override=env_override,
                timeout=timeout,
            )
        else:
            result = self.local_runner.run(
                command=command,
                cwd=target_cwd,
                env_override=env_override,
                timeout=timeout,
            )

        # Store in cache
        if use_cache:
            self.cache.put(result, env_hash=env_hash)

        return result
