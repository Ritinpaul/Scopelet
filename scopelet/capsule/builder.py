"""
Capsule builder assembling self-contained reproduction workspaces, manifests, and task specs.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from ..reducer.candidate import CandidateState
from .models import CapsuleFile, CapsuleManifest, TaskSpec
from .hasher import compute_capsule_hash


class CapsuleBuilder:
    """
    Assembles minimal reproducible capsule directories and writes metadata specs.
    """

    def __init__(self, default_runtime: Optional[Dict[str, str]] = None):
        self.default_runtime = default_runtime or {"node": "22"}

    def build(
        self,
        output_dir: Path,
        state: CandidateState,
        title: str,
        command: str,
        failure_fingerprint: str,
        failure_description: Optional[str] = None,
        allowed_changes: Optional[List[str]] = None,
        runtime: Optional[Dict[str, str]] = None,
    ) -> CapsuleManifest:
        """
        Assembles all active source files, writes capsule.json, task.yaml, and README.md.
        """
        target = output_dir.resolve()
        target.mkdir(parents=True, exist_ok=True)

        # 1. Materialize source files into output directory
        state.materialize(target, link_node_modules=False)

        # 2. Index all materialized source files and compute hashes
        capsule_files: List[CapsuleFile] = []
        for file_path in sorted(target.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(target).as_posix()
                if rel in ("capsule.json", "task.yaml", "README.md") or rel.startswith("node_modules/"):
                    continue

                content = file_path.read_bytes()
                file_hash = hashlib.sha256(content).hexdigest()
                capsule_files.append(
                    CapsuleFile(
                        path=rel,
                        hash=file_hash,
                        size_bytes=len(content),
                    )
                )

        # 3. Determine allowed changes if not explicitly specified
        # (Exclude test suites and configuration files by default)
        effective_allowed: List[str]
        if allowed_changes is not None:
            effective_allowed = sorted(allowed_changes)
        else:
            effective_allowed = []
            for cf in capsule_files:
                p = cf.path
                if (
                    p.startswith("src/")
                    and p.endswith((".ts", ".js", ".tsx", ".jsx"))
                    and not p.endswith(".test.ts")
                ):
                    effective_allowed.append(p)
            effective_allowed.sort()

        effective_runtime = runtime or self.default_runtime

        # 4. Compute deterministic capsule hash
        capsule_hash = compute_capsule_hash(
            files=capsule_files,
            command=command,
            runtime=effective_runtime,
            allowed_changes=effective_allowed,
        )

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 5. Build manifest
        manifest = CapsuleManifest(
            schema_version="1.0",
            capsule_hash=capsule_hash,
            title=title,
            created_at=now_utc,
            runtime=effective_runtime,
            command=command,
            allowed_changes=effective_allowed,
            expected={"test_should_pass": True},
            network_allowed=False,
            failure_fingerprint=failure_fingerprint,
            failure_description=failure_description,
            files=capsule_files,
        )

        # Write capsule.json
        manifest_json_path = target / "capsule.json"
        manifest_json_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # 6. Build and write task.yaml
        task_spec = TaskSpec(
            title=title,
            command=command,
            failure_description=failure_description,
            allowed_changes=effective_allowed,
            expected={"test_should_pass": True},
            runtime=effective_runtime,
            network={"allowed": False},
        )
        task_yaml_path = target / "task.yaml"
        task_yaml_path.write_text(
            yaml.dump(task_spec.model_dump(), sort_keys=False),
            encoding="utf-8",
        )

        # 7. Write README.md with reproduction instructions
        readme_path = target / "README.md"
        readme_content = self._generate_readme(manifest)
        readme_path.write_text(readme_content, encoding="utf-8")

        return manifest

    def _generate_readme(self, manifest: CapsuleManifest) -> str:
        changes_list = "\n".join(f"- `{f}`" for f in manifest.allowed_changes)
        return (
            f"# Scopelet Reproduction Capsule: {manifest.title}\n\n"
            f"**Capsule Hash:** `{manifest.capsule_hash}`\n"
            f"**Target Failure Fingerprint:** `{manifest.failure_fingerprint}`\n"
            f"**Verification Command:** `{manifest.command}`\n\n"
            f"## Instructions\n\n"
            f"1. Run the test command to verify reproduction of the defect:\n"
            f"   ```bash\n"
            f"   {manifest.command}\n"
            f"   ```\n"
            f"2. Implement your fix strictly within the allowed files:\n"
            f"{changes_list}\n\n"
            f"3. Verify that all tests pass after your modification.\n"
        )
