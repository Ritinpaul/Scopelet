"""
Dependency graph representation and reachability traversal algorithms.
"""

from collections import deque
from typing import Dict, Set, List, Optional
from pydantic import BaseModel, Field
from .node import GraphNode


class DependencyGraph(BaseModel):
    """
    Directed dependency graph mapping files and symbols to their transitive dependencies.
    """
    nodes: Dict[str, GraphNode] = Field(default_factory=dict)
    forward_edges: Dict[str, Set[str]] = Field(default_factory=dict)
    reverse_edges: Dict[str, Set[str]] = Field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        """Adds or updates a node in the graph."""
        self.nodes[node.file] = node
        if node.file not in self.forward_edges:
            self.forward_edges[node.file] = set()
        if node.file not in self.reverse_edges:
            self.reverse_edges[node.file] = set()

    def add_edge(self, source: str, target: str) -> None:
        """
        Adds a directed dependency edge: source depends on target (source -> target).
        """
        if source not in self.forward_edges:
            self.forward_edges[source] = set()
        if target not in self.reverse_edges:
            self.reverse_edges[target] = set()

        self.forward_edges[source].add(target)
        self.reverse_edges[target].add(source)

        # Update node import lists if nodes exist
        if source in self.nodes and target not in self.nodes[source].imports:
            self.nodes[source].imports.append(target)
        if target in self.nodes and source not in self.nodes[target].imported_by:
            self.nodes[target].imported_by.append(source)

    def get_dependencies(self, file_path: str) -> Set[str]:
        """Returns direct dependencies of a file."""
        return self.forward_edges.get(file_path, set())

    def get_dependents(self, file_path: str) -> Set[str]:
        """Returns files that directly depend on file_path."""
        return self.reverse_edges.get(file_path, set())

    def reachable(self, entry_points: List[str]) -> Set[str]:
        """
        Traverses forward edges from entry_points (BFS) to compute the transitive
        closure of all reachable dependency files.
        """
        visited: Set[str] = set()
        queue = deque()

        for ep in entry_points:
            norm_ep = ep.replace("\\", "/").lstrip("./")
            visited.add(norm_ep)
            queue.append(norm_ep)

        while queue:
            current = queue.popleft()
            for dep in self.forward_edges.get(current, set()):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)

        return visited

    def to_mermaid(self, entry_points: Optional[List[str]] = None) -> str:
        """
        Generates a Mermaid flowchart string visualizing the dependency graph.
        """
        lines = ["flowchart TD"]
        focus = self.reachable(entry_points) if entry_points else set(self.nodes.keys())

        for src in sorted(focus):
            clean_src = src.replace("/", "_").replace(".", "_").replace("-", "_")
            for tgt in sorted(self.forward_edges.get(src, set())):
                if not entry_points or tgt in focus:
                    clean_tgt = tgt.replace("/", "_").replace(".", "_").replace("-", "_")
                    lines.append(f'    {clean_src}["{src}"] --> {clean_tgt}["{tgt}"]')

        return "\n".join(lines)
