"""
Unit tests for Patch Boundary Verifier (Phase 15).
Ensures candidate patches adhere to security policies and task restrictions before ingestion.
"""

import pytest

from scopelet.patches import (
    BoundaryChecker,
    DependencyVersionCheck,
    DiffSizeLimitCheck,
    ForbiddenFilesCheck,
    NetworkCallsCheck,
    PackageConfigCheck,
    ShellExecutionCheck,
    TestFileModificationCheck,
    TestSkippingCheck,
    ValidationDisablingCheck,
)


def test_test_file_modification_rejected():
    checker = BoundaryChecker([TestFileModificationCheck()])

    # Modifying test file directly
    diff = "--- a/tests/invoice.test.ts\n+++ b/tests/invoice.test.ts\n@@ -1 +1 @@\n-assert(false)\n+assert(true)\n"
    assert checker.is_valid(diff) is False

    # Modifying python test file
    diff_py = "--- a/tests/test_date.py\n+++ b/tests/test_date.py\n@@ -1 +1 @@\n-def test_1():\n+def test_2():\n"
    assert checker.is_valid(diff_py) is False

    # Modifying spec file
    diff_spec = "--- a/src/service.spec.ts\n+++ b/src/service.spec.ts\n@@ -1 +1 @@\n-a\n+b\n"
    assert checker.is_valid(diff_spec) is False

    # Modifying regular source file
    diff_src = "--- a/src/service.ts\n+++ b/src/service.ts\n@@ -1 +1 @@\n-a\n+b\n"
    assert checker.is_valid(diff_src) is True


def test_test_skipping_directives_rejected():
    checker = BoundaryChecker([TestSkippingCheck()])

    # test.skip
    d1 = "--- a/src/index.ts\n+++ b/src/index.ts\n@@ -1 +1,2 @@\n+test.skip('skip test');\n const x = 1;\n"
    assert checker.is_valid(d1) is False

    # describe.skip
    d2 = "--- a/src/index.ts\n+++ b/src/index.ts\n@@ -1 +1,2 @@\n+describe.skip('skip suite');\n const x = 1;\n"
    assert checker.is_valid(d2) is False

    # it.skip
    d3 = "--- a/src/index.ts\n+++ b/src/index.ts\n@@ -1 +1,2 @@\n+it.skip('skip item');\n const x = 1;\n"
    assert checker.is_valid(d3) is False

    # @pytest.mark.skip
    d4 = "--- a/src/index.py\n+++ b/src/index.py\n@@ -1 +1,2 @@\n+@pytest.mark.skip(reason='bypass')\n def foo(): pass\n"
    assert checker.is_valid(d4) is False

    # unittest.skip
    d5 = "--- a/src/index.py\n+++ b/src/index.py\n@@ -1 +1,2 @@\n+@unittest.skip('bypass')\n def foo(): pass\n"
    assert checker.is_valid(d5) is False


def test_package_config_integrity_rejected():
    checker = BoundaryChecker([PackageConfigCheck()])

    for cfg in [
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pyproject.toml",
        "poetry.lock",
        "requirements.txt",
        "Pipfile",
        "Dockerfile",
        ".env",
        "tsconfig.json",
    ]:
        diff = f"--- a/{cfg}\n+++ b/{cfg}\n@@ -1 +1 @@\n-foo\n+bar\n"
        assert checker.is_valid(diff) is False, f"Expected {cfg} modification to be rejected"


def test_forbidden_files_rejected():
    checker = BoundaryChecker([ForbiddenFilesCheck()])

    diff = "--- a/src/secret.ts\n+++ b/src/secret.ts\n@@ -1 +1 @@\n-a\n+b\n"
    assert checker.is_valid(diff, forbidden_files=["src/secret.ts"]) is False
    assert checker.is_valid(diff, forbidden_files=["src/other.ts"]) is True


def test_network_calls_rejected():
    checker = BoundaryChecker([NetworkCallsCheck()])

    # fetch
    d1 = "--- a/src/date.ts\n+++ b/src/date.ts\n@@ -1 +1,2 @@\n+fetch('https://malicious.org');\n return 1;\n"
    assert checker.is_valid(d1) is False

    # axios
    d2 = "--- a/src/date.ts\n+++ b/src/date.ts\n@@ -1 +1,2 @@\n+axios.get('https://malicious.org');\n return 1;\n"
    assert checker.is_valid(d2) is False

    # requests.get
    d3 = "--- a/src/date.py\n+++ b/src/date.py\n@@ -1 +1,2 @@\n+requests.get('https://malicious.org')\n return 1\n"
    assert checker.is_valid(d3) is False

    # socket.socket
    d4 = "--- a/src/date.py\n+++ b/src/date.py\n@@ -1 +1,2 @@\n+s = socket.socket()\n return 1\n"
    assert checker.is_valid(d4) is False

    # WebSocket
    d5 = "--- a/src/date.ts\n+++ b/src/date.ts\n@@ -1 +1,2 @@\n+const ws = new WebSocket('ws://evil.com');\n return 1;\n"
    assert checker.is_valid(d5) is False


def test_shell_execution_rejected():
    checker = BoundaryChecker([ShellExecutionCheck()])

    # eval
    d1 = "--- a/src/date.ts\n+++ b/src/date.ts\n@@ -1 +1,2 @@\n+eval(payload);\n return 1;\n"
    assert checker.is_valid(d1) is False

    # new Function
    d2 = "--- a/src/date.ts\n+++ b/src/date.ts\n@@ -1 +1,2 @@\n+new Function('return process')();\n return 1;\n"
    assert checker.is_valid(d2) is False

    # child_process
    d3 = "--- a/src/date.ts\n+++ b/src/date.ts\n@@ -1 +1,2 @@\n+const cp = require('child_process');\n return 1;\n"
    assert checker.is_valid(d3) is False

    # subprocess
    d4 = "--- a/src/date.py\n+++ b/src/date.py\n@@ -1 +1,2 @@\n+subprocess.Popen(['rm', '-rf'])\n return 1\n"
    assert checker.is_valid(d4) is False

    # os.system
    d5 = "--- a/src/date.py\n+++ b/src/date.py\n@@ -1 +1,2 @@\n+os.system('sh evil.sh')\n return 1\n"
    assert checker.is_valid(d5) is False


def test_dependency_version_changes_rejected():
    checker = BoundaryChecker([DependencyVersionCheck()])

    diff = '--- a/src/date.ts\n+++ b/src/date.ts\n@@ -1 +1,2 @@\n+ "lodash": "^4.17.21",\n return 1;\n'
    assert checker.is_valid(diff) is False


def test_diff_size_limits():
    checker = BoundaryChecker([DiffSizeLimitCheck(max_lines=10, max_files=2)])

    # Too many files
    d_files = (
        "--- a/src/f1.ts\n+++ b/src/f1.ts\n@@ -1 +1 @@\n-a\n+b\n"
        "--- a/src/f2.ts\n+++ b/src/f2.ts\n@@ -1 +1 @@\n-a\n+b\n"
        "--- a/src/f3.ts\n+++ b/src/f3.ts\n@@ -1 +1 @@\n-a\n+b\n"
    )
    assert checker.is_valid(d_files) is False

    # Too many lines
    lines = "".join([f"+line {i}\n" for i in range(20)])
    d_lines = f"--- a/src/f1.ts\n+++ b/src/f1.ts\n@@ -1 +1,20 @@\n{lines}"
    assert checker.is_valid(d_lines) is False


def test_clean_patch_passes_boundary():
    checker = BoundaryChecker()

    diff = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,3 @@\n"
        " export function getAdjustedDate(d: Date): string {\n"
        "-    return formatUTC(d);\n"
        "+    return formatWithOffset(d, 330);\n"
        " }\n"
    )

    results = checker.check_all(diff, allowed_changes=["src/date/timezone.ts"])
    assert all(r.passed for r in results)
    assert checker.is_valid(diff, allowed_changes=["src/date/timezone.ts"]) is True


def test_hardcoded_return_value_passes_boundary_for_hidden_verifier():
    """
    As specified in Phase 15: hardcoded return value passes boundary checks,
    because boundary checks verify policy/security, while the hidden verifier
    catches hardcoded returns via hidden regression tests.
    """
    checker = BoundaryChecker()

    diff = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,3 @@\n"
        " export function getInvoiceDate(): string {\n"
        "-    return computeDate();\n"
        "+    return '2026-10-18';\n"
        " }\n"
    )

    assert checker.is_valid(diff, allowed_changes=["src/date/timezone.ts"]) is True
