"""Command-line interface: ``competitor-intel run --url ... --url ...``."""

from __future__ import annotations

from pathlib import Path

import typer

from .config import load_config

app = typer.Typer(
    add_completion=False,
    help="Competitor intelligence crew - turn competitor URLs into a report.",
)


@app.callback()
def _main() -> None:
    """Competitor intelligence crew CLI."""
    # Presence of a callback keeps `run` as an explicit subcommand.


@app.command()
def run(
    url: list[str] = typer.Option(
        ..., "--url", "-u", help="Competitor URL to analyse (repeatable)."
    ),
    output: Path = typer.Option(
        Path("reports"), "--output", "-o", help="Directory for the report files."
    ),
    stem: str = typer.Option("report", "--name", help="Report file name stem."),
    provider: str | None = typer.Option(
        None, "--provider", help="Override LLM provider (anthropic|openai)."
    ),
    model: str | None = typer.Option(None, "--model", help="Override LLM model id."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable the on-disk scrape cache."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose agents."),
) -> None:
    """Analyse one or more competitor URLs and write a Markdown + JSON report."""
    # Import here so `--help` and CLI parsing stay fast and crewai-free.
    from .report import write_report
    from .runner import run as run_flow

    config = load_config()
    if provider:
        config.provider = provider.lower()
    if model:
        config.model = model
    if no_cache:
        config.cache_enabled = False
    if verbose:
        config.verbose = True

    typer.echo(f"Analysing {len(url)} URL(s) with {config.model_string} ...")
    report = run_flow(url, config)

    paths = write_report(report, output, stem=stem)
    typer.echo(f"Wrote {paths['markdown']} and {paths['json']}")
    if report.cost:
        typer.echo(
            f"Tokens: {report.cost.total_usage.total_tokens:,} | "
            f"Estimated cost: ${report.cost.total_cost_usd:.4f}"
        )
    typer.echo(f"Usable pages: {sum(p.usable() for p in report.pages)}/{len(report.pages)}")


def main() -> None:  # pragma: no cover - thin wrapper
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
