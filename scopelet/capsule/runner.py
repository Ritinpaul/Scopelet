"""
Capsule runner for executing Scopelet capsules standalone in isolated environments.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional

from ..runner import IsolatedRunner, ExecutionResult
from .packager import CapsulePackager
from .models import CapsuleManifest
from ..reducer.candidate import link_directory


class CapsuleRunner:
    """
    Executes a standalone .scopelet archive or capsule directory under isolation.
    """

    def __init__(self, runner: Optional[IsolatedRunner] = None):
        self.runner = runner or IsolatedRunner(prefer_docker=False)

    def run(
        self,
        capsule_target: Path,
        working_dir: Optional[Path] = None,
        timeout: int = 60,
        dependency_dir: Optional[Path] = None,
    ) -> tuple[CapsuleManifest, ExecutionResult]:
        """
        Extracts capsule if needed, verifies structure, executes verification command under isolation.
        """
        target = capsule_target.resolve()
        is_temp_ws = False

        if target.is_file():
            # Extract archive to temporary workspace
            ws = working_dir or Path(tempfile.mkdtemp(prefix="scopelet_capsule_run_"))
            CapsulePackager.unpack(target, ws)
            is_temp_ws = working_dir is None
        elif target.is_dir():
            ws = target
        else:
            raise FileNotFoundError(f"Capsule target not found: {target}")

        try:
            manifest_file = ws / "capsule.json"
            if not manifest_file.exists():
                raise FileNotFoundError(f"Invalid capsule: missing capsule.json in {ws}")

            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest = CapsuleManifest.model_validate(manifest_data)

            # Ensure node_modules exists for execution
            if not (ws / "node_modules").exists() and dependency_dir:
                dep_nm = dependency_dir / "node_modules"
                if dep_nm.exists():
                    link_directory(dep_nm, ws / "node_modules")

            # Execute command inside isolated workspace
            exec_result = self.runner.run(
                command=manifest.command,
                cwd=ws,
                timeout=timeout,
                use_cache=False,
            )

            return manifest, exec_result
        finally:
            if is_temp_ws and working_dir is None:
                try:
                    import shutil
                    shutil.rmtree(ws, ignore_errors=True)
                except Exception:
                    pass
