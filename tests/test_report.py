"""Offline tests for PDF rendering. No LLM or network calls at all — this is
pure, deterministic rendering of a synthetic report object.
"""

from __future__ import annotations

from pathlib import Path

from agent.report import render_report_pdf, report_path_for
from agent.schemas import DeepResearchReport, ReportSection, Source


def _report() -> DeepResearchReport:
    return DeepResearchReport(
        topic="Acme & Co",
        subject_type="company",
        sections=[
            ReportSection(
                heading="Ownership & Corporate Structure",
                content="Acme is <privately> held & founder-led.",
                source_urls=["https://acme.example/about"],
            ),
            ReportSection(
                heading="Controversies & Legal Issues",
                content="No notable controversies were found in the available sources.",
                source_urls=[],
            ),
        ],
    )


def _sources() -> list[Source]:
    return [Source(url="https://acme.example/about", title="About & History")]


def test_render_report_pdf_produces_valid_pdf_file(tmp_path: Path) -> None:
    output_path = tmp_path / "run_1_acme.pdf"

    result_path = render_report_pdf(_report(), _sources(), output_path=output_path)

    assert result_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes()[:4] == b"%PDF"


def test_render_report_pdf_creates_parent_directory(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "dir" / "run_1_acme.pdf"

    render_report_pdf(_report(), _sources(), output_path=output_path)

    assert output_path.exists()


def test_report_path_for_builds_expected_filename(tmp_path: Path) -> None:
    path = report_path_for(5, "Acme Corp!", reports_dir=tmp_path)

    assert path == tmp_path / "run_5_acme-corp.pdf"


def test_report_path_for_handles_empty_slug(tmp_path: Path) -> None:
    path = report_path_for(1, "???", reports_dir=tmp_path)

    assert path == tmp_path / "run_1_topic.pdf"
