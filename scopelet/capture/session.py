"""
Persistence and session management for captured bug reproductions.
Saves session.json, stdout.log, stderr.log, and failure.json.
"""

from pathlib import Path
from ..models.session import SessionInfo
from ..models.failure import NormalizedFailure


class SessionStore:
    """
    Manages the .scopelet directory structure for recording bug reproduction sessions.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def save_session(
        self,
        session_info: SessionInfo,
        stdout: str,
        stderr: str,
        failure: NormalizedFailure,
    ) -> Path:
        """
        Saves all capture artifacts to disk under the output directory.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 1. stdout.log
        stdout_file = self.output_dir / "stdout.log"
        stdout_file.write_text(stdout, encoding="utf-8")

        # 2. stderr.log
        stderr_file = self.output_dir / "stderr.log"
        stderr_file.write_text(stderr, encoding="utf-8")

        # 3. failure.json
        failure_file = self.output_dir / "failure.json"
        failure_file.write_text(failure.model_dump_json(indent=2), encoding="utf-8")

        # 4. session.json
        session_file = self.output_dir / "session.json"
        session_file.write_text(session_info.model_dump_json(indent=2), encoding="utf-8")

        return self.output_dir
