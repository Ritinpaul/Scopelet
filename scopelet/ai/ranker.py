"""
AI Relevance Ranker engine.
Scores candidate files by bug relevance using local open-weight LLMs (Ollama)
with robust heuristic fallback and graceful degradation.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Set

from .models import FileRanking, RankerResponse, RankingEvaluationMetrics
from .prompts import RANKER_SYSTEM_PROMPT, build_ranking_prompt


class AIRelevanceRanker:
    """
    Ranks repository candidate files using local AI models with guaranteed graceful degradation.
    The ranker only modulates priority order during reduction and never unilaterally deletes files.
    """

    def __init__(
        self,
        model: str = "llama3.2",
        endpoint_url: str = "http://localhost:11434/api/generate",
        timeout_seconds: float = 5.0,
        enable_fallback: bool = True,
    ):
        self.model = model
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self.enable_fallback = enable_fallback

    def rank_files(
        self,
        candidate_files: List[str],
        failure_summary: str,
        stack_frames: Optional[List[str]] = None,
    ) -> RankerResponse:
        """
        Ranks candidate files by bug relevance.
        Falls back gracefully if the local AI service is offline or fails to respond.
        """
        if not candidate_files:
            return RankerResponse(rankings=[], model=self.model, latency_ms=0, fallback_used=False)

        start_time = time.time()
        prompt = build_ranking_prompt(
            failure_summary=failure_summary,
            candidate_files=candidate_files,
            stack_frames=stack_frames,
        )

        try:
            raw_text = self._query_endpoint(prompt)
            rankings = self._parse_json_response(raw_text, candidate_files)
            latency = int((time.time() - start_time) * 1000)
            return RankerResponse(
                rankings=rankings,
                model=self.model,
                latency_ms=latency,
                fallback_used=False,
            )
        except Exception:
            if not self.enable_fallback:
                raise

            latency = int((time.time() - start_time) * 1000)
            fallback_rankings = self._fallback_rankings(candidate_files, stack_frames)
            return RankerResponse(
                rankings=fallback_rankings,
                model=f"{self.model}-fallback",
                latency_ms=latency,
                fallback_used=True,
            )

    def _query_endpoint(self, user_prompt: str) -> str:
        """
        Executes HTTP request against local Ollama or OpenAI-compatible generation endpoint.
        """
        payload = {
            "model": self.model,
            "prompt": f"{RANKER_SYSTEM_PROMPT}\n\n{user_prompt}",
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint_url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
            resp_body = response.read().decode("utf-8")
            data = json.loads(resp_body)
            # Ollama returns output in "response", openai in "choices[0].text" or "message"
            if "response" in data:
                return data["response"]
            elif "choices" in data and data["choices"]:
                choice = data["choices"][0]
                if "text" in choice:
                    return choice["text"]
                elif "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"]
            raise ValueError(f"Unrecognized response format from endpoint: {list(data.keys())}")

    def _parse_json_response(self, text: str, expected_files: List[str]) -> List[FileRanking]:
        """
        Parses LLM output JSON, extracting and bounding relevance scores.
        """
        # Strip potential code block formatting
        cleaned = text.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)

        # Locate first '{' and last '}'
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx : end_idx + 1]

        parsed = json.loads(cleaned)
        raw_list = parsed.get("rankings", [])

        rankings_map: Dict[str, FileRanking] = {}
        for item in raw_list:
            fname = item.get("file", "").strip()
            score = float(item.get("relevance", 0.5))
            score = max(0.0, min(1.0, score))
            reason = item.get("reason", "AI relevance assessment")
            if fname:
                rankings_map[fname] = FileRanking(file=fname, relevance=score, reason=reason)

        # Ensure all expected files are present in the returned rankings
        result: List[FileRanking] = []
        for f in expected_files:
            if f in rankings_map:
                result.append(rankings_map[f])
            else:
                # Match by basename if relative prefix differed
                base = Path(f).name
                matched = None
                for k, v in rankings_map.items():
                    if Path(k).name == base:
                        matched = FileRanking(file=f, relevance=v.relevance, reason=v.reason)
                        break
                result.append(matched or FileRanking(file=f, relevance=0.5, reason="Default neutral score"))

        return result

    def _fallback_rankings(
        self,
        candidate_files: List[str],
        stack_frames: Optional[List[str]] = None,
    ) -> List[FileRanking]:
        """
        Deterministic heuristic fallback when the AI service is unavailable.
        Prioritizes stack frame matches, co-located modules and test runners.
        """
        frame_files = set()
        frame_dirs = set()
        if stack_frames:
            for fr in stack_frames:
                clean_fr = fr.replace("\\", "/").split(":")[0].strip()
                frame_files.add(clean_fr)
                frame_dirs.add(str(Path(clean_fr).parent).replace("\\", "/"))

        rankings: List[FileRanking] = []
        for f in candidate_files:
            norm_f = f.replace("\\", "/")
            f_dir = str(Path(norm_f).parent).replace("\\", "/")

            if any(norm_f == fr or norm_f.endswith(fr) for fr in frame_files):
                score = 0.95
                reason = "Heuristic match: directly cited in failure stack frames"
            elif f_dir in frame_dirs:
                score = 0.70
                reason = "Heuristic match: co-located in directory of failing module"
            elif "test" in norm_f.lower():
                score = 0.60
                reason = "Heuristic match: test fixture or execution harness"
            else:
                score = 0.40
                reason = "Heuristic baseline: non-stack candidate file"

            rankings.append(FileRanking(file=f, relevance=score, reason=reason))

        return rankings

    @staticmethod
    def compute_benchmark_metrics(
        rankings: List[FileRanking],
        ground_truth_relevant: Set[str],
        k: Optional[int] = None,
    ) -> RankingEvaluationMetrics:
        """
        Calculates recall and evaluation savings for AI ranking validation benchmarks.
        """
        if not ground_truth_relevant or not rankings:
            return RankingEvaluationMetrics(
                relevant_file_recall=1.0,
                initial_candidate_count=len(rankings),
                evaluations_saved=0,
            )

        # Sort candidate files by descending relevance score
        sorted_files = [r.file for r in sorted(rankings, key=lambda x: x.relevance, reverse=True)]
        top_k_count = k or max(len(ground_truth_relevant) * 2, 3)
        top_k_set = set(sorted_files[:top_k_count])

        hits = sum(1 for gt in ground_truth_relevant if gt in top_k_set or any(f.endswith(gt) for f in top_k_set))
        recall = hits / len(ground_truth_relevant)

        # Estimated reducer evaluations saved by attempting low-relevance files first
        total_count = len(rankings)
        low_relevance_count = sum(1 for r in rankings if r.relevance < 0.5)
        evaluations_saved = max(0, int(low_relevance_count * 0.75))

        return RankingEvaluationMetrics(
            relevant_file_recall=round(recall, 3),
            initial_candidate_count=total_count,
            evaluations_saved=evaluations_saved,
        )
