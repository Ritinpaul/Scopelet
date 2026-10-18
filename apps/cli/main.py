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


capsule_app = typer.Typer(
    name="capsule",
    help="Build and execute independent reproduction capsules.",
)
app.add_typer(capsule_app, name="capsule")


@capsule_app.command(name="build")
def capsule_build_command(
    source_dir: Optional[Path] = typer.Option(None, "--source-dir", "-s", help="Directory with reduced candidate files"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Title describing the failure defect"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output .scopelet archive file path"),
    cmd: Optional[str] = typer.Option(None, "--cmd", "-c", help="Verification test command"),
    fingerprint: Optional[str] = typer.Option(None, "--fingerprint", "-f", help="Failure fingerprint"),
    allowed: Optional[list[str]] = typer.Option(None, "--allow", "-a", help="Allowed files for bugfix modification"),
) -> None:
    """
    Assembles a minimal reproduction capsule directory and packs it into a .scopelet archive.
    """
    import json
    import tempfile
    from scopelet.capsule import CapsuleBuilder, CapsulePackager
    from scopelet.reducer import CandidateState

    base_dir = (source_dir or Path(".scopelet/reduced")).resolve()
    if not base_dir.exists():
        base_dir = Path.cwd().resolve()

    # Detect metadata from .scopelet if available
    detected_title = title or "Deterministic Test Failure"
    detected_cmd = cmd or "npm test"
    detected_fp = fingerprint or ""

    session_json = base_dir / ".scopelet" / "session.json"
    if not session_json.exists():
        session_json = Path.cwd() / ".scopelet" / "session.json"
    if session_json.exists():
        try:
            s_data = json.loads(session_json.read_text(encoding="utf-8"))
            if not cmd and "command" in s_data:
                detected_cmd = s_data["command"]
            if not title and "failure" in s_data and "test" in s_data["failure"]:
                detected_title = s_data["failure"]["test"]
            if not fingerprint and "failure" in s_data and "fingerprint" in s_data["failure"]:
                detected_fp = s_data["failure"]["fingerprint"]
        except Exception:
            pass

    console.print("[bold blue]Scopelet Independent Capsule Builder[/bold blue]")
    console.print(f"[dim]Source Directory:[/dim] [yellow]{base_dir}[/yellow]")
    console.print(f"[dim]Title:[/dim] [bold]{detected_title}[/bold]")
    console.print(f"[dim]Command:[/dim] [cyan]{detected_cmd}[/cyan]\n")

    state = CandidateState.from_directory(base_dir)
    staging_dir = Path(tempfile.mkdtemp(prefix="scopelet_capsule_build_"))

    builder = CapsuleBuilder()
    manifest = builder.build(
        output_dir=staging_dir,
        state=state,
        title=detected_title,
        command=detected_cmd,
        failure_fingerprint=detected_fp,
        allowed_changes=allowed,
    )

    archive_target = (output or Path(f"{staging_dir.name}.scopelet")).resolve()
    CapsulePackager.pack(staging_dir, archive_target)

    # Clean staging files
    import shutil
    shutil.rmtree(staging_dir, ignore_errors=True)

    table = Table(title="Built Capsule Summary", show_header=True, header_style="bold green")
    table.add_column("Property", style="dim", width=22)
    table.add_column("Value", style="bold")

    table.add_row("Archive File", str(archive_target))
    table.add_row("Capsule Hash", f"[bold cyan]{manifest.capsule_hash}[/bold cyan]")
    table.add_row("Bundled Files", str(len(manifest.files)))
    table.add_row("Allowed Changes", str(len(manifest.allowed_changes)))
    if manifest.failure_fingerprint:
        table.add_row("Failure Fingerprint", manifest.failure_fingerprint[:16] + "...")

    console.print(table)
    console.print(f"\n[bold green][OK] Capsule successfully built:[/bold green] [cyan]{archive_target}[/cyan]")


@capsule_app.command(name="run")
def capsule_run_command(
    target: Path = typer.Argument(..., help="Path to .scopelet archive or extracted capsule directory"),
    dep_dir: Optional[Path] = typer.Option(None, "--dep-dir", "-d", help="Directory containing pre-installed node_modules"),
    timeout: int = typer.Option(60, "--timeout", "-t", help="Timeout in seconds"),
) -> None:
    """
    Executes a .scopelet capsule under isolated execution without original repository access.
    """
    from scopelet.capsule import CapsuleRunner

    target_path = target.resolve()
    console.print(f"[bold blue]Scopelet Capsule Standalone Runner[/bold blue]")
    console.print(f"[dim]Target:[/dim] [yellow]{target_path}[/yellow]\n")

    runner = CapsuleRunner()
    try:
        manifest, result = runner.run(
            capsule_target=target_path,
            dependency_dir=dep_dir,
            timeout=timeout,
        )
    except Exception as e:
        console.print(f"[bold red][FAIL] Capsule execution failed:[/bold red] {e}")
        raise typer.Exit(code=1)

    table = Table(title="Capsule Execution Verdict", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="dim", width=22)
    table.add_column("Value", style="bold")

    table.add_row("Title", manifest.title)
    table.add_row("Command", manifest.command)
    table.add_row("Exit Code", str(result.exit_code))
    table.add_row("Duration", f"{result.duration_ms} ms")
    if result.fingerprint:
        table.add_row("Received Fingerprint", f"[cyan]{result.fingerprint}[/cyan]")
    if manifest.failure_fingerprint:
        table.add_row("Expected Fingerprint", f"[dim]{manifest.failure_fingerprint}[/dim]")

    console.print(table)

    if result.fingerprint and result.fingerprint == manifest.failure_fingerprint:
        console.print(f"\n[bold green][OK] Verified standalone reproduction: Failure fingerprint matches exactly.[/bold green]")
    elif result.exit_code != 0:
        console.print(f"\n[bold yellow][WARN] Execution failed (exit code {result.exit_code}) but fingerprint differed.[/bold yellow]")
    else:
        console.print(f"\n[bold green][PASS] Execution passed without failure.[/bold green]")


@app.command(name="scan")
def scan_command(
    target: Path = typer.Argument(..., help="Path to capsule archive or workspace directory to scan"),
    canary: Optional[list[str]] = typer.Option(None, "--canary", "-k", help="Custom canary token string to detect"),
    entropy_threshold: float = typer.Option(4.5, "--entropy", help="Shannon entropy threshold for secret detection"),
) -> None:
    """
    Scans a capsule archive or directory for secrets, credentials, canaries and git history leaks.
    """
    from scopelet.privacy import PrivacyScanner

    target_path = target.resolve()
    console.print("[bold blue]Scopelet Privacy & Secret Scanner[/bold blue]")
    console.print(f"[dim]Scanning Target:[/dim] [yellow]{target_path}[/yellow]\n")

    canary_set = set(canary) if canary else set()
    scanner = PrivacyScanner(canaries=canary_set, entropy_threshold=entropy_threshold)

    try:
        report = scanner.scan(target_path)
    except Exception as e:
        console.print(f"[bold red][FAIL] Scan execution failed:[/bold red] {e}")
        raise typer.Exit(code=1)

    console.print(f"Scanned [bold cyan]{report.total_files_scanned}[/bold cyan] files. Detected [bold]{len(report.findings)}[/bold] finding(s).\n")

    if report.findings:
        table = Table(title="Privacy & Secret Findings", show_header=True, header_style="bold red")
        table.add_column("File", style="yellow", width=26)
        table.add_column("Line", style="dim", width=6)
        table.add_column("Category", style="cyan", width=18)
        table.add_column("Severity", style="bold", width=10)
        table.add_column("Description", style="white")
        table.add_column("Sample", style="dim")

        for f in report.findings:
            sev_color = "red" if f.severity in ("CRITICAL", "HIGH") else "yellow"
            sev_styled = f"[{sev_color}]{f.severity}[/{sev_color}]"
            table.add_row(
                f.file_path,
                str(f.line_number),
                f.category,
                sev_styled,
                f.description,
                f.matched_text,
            )

        console.print(table)

    if report.has_critical_leaks:
        console.print(f"\n[bold red][FAIL] Critical secrets or privacy leaks detected. Export blocked.[/bold red]")
        raise typer.Exit(code=1)
    else:
        console.print(f"\n[bold green][OK] Privacy scan passed with no critical leaks detected.[/bold green]")


@app.command(name="sanitize")
def sanitize_command(
    target: Path = typer.Argument(..., help="Path to workspace directory to sanitize"),
    command: str = typer.Option(..., "--command", "-c", help="Test command reproducing the failure"),
    fingerprint: str = typer.Option(..., "--fingerprint", "-f", help="Expected failure fingerprint to preserve"),
    canary: Optional[list[str]] = typer.Option(None, "--canary", "-k", help="Custom canary token string to anonymize"),
) -> None:
    """
    Sanitizes sensitive identifiers and canaries while verifying failure reproducibility after every change.
    """
    from scopelet.privacy.sanitizer import BehaviorPreservingSanitizer

    target_path = target.resolve()
    console.print("[bold blue]Scopelet Behavior-Preserving Sanitizer[/bold blue]")
    console.print(f"[dim]Target Workspace:[/dim] [yellow]{target_path}[/yellow]")
    console.print(f"[dim]Expected Fingerprint:[/dim] [cyan]{fingerprint[:16]}...[/cyan]\n")

    canary_set = set(canary) if canary else set()
    sanitizer = BehaviorPreservingSanitizer(
        workspace_dir=target_path,
        command=command,
        expected_fingerprint=fingerprint,
    )

    with console.status("[bold cyan]Discovering and sanitizing sensitive identifiers...[/bold cyan]"):
        mapping_store = sanitizer.auto_sanitize(canaries=canary_set)

    if mapping_store.mapping:
        table = Table(title="Sanitized Identifier Mappings", show_header=True, header_style="bold green")
        table.add_column("Original Identifier", style="yellow")
        table.add_column("Sanitized Pseudonym", style="bold cyan")

        for orig, pseudo in mapping_store.mapping.items():
            table.add_row(orig, pseudo)

        console.print(table)
        console.print(f"\n[bold green][SUCCESS] Sanitized {len(mapping_store.mapping)} sensitive identifier(s).[/bold green]")
        console.print(f"[dim]Private mapping saved to:[/dim] [yellow]{sanitizer.workspace_dir / '.scopelet' / 'private' / 'mapping.json'}[/yellow]")
    else:
        console.print("[dim]No sensitive identifiers required transformation.[/dim]")


@app.command(name="report")
def report_command(
    capsule_target: Path = typer.Argument(..., help="Path to capsule directory or .scopelet archive"),
    original: Optional[Path] = typer.Option(None, "--original", "-o", help="Path to original source workspace"),
    canary: Optional[list[str]] = typer.Option(None, "--canary", "-k", help="Custom canary tokens"),
    as_json: bool = typer.Option(False, "--json", help="Output report in JSON format"),
) -> None:
    """
    Generates a Scopelet privacy report comparing original workspace and capsule.
    """
    from scopelet.reports.privacy_report import PrivacyReportGenerator

    target_capsule = capsule_target.resolve()
    orig_dir = original.resolve() if original else target_capsule

    canary_set = set(canary) if canary else set()
    generator = PrivacyReportGenerator(canaries=canary_set)

    try:
        report_data = generator.generate_report(original_dir=orig_dir, capsule_target=target_capsule)
    except Exception as e:
        console.print(f"[bold red][FAIL] Privacy report generation failed:[/bold red] {e}")
        raise typer.Exit(code=1)

    if as_json:
        console.print(report_data.model_dump_json(indent=2))
    else:
        console.print(f"[bold blue]{report_data.format_text()}[/bold blue]")


if __name__ == "__main__":
    app()


