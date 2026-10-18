"""
Rich live display and progress reporting for delta-debugging reduction.
"""

from __future__ import annotations

from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .oracle import OracleVerdict


class ReducerProgress:
    """
    Console reporter and live progress tracker for repository reduction.
    """

    def __init__(self, console: Optional[Console] = None, quiet: bool = False):
        self.console = console or Console()
        self.quiet = quiet

    def print_banner(self, repo_files: int, candidate_files: int, initial_loc: int) -> None:
        """Prints initial reduction session status."""
        if self.quiet:
            return

        self.console.print("\n[bold blue]Scopelet Behavior-Preserving Reducer[/bold blue]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim", width=22)
        table.add_column("Value", style="bold")

        table.add_row("Repository Files", str(repo_files))
        table.add_row("Initial Candidate Files", str(candidate_files))
        table.add_row("Initial Lines of Code", f"{initial_loc} LOC")
        self.console.print(table)
        self.console.print()

    def on_phase_start(self, phase_name: str, description: str) -> None:
        """Announces commencement of a reduction phase."""
        if self.quiet:
            return
        self.console.print(f"[bold magenta]=== {phase_name} ===[/bold magenta] [dim]({description})[/dim]")

    def on_step(
        self,
        target: str,
        verdict: OracleVerdict,
        current_files: int,
        current_loc: int,
        initial_loc: int,
        evaluations: int,
        cache_hits: int,
    ) -> None:
        """Reports the outcome of a trial candidate evaluation."""
        if self.quiet:
            return

        reduction_pct = ((initial_loc - current_loc) / initial_loc * 100) if initial_loc > 0 else 0.0

        if verdict == OracleVerdict.MATCH:
            status = "[bold green][OK] Failure preserved (pruned)[/bold green]"
        elif verdict == OracleVerdict.MISMATCH:
            status = "[bold yellow][REJECT] Failure lost (restored)[/bold yellow]"
        else:
            status = "[bold red][ERROR] Execution failed (restored)[/bold red]"

        self.console.print(
            f"  * {target:36} {status} | "
            f"[cyan]{current_files} files[/cyan] | [green]{current_loc} LOC[/green] ({reduction_pct:.1f}% reduced) | "
            f"evals: {evaluations} (cache hits: {cache_hits})"
        )

    def print_summary(
        self,
        initial_files: int,
        final_files: int,
        initial_loc: int,
        final_loc: int,
        evaluations: int,
        cache_hits: int,
        output_dir: Optional[str] = None,
    ) -> None:
        """Displays completion metrics and summary table."""
        if self.quiet:
            return

        file_reduction = ((initial_files - final_files) / initial_files * 100) if initial_files > 0 else 0.0
        loc_reduction = ((initial_loc - final_loc) / initial_loc * 100) if initial_loc > 0 else 0.0

        table = Table(title="Reduction Results Summary", show_header=True, header_style="bold green")
        table.add_column("Metric", style="dim", width=24)
        table.add_column("Initial", style="bold")
        table.add_column("Final", style="bold cyan")
        table.add_column("Reduction", style="green")

        table.add_row("Source Files", str(initial_files), str(final_files), f"{file_reduction:.1f}%")
        table.add_row("Lines of Code (LOC)", f"{initial_loc} LOC", f"{final_loc} LOC", f"{loc_reduction:.1f}%")
        table.add_row("Oracle Evaluations", "-", str(evaluations), "-")
        table.add_row("Cache Hits", "-", str(cache_hits), "-")
        if output_dir:
            table.add_row("Minimal Output Dir", "-", output_dir, "-")

        self.console.print()
        self.console.print(table)
        self.console.print(f"\n[bold green][OK] Repository successfully reduced with verified failure preservation.[/bold green]")
