"""
Scopelet CLI interface powered by Typer and Rich.
"""

from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from scopelet.capture import capture, NoFailureDetectedError

app = typer.Typer(
    name="scopelet",
    help="Scopelet - Behavior-Preserving Bug Minimization & Private Hidden Verification Engine",
    add_completion=False,
)
console = Console()


@app.command(name="capture")
def capture_command(
    cmd: str = typer.Option(..., "--cmd", "-c", help="The test or execution command to run and capture"),
    cwd: Optional[Path] = typer.Option(None, "--cwd", "-d", help="Working directory path (default: current directory)"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory for session artifacts (default: .scopelet)"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Timeout in seconds"),
) -> None:
    """
    Executes a test command, extracts the failure fingerprint and saves session artifacts.
    """
    target_cwd = (cwd or Path.cwd()).resolve()

    console.print(f"[bold blue]Scopelet Failure Capture Engine[/bold blue]")
    console.print(f"[dim]Running:[/dim] [cyan]{cmd}[/cyan] in [yellow]{target_cwd}[/yellow]...\n")

    try:
        result = capture(
            command=cmd,
            cwd=target_cwd,
            output_dir=output_dir,
            timeout=timeout,
        )
    except NoFailureDetectedError as e:
        console.print(f"[bold green][OK] Success:[/bold green] {e}")
        raise typer.Exit(code=0)
    except Exception as e:
        console.print(f"[bold red][FAIL] Capture Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    f = result.failure
    s = result.session

    table = Table(title="Captured Failure Summary", show_header=True, header_style="bold magenta")
    table.add_column("Property", style="dim", width=22)
    table.add_column("Value", style="bold")

    table.add_row("Exit Code", str(s.exit_code))
    table.add_row("Duration", f"{s.duration_ms} ms")
    table.add_row("Test Name", f.test)
    table.add_row("Exception", f.exception)
    if f.expected:
        table.add_row("Expected", f"[green]{f.expected}[/green]")
    if f.actual:
        table.add_row("Actual Received", f"[red]{f.actual}[/red]")
    table.add_row("Fingerprint", f"[bold cyan]{f.fingerprint}[/bold cyan]")
    if s.git_commit:
        table.add_row("Git Commit", s.git_commit[:10])
    table.add_row("Artifacts Dir", str(result.output_dir))

    console.print(table)

    if f.frames:
        frame_text = "\n".join(f"  * [yellow]{frame}[/yellow]" for frame in f.frames)
        console.print(Panel(frame_text, title="Relevant Stack Frames (Normalized)", border_style="blue"))

    console.print(f"\n[bold green][OK] Failure captured successfully.[/bold green] Oracle fingerprint: [cyan]{f.fingerprint}[/cyan]")


@app.command(name="run")
def run_command(
    cmd: str = typer.Option("npm test", "--cmd", "-c", help="Command to execute in isolated environment"),
    cwd: Optional[Path] = typer.Option(None, "--cwd", "-d", help="Working directory path (default: current directory)"),
    backend: str = typer.Option("auto", "--backend", "-b", help="Isolation backend: 'auto', 'docker', or 'local'"),
    use_cache: bool = typer.Option(True, "--cache/--no-cache", help="Enable or disable execution cache"),
    timeout: int = typer.Option(60, "--timeout", "-t", help="Timeout in seconds"),
) -> None:
    """
    Executes a command inside hermetically sealed isolation (Docker container or hardened local sandbox).
    """
    from scopelet.runner import IsolatedRunner

    target_cwd = (cwd or Path.cwd()).resolve()
    console.print(f"[bold blue]Scopelet Isolated Execution Runner[/bold blue]")
    console.print(f"[dim]Running:[/dim] [cyan]{cmd}[/cyan] in [yellow]{target_cwd}[/yellow]")
    console.print(f"[dim]Backend:[/dim] [magenta]{backend}[/magenta] | [dim]Cache:[/dim] [green]{use_cache}[/green]\n")

    force_backend = None
    if backend == "docker":
        force_backend = "docker"
    elif backend in ("local", "local_sandbox"):
        force_backend = "local_sandbox"

    runner = IsolatedRunner()
    result = runner.run(
        command=cmd,
        cwd=target_cwd,
        timeout=timeout,
        use_cache=use_cache,
        force_backend=force_backend,
    )

    table = Table(title="Isolated Execution Summary", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="dim", width=20)
    table.add_column("Value", style="bold")

    table.add_row("Backend", result.backend)
    table.add_row("Exit Code", str(result.exit_code))
    table.add_row("Duration", f"{result.duration_ms} ms")
    table.add_row("Served From Cache", "[green]YES[/green]" if result.cached else "[yellow]NO (executed)[/yellow]")
    table.add_row("Tree Hash", result.tree_hash[:16] + "...")
    if result.fingerprint:
        table.add_row("Fingerprint", f"[cyan]{result.fingerprint}[/cyan]")

    console.print(table)

    if result.exit_code != 0 and result.failure:
        safe_test = result.failure.test.encode("ascii", "replace").decode("ascii")
        console.print(f"\n[bold yellow]Captured Failure:[/bold yellow] {safe_test}")
        if result.failure.expected and result.failure.actual:
            safe_exp = result.failure.expected.encode("ascii", "replace").decode("ascii")
            safe_act = result.failure.actual.encode("ascii", "replace").decode("ascii")
            console.print(f"  Expected: [green]{safe_exp}[/green] | Received: [red]{safe_act}[/red]")

    if result.exit_code == 0:
        console.print(f"\n[bold green][OK] Execution passed under isolation.[/bold green]")
    else:
        console.print(f"\n[bold red][FAIL] Execution failed as expected under isolation (exit code {result.exit_code}).[/bold red]")


@app.command(name="analyze")
def analyze_command(
    cwd: Optional[Path] = typer.Option(None, "--cwd", "-d", help="Working directory path (default: current directory)"),
    entry: Optional[str] = typer.Option(None, "--entry", "-e", help="Entry point file to compute reachability from"),
    mermaid: bool = typer.Option(False, "--mermaid", "-m", help="Output Mermaid dependency diagram"),
) -> None:
    """
    Constructs the static repository dependency graph and performs reachability analysis.
    """
    from scopelet.analysis.static import TypeScriptAnalyzer

    target_cwd = (cwd or Path.cwd()).resolve()
    console.print(f"[bold blue]Scopelet Static Analysis Engine[/bold blue]")
    console.print(f"[dim]Analyzing repository in:[/dim] [yellow]{target_cwd}[/yellow]...\n")

    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(target_cwd)

    total_files = len(graph.nodes)
    console.print(f"Discovered [bold cyan]{total_files}[/bold cyan] source files.")

    # Determine entry points
    entry_points = [entry] if entry else []
    if not entry_points:
        # Default: auto-detect failing tests from .scopelet/failure.json if available
        failure_json = target_cwd / ".scopelet" / "failure.json"
        if failure_json.exists():
            import json
            try:
                data = json.loads(failure_json.read_text(encoding="utf-8"))
                entry_points.extend(data.get("frames", []))
            except Exception:
                pass

    if entry_points:
        console.print(f"Entry points: [magenta]{', '.join(entry_points)}[/magenta]")
        reachable_files = graph.reachable(entry_points)
        unreachable_files = set(graph.nodes.keys()) - reachable_files

        table = Table(title="Reachability Slice Summary", show_header=True, header_style="bold green")
        table.add_column("Category", style="dim", width=25)
        table.add_column("Count", style="bold")
        table.add_column("Percentage", style="cyan")

        table.add_row("Total Discovered Files", str(total_files), "100.0%")
        pct_reach = (len(reachable_files) / total_files * 100) if total_files else 0
        table.add_row("Reachable Dependency Slice", str(len(reachable_files)), f"{pct_reach:.1f}%")
        pct_unreach = (len(unreachable_files) / total_files * 100) if total_files else 0
        table.add_row("Unreachable (Safe to Prune)", str(len(unreachable_files)), f"{pct_unreach:.1f}%")

        console.print(table)

        tree_lines = []
        for rf in sorted(reachable_files):
            deps = graph.get_dependencies(rf)
            dep_count = f"({len(deps)} deps)" if deps else "(leaf)"
            tree_lines.append(f"  * [green]{rf}[/green] [dim]{dep_count}[/dim]")

        console.print(Panel("\n".join(tree_lines), title="Reachable Static Slice", border_style="green"))

        if mermaid:
            console.print(Panel(graph.to_mermaid(entry_points), title="Mermaid Dependency Flowchart", border_style="cyan"))
    else:
        console.print("[dim]Tip: specify --entry <path/to/test.ts> to compute reachability slice.[/dim]")


if __name__ == "__main__":
    app()
