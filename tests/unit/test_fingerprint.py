"""
Tests for Scopelet failure fingerprinting and normalization.
Verifies that:
- Same bug produces the exact same fingerprint
- Line number changes do not alter fingerprint
- Logging additions do not alter fingerprint
- Volatile timings, UUIDs, timestamps do not alter fingerprint
- Different tests/exceptions produce different fingerprints
"""

import pytest
from pathlib import Path
from scopelet.fingerprint.hasher import canonical_json, compute_fingerprint
from scopelet.fingerprint.normalizer import (
    strip_ansi,
    clean_volatile,
    normalize_path,
    extract_stack_frames,
    parse_failure,
)
from scopelet.models.failure import NormalizedFailure


SAMPLE_VITEST_OUTPUT_1 = """
\x1b[31m RUN  v1.6.1 fixtures/timezone-bug\x1b[39m

 ❯ tests/invoice-timezone.test.ts:22:31
FAIL  tests/invoice-timezone.test.ts > Invoice Timezone Generation > generates correct calendar date for invoice created at 00:30 IST
AssertionError: expected '2026-10-17' to be '2026-10-18' // Object.is equality

- Expected
+ Received

- 2026-10-18
+ 2026-10-17

 ❯ tests/invoice-timezone.test.ts:22:31
     20|     expect(invoice.issueDate).toBe('2026-10-18');
       |                               ^

 Test Files  1 failed (1)
      Tests  1 failed (1)
   Duration  411ms (transform 53ms, setup 0ms, collect 86ms, tests 6ms)
"""

# Same failure, but line numbers in stack trace changed from 22:31 to 145:89
SAMPLE_VITEST_OUTPUT_LINE_CHANGE = """
\x1b[31m RUN  v1.6.1 fixtures/timezone-bug\x1b[39m

 ❯ tests/invoice-timezone.test.ts:145:89
FAIL  tests/invoice-timezone.test.ts > Invoice Timezone Generation > generates correct calendar date for invoice created at 00:30 IST
AssertionError: expected '2026-10-17' to be '2026-10-18' // Object.is equality

- Expected
+ Received

- 2026-10-18
+ 2026-10-17

 ❯ tests/invoice-timezone.test.ts:145:89
    144|     expect(invoice.issueDate).toBe('2026-10-18');
       |                               ^

 Test Files  1 failed (1)
      Tests  1 failed (1)
   Duration  892ms (transform 120ms, setup 0ms, collect 140ms, tests 12ms)
"""

# Same failure, but extra application logs, UUIDs, and timestamps emitted before failure
SAMPLE_VITEST_OUTPUT_LOGS_ADDED = """
[INFO] 2026-10-18T14:02:16.123Z Server initializing session uuid 550e8400-e29b-41d4-a716-446655440000
[DEBUG] Memory address at 0x7fff5fbff8a0
[WARN] Database latency took 45ms
\x1b[31m RUN  v1.6.1 fixtures/timezone-bug\x1b[39m

FAIL  tests/invoice-timezone.test.ts > Invoice Timezone Generation > generates correct calendar date for invoice created at 00:30 IST
AssertionError: expected '2026-10-17' to be '2026-10-18' // Object.is equality

- Expected
+ Received

- 2026-10-18
+ 2026-10-17

 ❯ tests/invoice-timezone.test.ts:22:31

 Test Files  1 failed (1)
      Tests  1 failed (1)
   Duration  950ms
"""

# Different test failure (Fixture B rounding bug)
SAMPLE_VITEST_OUTPUT_ROUNDING = """
FAIL  tests/rounding.test.ts > Currency Rounding Behavior > correctly rounds half-cent amount ₹249.995 to ₹250.00
AssertionError: expected 249.99 to be 250 // Object.is equality

- Expected
+ Received

- 250
+ 249.99

 ❯ tests/rounding.test.ts:15:21
"""

# Passing test run output
SAMPLE_VITEST_PASSING = """
 RUN  v1.6.1 fixtures/timezone-bug

 ✓ tests/customer.test.ts (1 test) 2ms
 ✓ tests/auth.test.ts (1 test) 2ms
 ✓ tests/billing.test.ts (1 test) 3ms

 Test Files  3 passed (3)
      Tests  3 passed (3)
   Duration  350ms
"""


def test_canonical_json_sorting():
    d1 = {"b": 2, "a": 1, "c": [3, 2, 1]}
    d2 = {"c": [3, 2, 1], "a": 1, "b": 2}
    assert canonical_json(d1) == canonical_json(d2)
    assert canonical_json(d1) == '{"a":1,"b":2,"c":[3,2,1]}'


def test_compute_fingerprint_deterministic():
    data = {"test": "suite", "exception": "Error", "expected": "A", "actual": "B"}
    h1 = compute_fingerprint(data)
    h2 = compute_fingerprint(data)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256


def test_strip_ansi_escapes():
    colored = "\x1b[31mRED\x1b[0m and \x1b[32mGREEN\x1b[0m"
    assert strip_ansi(colored) == "RED and GREEN"


def test_clean_volatile_data():
    raw = "Failed at 2026-10-18T14:02:16Z with uuid 12345678-1234-5678-1234-567812345678 and ptr 0xdeadbeef after 125ms"
    cleaned = clean_volatile(raw)
    assert "<TIMESTAMP>" in cleaned
    assert "<UUID>" in cleaned
    assert "<ADDR>" in cleaned
    assert "<DURATION>" in cleaned


def test_normalize_path_windows_and_relative():
    cwd = Path("/workspace/myproject")
    # Windows drive path
    p1 = "D:/workspace/myproject/src/invoice/date.ts"
    assert "src/invoice/date.ts" in normalize_path(p1, Path("D:/workspace/myproject"))

    # Backslashes
    p2 = "tests\\invoice-timezone.test.ts"
    assert normalize_path(p2) == "tests/invoice-timezone.test.ts"


def test_extract_stack_frames_strips_lines():
    stack = """
    ❯ tests/invoice-timezone.test.ts:45:12
    at generateInvoice (src/invoice/invoice.service.ts:88:5)
    at formatToTimezoneDate (src/date/timezone.ts:12:3)
    at node:internal/process/task_queues:95:5
    at node_modules/vitest/dist/runner.js:120:9
    """
    frames = extract_stack_frames(stack)
    assert "tests/invoice-timezone.test.ts" in frames
    assert "src/invoice/invoice.service.ts" in frames
    assert "src/date/timezone.ts" in frames
    # Verify node internals and node_modules are excluded
    assert not any("node:internal" in f for f in frames)
    assert not any("node_modules" in f for f in frames)


def test_same_bug_twice_same_fingerprint():
    f1 = parse_failure(SAMPLE_VITEST_OUTPUT_1)
    f2 = parse_failure(SAMPLE_VITEST_OUTPUT_1)
    assert f1 is not None and f2 is not None
    assert f1.fingerprint == f2.fingerprint


def test_line_number_change_same_fingerprint():
    f1 = parse_failure(SAMPLE_VITEST_OUTPUT_1)
    f2 = parse_failure(SAMPLE_VITEST_OUTPUT_LINE_CHANGE)
    assert f1 is not None and f2 is not None
    # Fingerprint must be identical despite line 22 -> line 145!
    assert f1.fingerprint == f2.fingerprint
    assert f1.expected == f2.expected == "2026-10-18"
    assert f1.actual == f2.actual == "2026-10-17"


def test_logging_changes_same_fingerprint():
    f1 = parse_failure(SAMPLE_VITEST_OUTPUT_1)
    f2 = parse_failure(SAMPLE_VITEST_OUTPUT_LOGS_ADDED)
    assert f1 is not None and f2 is not None
    # Fingerprint must be invariant to timestamps, UUIDs, log preambles
    assert f1.fingerprint == f2.fingerprint


def test_different_bug_different_fingerprint():
    f_tz = parse_failure(SAMPLE_VITEST_OUTPUT_1)
    f_round = parse_failure(SAMPLE_VITEST_OUTPUT_ROUNDING)
    assert f_tz is not None and f_round is not None
    assert f_tz.fingerprint != f_round.fingerprint


def test_passing_test_returns_none():
    result = parse_failure(SAMPLE_VITEST_PASSING)
    assert result is None


def test_normalized_failure_schema_version():
    f = parse_failure(SAMPLE_VITEST_OUTPUT_1)
    assert f is not None
    assert f.schema_version == "1.0"
    assert f.exception == "AssertionError"
    assert len(f.frames) > 0


def test_inline_expectation_parsing():
    output = "FAIL tests/sample.test.ts\nAssertionError: expected 'Alice' to be 'Alice Smith'\n ❯ tests/sample.test.ts:10:5"
    f = parse_failure(output)
    assert f is not None
    assert f.expected == "Alice Smith"
    assert f.actual == "Alice"


def test_canonical_dict_invariance():
    f = NormalizedFailure(
        schema_version="1.0",
        test="T1",
        exception="AssertionError",
        message="Failure at 14:00:00",
        expected="A",
        actual="B",
        frames=["src/b.ts", "src/a.ts", "src/b.ts"],  # duplicate and out-of-order
    )
    cd = f.canonical_dict()
    # Frames must be deduplicated and sorted
    assert cd["frames"] == ["src/a.ts", "src/b.ts"]
