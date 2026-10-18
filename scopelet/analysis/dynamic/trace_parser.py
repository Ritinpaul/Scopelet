"""
V8 coverage parser for dynamic execution tracing.
Extracts executed repository files and function ranges from V8 coverage JSON files.
"""

from pathlib import Path
from typing import Set, Dict, List, Any, Optional
import json
import urllib.parse
from pydantic import BaseModel, Field


class FunctionCoverage(BaseModel):
    name: str
    is_block_coverage: bool = False
    execution_count: int = 0


class FileCoverage(BaseModel):
    file_path: str
    functions: List[FunctionCoverage] = Field(default_factory=list)
    executed: bool = True


class DynamicTraceResult(BaseModel):
    executed_files: Set[str] = Field(default_factory=set)
    file_details: Dict[str, FileCoverage] = Field(default_factory=dict)
    total_coverage_files_inspected: int = 0


def normalize_v8_url(url: str, repo_root: Path) -> Optional[str]:
    """
    Normalizes a V8 coverage URL (file://) to a repository-relative path.
    Returns None if the file is outside the repository or inside node_modules.
    """
    if not url or not url.startswith("file://"):
        return None

    # Parse and unquote URL
    parsed = urllib.parse.urlparse(url)
    path_str = urllib.parse.unquote(parsed.path)

    # Windows drive letter fix: /D:/foo -> D:/foo
    if len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
        path_str = path_str[1:]

    try:
        resolved_path = Path(path_str).resolve()
        resolved_repo = repo_root.resolve()

        # Check if file resides inside the repository
        rel_path = resolved_path.relative_to(resolved_repo).as_posix()

        # Ignore dependencies, version control and tool caches
        parts = rel_path.split("/")
        if any(p in ("node_modules", ".git", ".scopelet", "dist", "build", ".vitest", ".pytest_cache") for p in parts):
            return None

        return rel_path
    except (ValueError, OSError):
        return None


def parse_v8_coverage_dir(coverage_dir: Path, repo_root: Path) -> DynamicTraceResult:
    """
    Parses all V8 coverage JSON files in a directory and aggregates executed repository files.
    """
    coverage_dir_path = Path(coverage_dir)
    if not coverage_dir_path.exists():
        return DynamicTraceResult()

    json_files = list(coverage_dir_path.glob("*.json"))
    executed_files: Set[str] = set()
    file_details: Dict[str, FileCoverage] = {}

    for jf in json_files:
        try:
            content = jf.read_text(encoding="utf-8", errors="replace")
            data = json.loads(content)
            results = data.get("result", [])

            for entry in results:
                url = entry.get("url", "")
                rel_path = normalize_v8_url(url, repo_root)
                if not rel_path:
                    continue

                # Inspect execution counts across function ranges
                functions_data = entry.get("functions", [])
                total_exec_count = 0
                fn_coverages: List[FunctionCoverage] = []

                for fn in functions_data:
                    fn_name = fn.get("functionName", "") or "<anonymous>"
                    is_block = fn.get("isBlockCoverage", False)
                    ranges = fn.get("ranges", [])
                    fn_count = sum(r.get("count", 0) for r in ranges)
                    total_exec_count += fn_count

                    if fn_count > 0:
                        fn_coverages.append(
                            FunctionCoverage(
                                name=fn_name,
                                is_block_coverage=is_block,
                                execution_count=fn_count,
                            )
                        )

                # A file was executed if any block/function had execution count > 0
                if total_exec_count > 0 or not functions_data:
                    executed_files.add(rel_path)
                    if rel_path not in file_details:
                        file_details[rel_path] = FileCoverage(
                            file_path=rel_path,
                            functions=fn_coverages,
                            executed=True,
                        )
                    else:
                        file_details[rel_path].functions.extend(fn_coverages)

        except Exception:
            continue

    return DynamicTraceResult(
        executed_files=executed_files,
        file_details=file_details,
        total_coverage_files_inspected=len(json_files),
    )
