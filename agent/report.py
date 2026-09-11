"""Renders a DeepResearchReport to PDF. Pure and deterministic — no LLM or
network calls here, so it's fully testable with a synthetic report object.

Uses reportlab (pure Python, no system deps like libcairo/pango) — a new
project dependency added for --deep-research, see requirements.txt.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from agent.schemas import DeepResearchReport, Source


def _p(text: str, style: object) -> Paragraph:
    """Paragraph() parses its text as a small XML dialect — any literal '&',
    '<', or '>' in a heading (e.g. "Ownership & Corporate Structure") or in
    LLM-generated content breaks the parser unless escaped first."""
    return Paragraph(escape(text), style)


def report_path_for(run_id: int, topic: str, *, reports_dir: Path) -> Path:
    """Builds reports/run_{id}_{slug}.pdf — deterministic so callers and tests
    agree on the filename without reading it back from disk.
    """
    return reports_dir / f"run_{run_id}_{_slugify(topic)}.pdf"


def _slugify(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return slug or "topic"


def render_report_pdf(
    report: DeepResearchReport, sources: list[Source], *, output_path: Path
) -> Path:
    """Renders title/topic, generated-at timestamp, each section (heading +
    content + citing URLs), and a full source-list appendix (every fetched
    URL, not just cited ones — see CLAUDE.md: every claim must carry a
    source). Creates output_path's parent directory if it doesn't exist yet.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story = [
        _p(f"Deep Research Report: {report.topic}", styles["Title"]),
        _p(
            f"Subject type: {report.subject_type} — "
            f"generated {datetime.now(UTC):%Y-%m-%d %H:%M UTC}",
            styles["Normal"],
        ),
        Spacer(1, 18),
    ]
    for section in report.sections:
        story.append(_p(section.heading, styles["Heading2"]))
        story.append(_p(section.content, styles["BodyText"]))
        if section.source_urls:
            cited = ", ".join(section.source_urls)
            story.append(_p(f"Sources: {cited}", styles["Italic"]))
        story.append(Spacer(1, 12))

    story.append(_p("Appendix: All Fetched Sources", styles["Heading2"]))
    for source in sources:
        label = source.title or source.url
        story.append(_p(f"{label} — {source.url}", styles["Normal"]))

    SimpleDocTemplate(str(output_path), pagesize=LETTER).build(story)
    return output_path
