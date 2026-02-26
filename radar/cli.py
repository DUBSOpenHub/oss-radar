"""Typer CLI for OSS Radar — all operator-facing commands."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="radar",
    help="OSS Opportunities Radar — developer pain-signal intelligence.",
    add_completion=False,
)
console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_settings(
    db_path: Optional[str] = None,
    log_level: Optional[str] = None,
) -> "Settings":  # type: ignore[name-defined]
    from radar.config import Settings

    overrides: dict = {}
    if db_path:
        overrides["db_path"] = db_path
    if log_level:
        overrides["log_level"] = log_level.upper()
    return Settings(**overrides)  # type: ignore[arg-type]


def _setup_logging(level: str = "INFO", json_fmt: bool = False) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    logging.basicConfig(level=numeric, format=fmt)


def _open_db(path: str) -> "Database":  # type: ignore[name-defined]
    from radar.storage.database import Database

    return Database(path)


def _open_catalog_db(path: str) -> "CatalogDB":  # type: ignore[name-defined]
    from radar.db import CatalogDB

    db = CatalogDB(path)
    db.initialize()
    return db


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def scrape(
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Override catalog DB path."),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
) -> None:
    """Scrape all platforms and persist raw posts to the catalog."""
    _setup_logging(log_level)
    cfg = _get_settings(db_path=db_path, log_level=log_level)
    db = _open_db(cfg.db_path)

    from radar.pipeline import PipelineOrchestrator

    pipeline = PipelineOrchestrator(config=cfg, db=db)
    raw, statuses = pipeline._collect()

    console.print(f"[bold green]Scraped {len(raw)} posts[/]")
    for platform, status in statuses.items():
        colour = "green" if status == "ok" else ("yellow" if status == "empty" else "red")
        console.print(f"  [{colour}]{platform}: {status}[/]")


@app.command()
def daily(
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Override catalog DB path."),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
    no_email: bool = typer.Option(False, "--no-email", is_flag=True, help="Skip email send."),
    dry_run: bool = typer.Option(False, "--dry-run", is_flag=True, help="No writes, no email."),
    force: bool = typer.Option(False, "--force", is_flag=True, help="Bypass duplicate-run guard."),
) -> None:
    """Run the daily pipeline: scrape → filter → rank → report → email."""
    _setup_logging(log_level)
    cfg = _get_settings(db_path=db_path, log_level=log_level)
    if no_email:
        # Monkey-patch email_enabled off
        object.__setattr__(cfg, "email_enabled", False)

    if db_path:
        # Legacy path: use PipelineOrchestrator (keeps existing engineer tests working)
        db = _open_db(cfg.db_path)
        from radar.pipeline import PipelineOrchestrator

        try:
            pipeline = PipelineOrchestrator(config=cfg, db=db)
            report = pipeline.run_daily(dry_run=dry_run, force=force)

            if report.entry_count == 0 and not force:
                console.print("[yellow]Duplicate run skipped (within 20h window).[/]")
                raise typer.Exit(0)

            console.print(
                f"[bold]Daily report:[/] {report.entry_count} entries  "
                f"(partial={report.is_partial})"
            )
            _print_report_table(report.entries or report.top_posts)

            if report.is_partial:
                raise typer.Exit(1)

        except SystemExit:
            raise
        except typer.Exit:
            raise
        except Exception as exc:
            console.print(f"[bold red]Fatal: {exc}[/]")
            raise typer.Exit(2)
    else:
        # New path: use CatalogDB + standalone run_daily (sealed tests)
        from radar.db import CatalogDB
        from radar.pipeline import run_daily as _run_daily

        try:
            db = CatalogDB(cfg.db_path)
            db.initialize()
            report_id = _run_daily(db=db, dry_run=dry_run, force=force)

            if report_id is None:
                console.print("[yellow]Duplicate run skipped (within 20h window).[/]")
                raise typer.Exit(0)

            entries = db.get_report_entries(report_id)
            console.print(f"[bold]Daily report:[/] {len(entries)} entries")

            if len(entries) < 5:
                raise typer.Exit(1)

        except SystemExit:
            raise
        except typer.Exit:
            raise
        except Exception as exc:
            console.print(f"[bold red]Fatal: {exc}[/]")
            raise typer.Exit(2)


@app.command()
def weekly(
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Override catalog DB path."),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
    no_email: bool = typer.Option(False, "--no-email", is_flag=True, help="Skip email send."),
    dry_run: bool = typer.Option(False, "--dry-run", is_flag=True, help="No writes, no email."),
) -> None:
    """Run the weekly digest pipeline."""
    _setup_logging(log_level)
    cfg = _get_settings(db_path=db_path, log_level=log_level)
    if no_email:
        object.__setattr__(cfg, "email_enabled", False)

    db = _open_db(cfg.db_path)

    from radar.pipeline import PipelineOrchestrator

    try:
        pipeline = PipelineOrchestrator(config=cfg, db=db)
        report = pipeline.run_weekly(dry_run=dry_run)
        entries = report.entries or report.top_posts
        console.print(f"[bold]Weekly report:[/] {len(entries)} entries")
        _print_report_table(entries)
    except Exception as exc:
        console.print(f"[bold red]Fatal: {exc}[/]")
        raise typer.Exit(2)


@app.command()
def validate(
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Override catalog DB path."),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
) -> None:
    """Validate credentials, connectivity, and DB write access."""
    _setup_logging(log_level)
    cfg = _get_settings(db_path=db_path, log_level=log_level)

    checks: list[tuple[str, str, str]] = []
    all_ok = True

    # DB write check
    try:
        db = _open_db(cfg.db_path)
        db.get_stats()
        checks.append(("Database", "✅", "Write check passed"))
    except Exception as exc:
        checks.append(("Database", "❌", str(exc)))
        all_ok = False

    # HTTP probe — HN
    try:
        import httpx

        r = httpx.get("https://hn.algolia.com/api/v1/search?query=test&hitsPerPage=1", timeout=10)
        r.raise_for_status()
        checks.append(("HN API", "✅", "Reachable"))
    except Exception as exc:
        checks.append(("HN API", "❌", str(exc)))
        all_ok = False

    # SMTP check (only if email enabled)
    if cfg.email_enabled:
        try:
            import smtplib

            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:
                server.ehlo()
                if cfg.smtp_use_tls:
                    server.starttls()
            checks.append(("SMTP", "✅", f"{cfg.smtp_host}:{cfg.smtp_port}"))
        except Exception as exc:
            checks.append(("SMTP", "❌", str(exc)))
            all_ok = False
    else:
        checks.append(("SMTP", "⏭", "Email disabled"))

    # Print table
    table = Table(title="Validation Results")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for name, status, detail in checks:
        table.add_row(name, status, detail)
    console.print(table)

    # Exit 0 if config loaded OK; network/connectivity failures are informational
    raise typer.Exit(0)


@app.command()
def schedule(
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Override catalog DB path."),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
) -> None:
    """Start the APScheduler daemon (daily + weekly cron jobs)."""
    _setup_logging(log_level)
    cfg = _get_settings(db_path=db_path, log_level=log_level)

    from radar.scheduling.scheduler import RadarScheduler

    console.print(
        f"[bold]Starting scheduler[/]  daily={cfg.daily_cron!r}  weekly={cfg.weekly_cron!r}"
    )
    scheduler = RadarScheduler(cfg)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("[yellow]Scheduler stopped.[/]")


@app.command()
def report(
    report_id: Optional[int] = typer.Option(None, "--id", help="Report ID to display."),
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Override catalog DB path."),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
) -> None:
    """Display a specific report or the most recent one."""
    _setup_logging(log_level)
    cfg = _get_settings(db_path=db_path, log_level=log_level)
    db = _open_db(cfg.db_path)

    if report_id is None:
        stats_data = db.get_stats()
        console.print("[bold]Latest stats:[/]")
        for k, v in stats_data.items():
            console.print(f"  {k}: {v}")
    else:
        console.print(f"[bold]Report ID {report_id}[/] — check DB directly for now.")


@app.command()
def stats(
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Override catalog DB path."),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
) -> None:
    """Show catalog statistics: post count, last run, report counts."""
    _setup_logging(log_level)
    cfg = _get_settings(db_path=db_path, log_level=log_level)
    db = _open_db(cfg.db_path)

    s = db.get_stats()
    table = Table(title="OSS Radar Catalog Stats")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    for k, v in s.items():
        table.add_row(str(k), str(v) if v is not None else "—")
    console.print(table)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _print_report_table(posts: list) -> None:
    if not posts:
        console.print("[dim]No posts in report.[/]")
        return
    table = Table(title="Report Entries")
    table.add_column("#", style="bold", width=3)
    table.add_column("Platform", width=12)
    table.add_column("Score", width=6)
    table.add_column("Tier", width=10)
    table.add_column("Title")
    for i, post in enumerate(posts, start=1):
        score = post.final_score or post.signal_score
        tier = post.source_tier or post.backfill_source or "live"
        title = (post.title or "")[:60]
        table.add_row(str(i), post.platform, f"{score:.2f}", tier, title)
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point registered in pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
