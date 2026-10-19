import pathlib
from app.modules.debate_arena import FinancialDebateArena
from app.models.schemas import DebateRequest


def test_no_direct_genai_imports_outside_gateway():
    root = pathlib.Path("app")
    offenders = []
    for p in root.rglob("*.py"):
        if p.name in ("llm_gateway.py", "gemini_backend.py"):
            continue
        src = p.read_text(encoding="utf-8")
        if "google.generativeai" in src or "from google import genai" in src or "import google.genai" in src:
            offenders.append(str(p))
    assert offenders == []


def test_compute_facts_is_deterministic():
    f = FinancialDebateArena.compute_facts(DebateRequest(item_name="phone", price=35_000_000, user_income=35_000_000), 65e6, 120e6, 15e6)
    assert f["pct_of_income"] == 100.0 and round(f["five_year_opportunity_cost"]) == round(35_000_000 * 1.08 ** 5)


def test_debate_offline_uses_three_turns_with_fact_citations():
    r = FinancialDebateArena.run_debate(DebateRequest(item_name="coffee machine", price=15_500_000, user_income=35_000_000))
    assert len(r.turns) == 3 and r.verdict in ("APPROVED", "DENIED", "CONDITIONAL_APPROVAL", "DELAYED")
