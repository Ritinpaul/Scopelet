"""
Unit tests for the behavior-preserving delta-debugging reducer engine.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scopelet.reducer.candidate import CandidateState
from scopelet.reducer.cache import ReducerCache
from scopelet.reducer.oracle import ReducerOracle, OracleVerdict, OracleResult
from scopelet.reducer.ddmin import DeltaDebuggingReducer
from scopelet.reducer.progress import ReducerProgress
from scopelet.runner.result import ExecutionResult


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Creates a temporary miniature repository for testing candidate state operations."""
    (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")
    (tmp_path / "src" / "admin").mkdir(parents=True)
    (tmp_path / "src" / "admin" / "users.ts").write_text("export const user = 1;\n", encoding="utf-8")
    (tmp_path / "src" / "billing").mkdir(parents=True)
    (tmp_path / "src" / "billing" / "invoice.ts").write_text("export const invoice = 2;\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "tests" / "test.ts").write_text("import { invoice } from '../src/billing/invoice';\n", encoding="utf-8")
    return tmp_path


def test_candidate_state_discovery(sample_repo: Path):
    state = CandidateState.from_directory(sample_repo)
    assert "package.json" in state.active_files
    assert "src/admin/users.ts" in state.active_files
    assert "src/billing/invoice.ts" in state.active_files
    assert "tests/test.ts" in state.active_files
    assert state.file_count() == 4
    assert state.loc() > 0


def test_candidate_state_tree_hash_determinism(sample_repo: Path):
    state1 = CandidateState.from_directory(sample_repo)
    state2 = CandidateState.from_directory(sample_repo)
    assert state1.compute_tree_hash() == state2.compute_tree_hash()

    pruned = state1.prune_file("src/admin/users.ts")
    assert pruned.compute_tree_hash() != state1.compute_tree_hash()
    assert pruned.file_count() == 3


def test_candidate_state_materialize(sample_repo: Path, tmp_path: Path):
    state = CandidateState.from_directory(sample_repo)
    target = tmp_path / "materialized"

    state.materialize(target)
    assert (target / "package.json").exists()
    assert (target / "src" / "admin" / "users.ts").exists()

    # Prune a file and materialize again to verify cleanup
    pruned = state.prune_file("src/admin/users.ts")
    pruned.materialize(target)
    assert not (target / "src" / "admin" / "users.ts").exists()
    assert (target / "src" / "billing" / "invoice.ts").exists()


def test_reducer_cache(tmp_path: Path):
    db_file = tmp_path / "cache.db"
    cache = ReducerCache(db_file)

    assert cache.get("hash_1", "npm test") is None
    assert cache.stats()["misses"] == 1

    cache.put(
        tree_hash="hash_1",
        command="npm test",
        verdict=OracleVerdict.MATCH.value,
        fingerprint="fp_123",
        exit_code=1,
        duration_ms=45,
    )

    cached = cache.get("hash_1", "npm test")
    assert cached is not None
    assert cached["verdict"] == "MATCH"
    assert cached["fingerprint"] == "fp_123"
    assert cache.stats()["hits"] == 1


def test_reducer_oracle_evaluations(tmp_path: Path):
    workspace = tmp_path / "workspace"
    mock_runner = MagicMock()

    # Case 1: Match
    mock_runner.run.return_value = ExecutionResult(
        command="npm test",
        exit_code=1,
        stdout="",
        stderr="",
        duration_ms=100,
        tree_hash="tree_a",
        backend="local_sandbox",
        fingerprint="fp_expected",
    )

    oracle = ReducerOracle(
        command="npm test",
        expected_fingerprint="fp_expected",
        workspace_dir=workspace,
        runner=mock_runner,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text("{}", encoding="utf-8")
    state = CandidateState.from_directory(repo)

    result = oracle.evaluate(state)
    assert result.verdict == OracleVerdict.MATCH
    assert result.fingerprint == "fp_expected"

    # Case 2: Mismatch (different fingerprint)
    mock_runner.run.return_value = ExecutionResult(
        command="npm test",
        exit_code=1,
        stdout="",
        stderr="",
        duration_ms=100,
        tree_hash="tree_b",
        backend="local_sandbox",
        fingerprint="fp_other",
    )
    result_mismatch = oracle.evaluate(state)
    assert result_mismatch.verdict == OracleVerdict.MISMATCH

    # Case 3: Exit code 0 (test passed -> bug lost)
    mock_runner.run.return_value = ExecutionResult(
        command="npm test",
        exit_code=0,
        stdout="",
        stderr="",
        duration_ms=100,
        tree_hash="tree_c",
        backend="local_sandbox",
        fingerprint=None,
    )
    result_pass = oracle.evaluate(state)
    assert result_pass.verdict == OracleVerdict.MISMATCH


def test_delta_debugging_algorithm_synthetic(tmp_path: Path):
    """
    Tests delta-debugging minimization using a mock oracle.
    Repository has files A, B, C, D, E.
    Bug reproduction requires only {B, D}.
    Verifies reducer correctly prunes {A, C, E} and preserves {B, D}.
    """
    repo = tmp_path / "synth_repo"
    repo.mkdir()
    (repo / "package.json").write_text("{}", encoding="utf-8")
    (repo / "src" / "dir_a").mkdir(parents=True)
    (repo / "src" / "dir_a" / "a.ts").write_text("const a = 1;", encoding="utf-8")
    (repo / "src" / "dir_b").mkdir(parents=True)
    (repo / "src" / "dir_b" / "b.ts").write_text("const b = 2;", encoding="utf-8")
    (repo / "src" / "dir_c").mkdir(parents=True)
    (repo / "src" / "dir_c" / "c.ts").write_text("const c = 3;", encoding="utf-8")
    (repo / "src" / "dir_d").mkdir(parents=True)
    (repo / "src" / "dir_d" / "d.ts").write_text("const d = 4;", encoding="utf-8")
    (repo / "src" / "dir_e").mkdir(parents=True)
    (repo / "src" / "dir_e" / "e.ts").write_text("const e = 5;", encoding="utf-8")

    initial_state = CandidateState.from_directory(repo)

    required_files = {"src/dir_b/b.ts", "src/dir_d/d.ts"}

    class SyntheticOracle:
        def __init__(self):
            self.total_evaluations = 0
            self.cache = None

        def evaluate(self, candidate: CandidateState) -> OracleResult:
            self.total_evaluations += 1
            # If all required files are present, match!
            if required_files.issubset(candidate.active_files):
                return OracleResult(verdict=OracleVerdict.MATCH, fingerprint="target_fp", exit_code=1)
            return OracleResult(verdict=OracleVerdict.MISMATCH, fingerprint="other_fp", exit_code=1)

    synth_oracle = SyntheticOracle()
    reducer = DeltaDebuggingReducer(
        oracle=synth_oracle,  # type: ignore
        progress=ReducerProgress(quiet=True),
        protected_files={"package.json"},
    )

    final_state, summary = reducer.reduce(initial_state)

    assert "src/dir_b/b.ts" in final_state.active_files
    assert "src/dir_d/d.ts" in final_state.active_files
    assert "src/dir_a/a.ts" not in final_state.active_files
    assert "src/dir_c/c.ts" not in final_state.active_files
    assert "src/dir_e/e.ts" not in final_state.active_files

    assert summary.final_files == 3  # package.json + b.ts + d.ts
    assert summary.loc_reduction_percentage > 40.0
    assert summary.total_evaluations < 20
