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
    cmd: Optional[str] = typer.Option(None, "--cmd", "-c", help="Test command to run for dynamic runtime coverage tracing"),
    mermaid: bool = typer.Option(False, "--mermaid", "-m", help="Output Mermaid dependency diagram"),
) -> None:
    """
    Constructs the static repository dependency graph and performs reachability analysis.
    Optionally executes dynamic runtime tracing to produce an optimized candidate slice.
    """
    from scopelet.analysis.static import TypeScriptAnalyzer
    from scopelet.analysis.dynamic import DynamicTracer, compute_candidate_slice

    target_cwd = (cwd or Path.cwd()).resolve()
    console.print(f"[bold blue]Scopelet Analysis Engine[/bold blue]")
    console.print(f"[dim]Analyzing repository in:[/dim] [yellow]{target_cwd}[/yellow]...\n")

    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(target_cwd)

    total_files = len(graph.nodes)
    console.print(f"Discovered [bold cyan]{total_files}[/bold cyan] source files.")

    # Determine entry points and stack frames
    entry_points = [entry] if entry else []
    stack_frames = []
    detected_cmd = cmd

    failure_json = target_cwd / ".scopelet" / "failure.json"
    session_json = target_cwd / ".scopelet" / "session.json"

    if failure_json.exists():
        import json
        try:
            data = json.loads(failure_json.read_text(encoding="utf-8"))
            frames = data.get("frames", [])
            stack_frames.extend(frames)
            if not entry_points:
                entry_points.extend(frames)
        except Exception:
            pass

    if not detected_cmd and session_json.exists():
        import json
        try:
            s_data = json.loads(session_json.read_text(encoding="utf-8"))
            detected_cmd = s_data.get("command")
        except Exception:
            pass

    # Optional dynamic tracing
    dynamic_trace_result = None
    if detected_cmd:
        console.print(f"\n[bold magenta]Tracing runtime execution:[/bold magenta] [cyan]{detected_cmd}[/cyan]...")
        tracer = DynamicTracer()
        report = tracer.trace(detected_cmd, target_cwd)
        dynamic_trace_result = report.trace
        console.print(f"Dynamic execution recorded [bold green]{len(dynamic_trace_result.executed_files)}[/bold green] executed repository files.")

    if entry_points or dynamic_trace_result:
        all_repo_files = set(graph.nodes.keys())
        if dynamic_trace_result:
            slice_result = compute_candidate_slice(
                static_graph=graph,
                dynamic_trace=dynamic_trace_result,
                stack_frames=stack_frames or entry_points,
                all_files=all_repo_files,
            )

            table = Table(title="Candidate Slice Analysis", show_header=True, header_style="bold green")
            table.add_column("Category", style="dim", width=25)
            table.add_column("Count", style="bold")
            table.add_column("Percentage", style="cyan")

            table.add_row("Total Repository Files", str(slice_result.total_files_count), "100.0%")
            pct_static = (len(slice_result.static_reachable) / slice_result.total_files_count * 100) if slice_result.total_files_count else 0
            table.add_row("Static Reachable Set", str(len(slice_result.static_reachable)), f"{pct_static:.1f}%")
            pct_dyn = (len(slice_result.dynamic_executed) / slice_result.total_files_count * 100) if slice_result.total_files_count else 0
            table.add_row("Dynamic Executed Set", str(len(slice_result.dynamic_executed)), f"{pct_dyn:.1f}%")
            table.add_row("Stack Frame Roots", str(len(slice_result.stack_frames)), "-")
            pct_comb = (slice_result.slice_count / slice_result.total_files_count * 100) if slice_result.total_files_count else 0
            table.add_row("Combined Candidate Slice", str(slice_result.slice_count), f"{pct_comb:.1f}%")
            table.add_row("Pruned Files", str(len(slice_result.pruned_files)), f"{slice_result.reduction_percentage:.1f}%")

            console.print(table)

            tree_lines = []
            for rf in slice_result.combined_slice:
                tag = "[bold cyan](dynamic)[/bold cyan]" if rf in slice_result.dynamic_executed else "[dim](static dep)[/dim]"
                if rf in slice_result.stack_frames:
                    tag = "[bold red](stack root)[/bold red]"
                tree_lines.append(f"  * [green]{rf}[/green] {tag}")

            console.print(Panel("\n".join(tree_lines), title="Optimal Candidate Slice", border_style="green"))

        else:
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

        if mermaid and entry_points:
            console.print(Panel(graph.to_mermaid(entry_points), title="Mermaid Dependency Flowchart", border_style="cyan"))
    else:
        console.print("[dim]Tip: specify --entry <test.ts> or --cmd <npm test> to compute candidate slice.[/dim]")


@app.command(name="reduce")
def reduce_command(
    cmd: Optional[str] = typer.Option(None, "--cmd", "-c", help="Test execution command (default: auto-detected or 'npm test')"),
    cwd: Optional[Path] = typer.Option(None, "--cwd", "-d", help="Working directory path (default: current directory)"),
    fingerprint: Optional[str] = typer.Option(None, "--fingerprint", "-f", help="Target failure fingerprint (default: auto-detected)"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Target output directory for reduced reproduction"),
    max_evals: int = typer.Option(500, "--max-evals", help="Maximum oracle evaluations allowed"),
    use_slice: bool = typer.Option(True, "--use-slice/--no-slice", help="Pre-filter using static and dynamic candidate slice"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Run without live step reporting"),
) -> None:
    """
    Minimizes repository to smallest reproducible candidate preserving the exact failure fingerprint.
    """
    import json
    import tempfile
    from scopelet.reducer import (
        CandidateState,
        ReducerOracle,
        ReducerCache,
        ReducerProgress,
        DeltaDebuggingReducer,
    )
    from scopelet.analysis.static import TypeScriptAnalyzer
    from scopelet.analysis.dynamic import DynamicTracer, compute_candidate_slice

    target_cwd = (cwd or Path.cwd()).resolve()
    target_output_dir = output_dir or (target_cwd / ".scopelet" / "reduced")

    detected_cmd = cmd
    detected_fingerprint = fingerprint
    stack_frames: list[str] = []

    failure_json = target_cwd / ".scopelet" / "failure.json"
    session_json = target_cwd / ".scopelet" / "session.json"

    if failure_json.exists():
        try:
            f_data = json.loads(failure_json.read_text(encoding="utf-8"))
            if not detected_fingerprint:
                detected_fingerprint = f_data.get("fingerprint")
            stack_frames.extend(f_data.get("frames", []))
        except Exception:
            pass

    if not detected_cmd and session_json.exists():
        try:
            s_data = json.loads(session_json.read_text(encoding="utf-8"))
            detected_cmd = s_data.get("command")
        except Exception:
            pass

    if not detected_cmd:
        detected_cmd = "npm test"

    # If no fingerprint provided or cached, capture baseline now
    if not detected_fingerprint:
        console.print("[dim]No cached failure found. Running baseline capture...[/dim]")
        try:
            cap_result = capture(command=detected_cmd, cwd=target_cwd)
            detected_fingerprint = cap_result.failure.fingerprint
            stack_frames.extend(cap_result.failure.frames)
        except Exception as e:
            console.print(f"[bold red][FAIL] Unable to capture baseline failure:[/bold red] {e}")
            raise typer.Exit(code=1)

    console.print(f"[bold blue]Scopelet Behavior-Preserving Reducer[/bold blue]")
    console.print(f"[dim]Repository:[/dim] [yellow]{target_cwd}[/yellow]")
    console.print(f"[dim]Command:[/dim] [cyan]{detected_cmd}[/cyan]")
    console.print(f"[dim]Target Fingerprint:[/dim] [bold cyan]{detected_fingerprint}[/bold cyan]\n")

    initial_state = CandidateState.from_directory(target_cwd)

    # Optional candidate slice pre-filtering
    candidate_slice_files = None
    if use_slice:
        try:
            analyzer = TypeScriptAnalyzer()
            graph = analyzer.build_graph(target_cwd)
            tracer = DynamicTracer()
            report = tracer.trace(detected_cmd, target_cwd)
            slice_result = compute_candidate_slice(
                static_graph=graph,
                dynamic_trace=report.trace,
                stack_frames=stack_frames,
                all_files=set(graph.nodes.keys()),
            )
            candidate_slice_files = set(slice_result.combined_slice)
        except Exception as e:
            console.print(f"[dim yellow]Warning: Candidate slice computation skipped: {e}[/dim yellow]")

    # Create isolated workspace directory for candidate evaluations
    temp_workspace = Path(tempfile.mkdtemp(prefix="scopelet_reducer_"))
    cache_path = target_cwd / ".scopelet" / "reducer_cache.db"
    cache = ReducerCache(cache_path)

    oracle = ReducerOracle(
        command=detected_cmd,
        expected_fingerprint=detected_fingerprint,
        workspace_dir=temp_workspace,
        cache=cache,
    )

    progress = ReducerProgress(console=console, quiet=quiet)
    protected = set(stack_frames)

    reducer = DeltaDebuggingReducer(
        oracle=oracle,
        progress=progress,
        protected_files=protected,
        max_evaluations=max_evals,
    )

    try:
        final_state, summary = reducer.reduce(
            initial_state=initial_state,
            candidate_slice_files=candidate_slice_files,
        )

        # Materialize final minimal reproduction to output directory
        target_output_dir.mkdir(parents=True, exist_ok=True)
        final_state.materialize(target_output_dir, link_node_modules=True)

        progress.print_summary(
            initial_files=summary.initial_files,
            final_files=summary.final_files,
            initial_loc=summary.initial_loc,
            final_loc=summary.final_loc,
            evaluations=summary.total_evaluations,
            cache_hits=summary.cache_hits,
            output_dir=str(target_output_dir),
        )
    except Exception as e:
        console.print(f"[bold red][FAIL] Reduction failed:[/bold red] {e}")
        raise typer.Exit(code=1)
    finally:
        # Cleanup temporary workspace files (junction/symlink removed safely)
        try:
            import shutil
            shutil.rmtree(temp_workspace, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    app()

