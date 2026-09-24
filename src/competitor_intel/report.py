"""Render a :class:`RunReport` to Markdown and JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .models import RunReport


def to_json(report: RunReport) -> str:
    return report.model_dump_json(indent=2)


def _fmt_pricing(summary_pricing: list) -> str:
    if not summary_pricing:
        return "unknown"
    parts = []
    for tier in summary_pricing:
        parts.append(f"{tier.name}: {tier.price} ({tier.billing_period})")
    return "; ".join(parts)


def to_markdown(report: RunReport) -> str:
    """Render a human-readable Markdown report."""
    lines: list[str] = []
    lines.append("# Competitor Intelligence Report")
    lines.append("")
    lines.append(f"- **Seed URLs:** {', '.join(report.seed_urls)}")
    lines.append(f"- **Generated:** {report.started_at.isoformat()}")
    if report.cost:
        lines.append(
            f"- **Model:** `{report.cost.model}` | "
            f"**Tokens:** {report.cost.total_usage.total_tokens:,} | "
            f"**Est. cost:** ${report.cost.total_cost_usd:.4f}"
        )
    lines.append("")

    insights = report.insights
    if insights:
        lines.append("## Executive Overview")
        lines.append("")
        lines.append(insights.overview or "_No overview produced._")
        lines.append("")

        if insights.comparison:
            lines.append("## Comparison")
            lines.append("")
            lines.append("| Competitor | Entry price | Positioning | Standout features |")
            lines.append("| --- | --- | --- | --- |")
            for row in insights.comparison:
                feats = ", ".join(row.standout_features) or "-"
                lines.append(
                    f"| {row.company_name} | {row.entry_price} | {row.positioning} | {feats} |"
                )
            lines.append("")

        _bullet_section(lines, "Differentiators", insights.differentiators)
        _bullet_section(lines, "Market gaps", insights.market_gaps)
        _bullet_section(lines, "Threats", insights.threats)

        if insights.recommendation:
            lines.append("## Recommendation")
            lines.append("")
            lines.append(insights.recommendation)
            lines.append("")

    if report.summaries:
        lines.append("## Per-competitor summaries")
        lines.append("")
        faith_by_url = {f.url: f for f in report.faithfulness}
        for summary in report.summaries:
            lines.append(f"### {summary.company_name}")
            lines.append("")
            lines.append(f"- **Source:** {summary.url}")
            lines.append(f"- **Positioning:** {summary.positioning or 'unknown'}")
            lines.append(f"- **Target audience:** {summary.target_audience or 'unknown'}")
            lines.append(f"- **Pricing:** {_fmt_pricing(summary.pricing)}")
            if summary.features:
                lines.append(f"- **Features:** {', '.join(summary.features)}")
            faith = faith_by_url.get(summary.url)
            if faith:
                status = "PASS" if faith.passed else "BELOW THRESHOLD"
                lines.append(
                    f"- **Faithfulness:** {faith.score:.2f} ({status}), "
                    f"revisions: {summary.revision}"
                )
            lines.append("")

    if report.decisions:
        lines.append("## Orchestrator decision log")
        lines.append("")
        for decision in report.decisions:
            lines.append(f"- {decision}")
        lines.append("")

    if report.cost and report.cost.entries:
        lines.append("## Cost breakdown")
        lines.append("")
        lines.append("| Step | Tokens | Cost (USD) |")
        lines.append("| --- | --- | --- |")
        for entry in report.cost.entries:
            lines.append(
                f"| {entry.label} | {entry.usage.total_tokens:,} | ${entry.cost_usd:.4f} |"
            )
        lines.append(
            f"| **Total** | **{report.cost.total_usage.total_tokens:,}** | "
            f"**${report.cost.total_cost_usd:.4f}** |"
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _bullet_section(lines: list[str], title: str, items: list[str]) -> None:
    if not items:
        return
    lines.append(f"## {title}")
    lines.append("")
    for item in items:
        lines.append(f"- {item}")
    lines.append("")


def write_report(report: RunReport, out_dir: Path | str, stem: str = "report") -> dict[str, Path]:
    """Write both Markdown and JSON reports; return the written paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"{stem}.md"
    json_path = out / f"{stem}.json"
    md_path.write_text(to_markdown(report), "utf-8")
    json_path.write_text(to_json(report), "utf-8")
    return {"markdown": md_path, "json": json_path}


def load_report(path: Path | str) -> RunReport:
    data = json.loads(Path(path).read_text("utf-8"))
    return RunReport.model_validate(data)
