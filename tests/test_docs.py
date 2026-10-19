from pathlib import Path


def test_docs_exist_with_required_sections():
    td = Path("docs/technical_documentation.md").read_text(encoding="utf-8")
    for h in ("## Architecture", "## State machine", "## Tools", "## Guardian", "## Evaluation results", "## Deployment"):
        assert h in td
    ssa = Path("docs/security_self_assessment.md").read_text(encoding="utf-8")
    for h in ("## Permission-tier implementation", "## Known-risk list", "## Three-layer flow", "## Evidence"):
        assert h in ssa
    rd = Path("README.md").read_text(encoding="utf-8")
    assert "## Quickstart" in rd and "## Deliverable map" in rd
    for word in ("killer", "sát thương", "100% hoàn thiện", "cutting-edge", "revolutionary"):
        assert word not in rd.lower()
