"""
Unit tests for the SQLite-backed runner execution cache and tree hashing.
"""

from pathlib import Path
from scopelet.runner.cache import ExecutionCache, compute_tree_hash
from scopelet.runner.result import ExecutionResult


def test_compute_tree_hash_deterministic(tmp_path):
    f1 = tmp_path / "a.ts"
    f2 = tmp_path / "b.ts"
    f1.write_text("console.log('hello')", encoding="utf-8")
    f2.write_text("export const x = 1;", encoding="utf-8")

    h1 = compute_tree_hash(tmp_path)
    h2 = compute_tree_hash(tmp_path)
    assert h1 == h2
    assert len(h1) == 64


def test_tree_hash_sensitive_to_file_content(tmp_path):
    f1 = tmp_path / "a.ts"
    f1.write_text("version 1", encoding="utf-8")
    h1 = compute_tree_hash(tmp_path)

    f1.write_text("version 2", encoding="utf-8")
    h2 = compute_tree_hash(tmp_path)
    assert h1 != h2


def test_tree_hash_ignores_node_modules_and_git(tmp_path):
    src = tmp_path / "src" / "index.ts"
    src.parent.mkdir(parents=True)
    src.write_text("const a = 1;", encoding="utf-8")
    base_hash = compute_tree_hash(tmp_path)

    # Adding files inside node_modules or .git must NOT change tree hash
    nm_file = tmp_path / "node_modules" / "pkg" / "index.js"
    nm_file.parent.mkdir(parents=True)
    nm_file.write_text("module.exports = {};", encoding="utf-8")

    git_file = tmp_path / ".git" / "HEAD"
    git_file.parent.mkdir(parents=True)
    git_file.write_text("ref: refs/heads/main", encoding="utf-8")

    assert compute_tree_hash(tmp_path) == base_hash


def test_execution_cache_lifecycle(tmp_path):
    db_file = tmp_path / "cache.db"
    cache = ExecutionCache(db_file)
    assert cache.count() == 0

    result = ExecutionResult(
        schema_version="1.0",
        command="npm test",
        exit_code=1,
        stdout="FAIL test",
        stderr="",
        duration_ms=450,
        backend="local_sandbox",
        tree_hash="abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
        cached=False,
        fingerprint="fp123456",
    )

    # Cache miss
    miss = cache.get(result.tree_hash, result.command, env_hash="default", backend=result.backend)
    assert miss is None

    # Put into cache
    cache.put(result, env_hash="default")
    assert cache.count() == 1

    # Cache hit
    hit = cache.get(result.tree_hash, result.command, env_hash="default", backend=result.backend)
    assert hit is not None
    assert hit.cached is True
    assert hit.command == "npm test"
    assert hit.exit_code == 1
    assert hit.fingerprint == "fp123456"

    # Clear cache
    cache.clear()
    assert cache.count() == 0
