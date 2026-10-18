"""
Pydantic data models for static analysis graph nodes and dependencies.
"""

from typing import List, Literal, Optional, Dict
from pydantic import BaseModel, Field

SymbolType = Literal["function", "class", "variable", "interface", "type", "module", "file"]


class GraphNode(BaseModel):
    """
    Represents a symbol or file node in the static dependency graph.
    """
    symbol: str = Field(..., description="Name of the symbol or file identifier")
    file: str = Field(..., description="Normalized relative path to the defining source file")
    imports: List[str] = Field(
        default_factory=list,
        description="List of symbols or files this node directly depends on"
    )
    imported_by: List[str] = Field(
        default_factory=list,
        description="List of symbols or files that depend on this node"
    )
    type: SymbolType = Field(default="file", description="Kind of code construct")
    loc: int = Field(default=0, description="Lines of code in construct or file")
