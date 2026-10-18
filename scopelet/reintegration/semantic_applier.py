"""
Semantic patch reintegration engine V2.
Handles context drift, line offset shifts and fuzzy hunk re-anchoring
when candidate patches drift from private repositories.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from .applier import ReintegrationApplierV1, ReintegrationResult
from .mapper import ReverseIdentifierMapper
from .worktree import IsolatedWorktree
from ..verification.patcher import PatchApplier, PatchError


class HunkMatch(BaseModel):
    """
    Metadata for a matched hunk in the target source file.
    """
    file_path: str
    expected_start: int
    matched_start: int
    matched_length: int
    drift_lines: int
    confidence: float


class SemanticReintegrationResult(BaseModel):
    """
    Outcome of semantic patch reintegration with drift tolerance.
    """
    success: bool = Field(..., description="Whether semantic application succeeded")
    un_sanitized_patch: str = Field(..., description="Un-sanitized patch string")
    modified_files: List[str] = Field(default_factory=list, description="List of modified files")
    hunks_total: int = Field(default=0, description="Total hunks across all files")
    hunks_adapted: int = Field(default=0, description="Number of hunks adapted via drift compensation")
    drift_detected: bool = Field(default=False, description="Whether any context or line drift was encountered")
    confidence_score: float = Field(default=1.0, description="Average confidence score across matched hunks")
    details: List[str] = Field(default_factory=list, description="Diagnostic notes detailing applied adaptations")
    error: Optional[str] = Field(default=None, description="Failure reason if application failed")


class SemanticPatchApplierV2:
    """
    Resilient semantic patch applier with fuzzy hunk anchoring and drift resolution.
    Follows the principle: AI proposes, verifier accepts.
    """

    HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

    def __init__(
        self,
        repo_dir: Path,
        mapping: Optional[Dict[str, str]] = None,
        mapping_file: Optional[Path] = None,
        semantic_adapter: Optional[Callable[[str, str, str], str]] = None,
        search_window: int = 100,
        fuzzy_threshold: float = 0.65,
    ):
        self.repo_dir = repo_dir.resolve()
        if mapping:
            self.mapper = ReverseIdentifierMapper(mapping)
        elif mapping_file and mapping_file.exists():
            self.mapper = ReverseIdentifierMapper.from_file(mapping_file)
        else:
            default_map = self.repo_dir / ".scopelet" / "private" / "mapping.json"
            if default_map.exists():
                self.mapper = ReverseIdentifierMapper.from_file(default_map)
            else:
                self.mapper = ReverseIdentifierMapper({})

        self.semantic_adapter = semantic_adapter
        self.search_window = search_window
        self.fuzzy_threshold = fuzzy_threshold
        self.v1_applier = ReintegrationApplierV1(self.repo_dir, mapping=self.mapper.mapping)

    def apply(
        self,
        patch_content: str,
        target_dir: Optional[Path] = None,
        force_semantic: bool = False,
    ) -> SemanticReintegrationResult:
        """
        Applies patch to target directory.
        First tries exact V1 application (unless force_semantic is True).
        If exact application fails due to drift, activates semantic fuzzy hunk matching.
        """
        dest = (target_dir or self.repo_dir).resolve()
        un_sanitized = self.mapper.un_sanitize_patch(patch_content)

        if not force_semantic:
            v1_res = self.v1_applier.apply(un_sanitized, target_dir=dest)
            if v1_res.success:
                return SemanticReintegrationResult(
                    success=True,
                    un_sanitized_patch=un_sanitized,
                    modified_files=v1_res.modified_files,
                    hunks_total=1,
                    hunks_adapted=0,
                    drift_detected=False,
                    confidence_score=1.0,
                    details=["Exact V1 patch application succeeded cleanly with zero drift."],
                    error=None,
                )

        # Fallback to Semantic V2 fuzzy hunk reconciliation
        return self._apply_semantic(un_sanitized, dest)

    def _apply_semantic(self, un_sanitized_patch: str, target_dir: Path) -> SemanticReintegrationResult:
        """
        Executes semantic fuzzy hunk matching and chunk re-anchoring.
        """
        file_diffs = PatchApplier._split_file_diffs(un_sanitized_patch)
        if not file_diffs:
            return SemanticReintegrationResult(
                success=False,
                un_sanitized_patch=un_sanitized_patch,
                modified_files=[],
                error="No valid file diffs found in patch.",
            )

        modified_files: List[str] = []
        total_hunks = 0
        adapted_hunks = 0
        drift_detected = False
        confidence_scores: List[float] = []
        details: List[str] = []

        for old_path, new_path, hunk_lines in file_diffs:
            if new_path == "/dev/null":
                del_file = target_dir / old_path
                if del_file.exists():
                    del_file.unlink()
                modified_files.append(old_path)
                continue

            if old_path == "/dev/null":
                dest_file = target_dir / new_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                new_content = PatchApplier._apply_hunks([], hunk_lines, new_path)
                dest_file.write_text("".join(new_content), encoding="utf-8")
                modified_files.append(new_path)
                continue

            target_file = target_dir / new_path
            if not target_file.exists():
                return SemanticReintegrationResult(
                    success=False,
                    un_sanitized_patch=un_sanitized_patch,
                    modified_files=[],
                    error=f"Target file not found for semantic reintegration: {new_path}",
                )

            orig_content = target_file.read_text(encoding="utf-8", errors="replace")
            orig_lines = orig_content.splitlines(keepends=True)

            parsed_hunks = self._parse_hunks(hunk_lines)
            if not parsed_hunks:
                continue

            curr_lines = list(orig_lines)
            file_hunks_total = len(parsed_hunks)
            total_hunks += file_hunks_total

            for h_idx, (h_header, h_body) in enumerate(parsed_hunks):
                match_res = self._find_best_anchor(curr_lines, h_header, h_body)

                if match_res is not None:
                    matched_start, matched_len, conf, drift_lines = match_res
                    confidence_scores.append(conf)
                    if drift_lines != 0 or conf < 0.99:
                        drift_detected = True
                        adapted_hunks += 1
                        details.append(
                            f"{new_path} hunk #{h_idx+1}: anchored at line {matched_start+1} "
                            f"(drift: {drift_lines:+d} lines, confidence: {conf:.2f})"
                        )

                    new_chunk = self._build_replacement_chunk(h_body)
                    curr_lines[matched_start : matched_start + matched_len] = new_chunk
                else:
                    # If fuzzy anchor failed, check if an external semantic adapter function was configured
                    if self.semantic_adapter:
                        try:
                            before_chunk = "".join(self._extract_old_lines(h_body))
                            after_chunk = "".join(self._extract_new_lines(h_body))
                            adapted = self.semantic_adapter("".join(curr_lines), before_chunk, after_chunk)
                            curr_lines = adapted.splitlines(keepends=True)
                            adapted_hunks += 1
                            drift_detected = True
                            confidence_scores.append(0.80)
                            details.append(f"{new_path} hunk #{h_idx+1}: adapted via semantic AI adapter")
                            continue
                        except Exception as ex:
                            return SemanticReintegrationResult(
                                success=False,
                                un_sanitized_patch=un_sanitized_patch,
                                modified_files=[],
                                error=f"Semantic adapter failed on {new_path}: {ex}",
                            )

                    return SemanticReintegrationResult(
                        success=False,
                        un_sanitized_patch=un_sanitized_patch,
                        modified_files=[],
                        error=f"Could not anchor hunk #{h_idx+1} in {new_path} despite semantic fuzzy search.",
                    )

            target_file.write_text("".join(curr_lines), encoding="utf-8")
            modified_files.append(new_path)

        avg_conf = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 1.0

        return SemanticReintegrationResult(
            success=True,
            un_sanitized_patch=un_sanitized_patch,
            modified_files=sorted(set(modified_files)),
            hunks_total=total_hunks,
            hunks_adapted=adapted_hunks,
            drift_detected=drift_detected,
            confidence_score=round(avg_conf, 3),
            details=details,
            error=None,
        )

    def _parse_hunks(self, hunk_lines: List[str]) -> List[Tuple[str, List[str]]]:
        """
        Splits raw hunk lines into list of (header, body_lines).
        """
        hunks: List[Tuple[str, List[str]]] = []
        current_header: Optional[str] = None
        current_body: List[str] = []

        for line in hunk_lines:
            if line.startswith("@@"):
                if current_header is not None:
                    hunks.append((current_header, current_body))
                current_header = line.strip()
                current_body = []
            else:
                if current_header is not None:
                    current_body.append(line)

        if current_header is not None:
            hunks.append((current_header, current_body))

        return hunks

    def _extract_old_lines(self, body_lines: List[str]) -> List[str]:
        return [l[1:] for l in body_lines if l.startswith(" ") or l.startswith("-")]

    def _extract_new_lines(self, body_lines: List[str]) -> List[str]:
        return [l[1:] for l in body_lines if l.startswith(" ") or l.startswith("+")]

    def _build_replacement_chunk(self, body_lines: List[str]) -> List[str]:
        result: List[str] = []
        for line in body_lines:
            if line.startswith(" ") or line.startswith("+"):
                result.append(line[1:])
        return result

    def _find_best_anchor(
        self,
        target_lines: List[str],
        header: str,
        body: List[str],
    ) -> Optional[Tuple[int, int, float, int]]:
        """
        Finds best starting index in target_lines for matching old context lines of hunk.
        Returns: (start_index, matched_length, confidence, drift_lines).
        """
        old_pattern = self._extract_old_lines(body)
        if not old_pattern:
            return (0, 0, 1.0, 0)

        pattern_len = len(old_pattern)
        m = self.HUNK_HEADER_RE.match(header)
        expected_start = int(m.group(1)) - 1 if m else 0
        expected_start = max(0, min(expected_start, len(target_lines)))

        # 1. Exact match at expected position
        if expected_start + pattern_len <= len(target_lines):
            candidate = target_lines[expected_start : expected_start + pattern_len]
            if candidate == old_pattern:
                return (expected_start, pattern_len, 1.0, 0)

        # 2. Exact match in local sliding window
        window = self.search_window
        min_idx = max(0, expected_start - window)
        max_idx = min(len(target_lines) - pattern_len + 1, expected_start + window)

        best_exact: Optional[Tuple[int, int, float, int]] = None
        min_offset = float("inf")

        for idx in range(min_idx, max_idx):
            candidate = target_lines[idx : idx + pattern_len]
            if candidate == old_pattern:
                offset = abs(idx - expected_start)
                if offset < min_offset:
                    min_offset = offset
                    drift = idx - expected_start
                    best_exact = (idx, pattern_len, 0.98, drift)

        if best_exact is not None:
            return best_exact

        # 3. Fuzzy normalized matching within window
        best_fuzzy: Optional[Tuple[int, int, float, int]] = None
        highest_similarity = 0.0

        normalized_pattern = [self._normalize_line(l) for l in old_pattern]
        pattern_str = "\n".join(normalized_pattern)

        for idx in range(min_idx, max_idx):
            candidate = target_lines[idx : idx + pattern_len]
            candidate_norm = [self._normalize_line(l) for l in candidate]
            candidate_str = "\n".join(candidate_norm)

            sim = difflib.SequenceMatcher(None, pattern_str, candidate_str).ratio()
            if sim > highest_similarity:
                highest_similarity = sim
                drift = idx - expected_start
                best_fuzzy = (idx, pattern_len, sim, drift)

        if best_fuzzy and highest_similarity >= self.fuzzy_threshold:
            return best_fuzzy

        return None

    @staticmethod
    def _normalize_line(line: str) -> str:
        """
        Normalizes line content for fuzzy comparison (removes whitespace variance).
        """
        return re.sub(r"\s+", " ", line.strip())
