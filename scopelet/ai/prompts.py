"""
Prompt templates and few-shot examples for AI file relevance ranking.
"""

from __future__ import annotations

RANKER_SYSTEM_PROMPT = """You are an expert software debugging and defect localization assistant.
Your task is to analyze a test failure report and score a list of candidate source files by their relevance to the bug.
Assign each file a relevance score between 0.0 (completely irrelevant) and 1.0 (highly relevant or origin of defect).
Files directly appearing in the stack trace or responsible for the failing assertion should receive high scores (0.8 - 1.0).
Support files, utilities or unrelated modules should receive lower scores (0.1 - 0.4).

Respond STRICTLY with valid JSON following this format:
{
  "rankings": [
    {
      "file": "path/to/file.ts",
      "relevance": 0.95,
      "reason": "Directly defines the failing function referenced in the assertion error"
    }
  ]
}
Do not include markdown fences, preamble or explanations outside the JSON object.
"""

RANKER_FEW_SHOT_USER = """Test Failure:
AssertionError: Expected "2026-10-18", Received "2026-10-17"
Stack Trace:
  at tests/invoice.timezone.test.ts:22:31
  at src/invoice/date.service.ts:15:10
  at src/date/timezone.ts:8:5

Candidate Files:
- src/date/timezone.ts
- src/invoice/date.service.ts
- src/customer/customer.repository.ts
- src/analytics/analytics.service.ts
"""

RANKER_FEW_SHOT_ASSISTANT = """{
  "rankings": [
    {
      "file": "src/date/timezone.ts",
      "relevance": 0.95,
      "reason": "Direct origin of date formatting and timezone offset calculation"
    },
    {
      "file": "src/invoice/date.service.ts",
      "relevance": 0.85,
      "reason": "Direct caller in stack trace converting invoice timestamp"
    },
    {
      "file": "src/customer/customer.repository.ts",
      "relevance": 0.20,
      "reason": "Customer data store unrelated to timezone generation"
    },
    {
      "file": "src/analytics/analytics.service.ts",
      "relevance": 0.10,
      "reason": "Background analytics service completely outside defect path"
    }
  ]
}"""


def build_ranking_prompt(
    failure_summary: str,
    candidate_files: list[str],
    stack_frames: list[str] | None = None,
) -> str:
    """
    Constructs the user prompt for the local AI relevance ranker.
    """
    lines = [f"Test Failure:\n{failure_summary.strip()}"]
    if stack_frames:
        lines.append("Stack Frames:\n" + "\n".join(f"  at {frame}" for frame in stack_frames))

    lines.append("\nCandidate Files to Rank:")
    for f in candidate_files:
        lines.append(f"- {f}")

    lines.append("\nOutput JSON with relevance score for each file.")
    return "\n".join(lines)
