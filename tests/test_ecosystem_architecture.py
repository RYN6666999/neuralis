"""驗證整體架構定位文件存在且結構完整"""
from __future__ import annotations
import os, re, sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "specs" / "ecosystem-architecture.md"

REQUIRED_SECTIONS = [
    "架構總覽",
    "neuralis",
    "Scream Code",
    "AgentOS",
    "資料流",
    "現狀定位",
]
SECTION_RE = re.compile(r"^##\s+\d*\.?\s*(.+)", re.MULTILINE)


def test_file_exists():
    assert DOC_PATH.is_file(), (
        f"ecosystem-architecture.md not found at {DOC_PATH}"
    )


def test_has_yaml_frontmatter():
    content = DOC_PATH.read_text(encoding="utf-8")
    assert content.startswith("---"), "Missing YAML frontmatter start"
    end = content.find("---", 3)
    assert end > 3, "Missing YAML frontmatter end"
    frontmatter = content[3:end].strip()
    assert "title:" in frontmatter, "Missing title in frontmatter"
    assert "date:" in frontmatter, "Missing date in frontmatter"


def test_has_required_sections():
    content = DOC_PATH.read_text(encoding="utf-8")
    headings = SECTION_RE.findall(content)
    found = {h.strip() for h in headings}
    for section in REQUIRED_SECTIONS:
        matches = [f for f in found if section in f]
        assert matches, (
            f"Required section '{section}' not found in headings: {found}"
        )


def test_minimum_length():
    content = DOC_PATH.read_text(encoding="utf-8")
    assert len(content) > 2000, (
        f"Document too short ({len(content)} chars, need >2000)"
    )


def test_mentions_both_aris_and_scream():
    content = DOC_PATH.read_text(encoding="utf-8")
    assert "aris" in content.lower(), "Document should mention Aris"
    assert "scream" in content.lower(), "Document should mention Scream Code"
    assert "agentos" in content.lower(), "Document should mention AgentOS"


def test_has_diagram_or_flow():
    """包含架構圖或ASCII流程圖"""
    content = DOC_PATH.read_text(encoding="utf-8")
    has_ascii_flow = "──" in content or "│" in content or "└" in content
    has_mermaid = "```mermaid" in content
    has_image = ".png" in content or ".svg" in content
    assert has_ascii_flow or has_mermaid or has_image, (
        "Document should contain an architecture diagram"
    )
