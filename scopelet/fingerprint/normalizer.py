"""
Normalization engine for test outputs, stack traces, and failure messages.
Transforms noisy, environment-dependent test failures into canonical representations.
"""

import re
from pathlib import Path
from typing import Optional, List
from ..models.failure import NormalizedFailure
from .hasher import compute_fingerprint

# Regex to strip ANSI escape sequences
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Common JS/TS exception types
EXCEPTION_PATTERNS = [
    r"\b(AssertionError)\b",
    r"\b(TypeError)\b",
    r"\b(ReferenceError)\b",
    r"\b(RangeError)\b",
    r"\b(SyntaxError)\b",
    r"\b(Error)\b",
]

# Vitest / Jest diff patterns:
# - Expected
# + Received
# - 2026-10-18
# + 2026-10-17
DIFF_EXPECTED_RE = re.compile(r"-\s*Expected[^\n]*\n\+\s*Received[^\n]*\n\s*-\s*([^\n]+)\n\s*\+\s*([^\n]+)", re.MULTILINE)

# Inline expectation: expected '2026-10-17' to be '2026-10-18'
# or expected 249.99 to be 250
INLINE_EXPECTED_RE = re.compile(
    r"expected\s+['\"]?([^'\"\n]+?)['\"]?\s+to\s+(?:be|equal|deeply\s+equal)\s+['\"]?([^'\"\n]+?)['\"]?(?:\s*//|\n|$)",
    re.IGNORECASE
)

# Stack frame patterns:
# ❯ tests/invoice-timezone.test.ts:22:31
# at Object.<anonymous> (src/invoice/service.ts:44:21)
# at src/invoice/service.ts:44:21
STACK_FRAME_PATTERNS = [
    re.compile(r"[❯\s]+(?:at\s+(?:.+?\s+\()?|[>❯]\s+)?([a-zA-Z0-9_\-\.\/\\:]+?\.[jt]sx?)(?::(\d+)(?::(\d+))?)?\)?"),
]

# Patterns for volatile values to strip: UUIDs, timings, hex memory addresses
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HEX_ADDR_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
DURATION_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|seconds|s|min)\b", re.IGNORECASE)
TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")


def strip_ansi(text: str) -> str:
    """Strips terminal ANSI color and styling escape sequences."""
    return ANSI_ESCAPE_RE.sub("", text)


def normalize_path(path_str: str, cwd: Optional[Path] = None) -> str:
    """
    Normalizes a file path to forward slashes and makes it relative to cwd if possible.
    """
    p = path_str.replace("\\", "/").strip()
    if cwd:
        cwd_str = str(cwd.resolve()).replace("\\", "/")
        if p.lower().startswith(cwd_str.lower()):
            p = p[len(cwd_str):].lstrip("/")
    # Clean leading drive letters or slashes
    if re.match(r"^[a-zA-Z]:", p):
        p = re.sub(r"^[a-zA-Z]:[\\/]*", "", p)
    return p.lstrip("./")


def clean_volatile(text: str) -> str:
    """
    Strips UUIDs, timestamps, timings, and memory addresses from error text.
    """
    cleaned = strip_ansi(text)
    cleaned = UUID_RE.sub("<UUID>", cleaned)
    cleaned = HEX_ADDR_RE.sub("<ADDR>", cleaned)
    cleaned = TIMESTAMP_RE.sub("<TIMESTAMP>", cleaned)
    cleaned = DURATION_RE.sub("<DURATION>", cleaned)
    return cleaned


def extract_stack_frames(text: str, cwd: Optional[Path] = None) -> List[str]:
    """
    Extracts and normalizes unique file paths from a stack trace,
    stripping line and column numbers and ignoring third-party libraries.
    """
    clean_text = strip_ansi(text)
    frames: list[str] = []

    for line in clean_text.splitlines():
        # Skip node internals and test runner internals
        if any(ignored in line for ignored in ("node:internal", "node_modules", "vitest/dist", "@vitest")):
            continue

        for pattern in STACK_FRAME_PATTERNS:
            match = pattern.search(line)
            if match:
                raw_path = match.group(1)
                # Ignore test runner internals
                if any(ignored in raw_path for ignored in ("node_modules", "vitest")):
                    continue
                norm = normalize_path(raw_path, cwd)
                # Ensure it looks like a valid source file path
                if norm.endswith((".ts", ".js", ".tsx", ".jsx", ".mjs", ".cjs")) and "/" in norm:
                    if norm not in frames:
                        frames.append(norm)

    return frames


def parse_failure(raw_output: str, cwd: Optional[Path] = None) -> Optional[NormalizedFailure]:
    """
    Parses raw test output (stdout + stderr) into a NormalizedFailure with canonical fingerprint.
    Returns None if no failure was detected.
    """
    clean_text = strip_ansi(raw_output)

    # 1. Detect if there is a test failure
    has_fail = bool(
        re.search(r"\bFAIL\b", clean_text)
        or re.search(r"\bAssertionError\b", clean_text)
        or re.search(r"Failed Tests \d+", clean_text)
        or re.search(r"Tests\s+\d+\s+failed", clean_text)
    )
    if not has_fail:
        return None

    # 2. Extract Test Name
    # Patterns:
    # FAIL  tests/invoice-timezone.test.ts > Invoice Timezone Generation > generates correct calendar date...
    # or ❯ tests/invoice-timezone.test.ts > Invoice Timezone Generation > ...
    test_name = "UnknownTest"
    test_match = re.search(
        r"(?:FAIL|[>❯])\s+(?:tests\/[^\n>]+>\s+)?([^\n]+?)(?:\s*//|\n|$)",
        clean_text
    )
    if test_match:
        cand = test_match.group(1).strip()
        # Clean leading symbols
        cand = re.sub(r"^[>❯\s]+", "", cand)
        if len(cand) > 3 and not cand.startswith("AssertionError"):
            test_name = cand

    # If test_name is generic, try finding "FAIL <path> > <name>"
    fail_line_match = re.search(r"FAIL\s+([^\n]+)", clean_text)
    if fail_line_match:
        test_name = fail_line_match.group(1).strip()

    # 3. Extract Exception Type
    exception_type = "AssertionError"
    for ep in EXCEPTION_PATTERNS:
        em = re.search(ep, clean_text)
        if em:
            exception_type = em.group(1)
            break

    # 4. Extract Expected and Actual values
    expected: Optional[str] = None
    actual: Optional[str] = None

    diff_match = DIFF_EXPECTED_RE.search(clean_text)
    if diff_match:
        expected = diff_match.group(1).strip().strip("'\"")
        actual = diff_match.group(2).strip().strip("'\"")
    else:
        inline_match = INLINE_EXPECTED_RE.search(clean_text)
        if inline_match:
            # "expected <actual> to be <expected>"
            actual = inline_match.group(1).strip().strip("'\"")
            expected = inline_match.group(2).strip().strip("'\"")

    # 5. Extract Stack Frames (Normalized, no line numbers)
    frames = extract_stack_frames(clean_text, cwd)

    # 6. Extract normalized message summary
    message = f"{exception_type}"
    if expected is not None and actual is not None:
        message = f"{exception_type}: expected {actual} to be {expected}"
    else:
        msg_match = re.search(rf"{exception_type}:\s*([^\n]+)", clean_text)
        if msg_match:
            message = clean_volatile(msg_match.group(1).strip())

    # Build NormalizedFailure
    failure = NormalizedFailure(
        schema_version="1.0",
        test=clean_volatile(test_name),
        exception=exception_type,
        message=message,
        expected=expected,
        actual=actual,
        frames=frames,
    )

    # Compute deterministic fingerprint
    failure.fingerprint = compute_fingerprint(failure.canonical_dict())
    return failure
