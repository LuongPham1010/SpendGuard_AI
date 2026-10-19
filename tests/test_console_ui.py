from fastapi.testclient import TestClient
from app.main import app


def test_console_page_serves_mission_control_view():
    with TestClient(app) as c:
        html = c.get("/console").text
        for phase in ("INTAKE", "GUARDRAIL", "PLAN", "PREFLIGHT", "EXECUTE", "REPLAN", "AWAIT_HUMAN", "REFLECT"):
            assert f'data-phase="{phase}"' in html
        for el in ("id=\"conversation\"", "id=\"vaults\"", "id=\"approvals\"", "id=\"audit-chain\"", "id=\"guardian-overlay\"", "id=\"quiz-modal\""):
            assert el in html
        assert "/static/js/console.js" in html and "/static/css/console.css" in html
        assert "cdn.tailwindcss.com" not in html


def test_legacy_dashboard_still_available():
    with TestClient(app) as c:
        r = c.get("/legacy")
        assert r.status_code == 200 and "tab-content-ghost" in r.text
        assert 'id="agent-hero"' in r.text and 'id="agent-rail"' in r.text


def test_health_reports_model_and_key_count():
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert "gemini_keys" in h and isinstance(h["gemini_keys"], int)
        assert "sandbox" in h and h["sandbox"] is True


def test_root_serves_mission_control_by_default():
    with TestClient(app) as c:
        html = c.get("/").text
        assert 'data-tab="tab-mission"' in html
        assert 'data-tab="tab-intelligence"' in html
        assert 'id="conversation"' in html
        for phase in ("INTAKE", "GUARDRAIL", "PLAN", "PREFLIGHT", "EXECUTE", "REPLAN", "AWAIT_HUMAN", "REFLECT"):
            assert f'data-phase="{phase}"' in html
        for el in ('id="conversation"', 'id="vaults"', 'id="approvals"', 'id="guardian-overlay"', 'id="quiz-modal"'):
            assert el in html


def test_mission_control_has_horizontal_dashboard_deck_below_chat():
    with TestClient(app) as c:
        html = c.get("/").text
        # Cockpit Option 1: Horizontal deck below chat containing vaults, approvals, and audit
        assert 'class="mission-deck"' in html
        conv_idx = html.find('id="conversation"')
        deck_idx = html.find('class="mission-deck"')
        assert conv_idx != -1 and deck_idx != -1
        # The deck must be located after the conversation in the DOM flow
        assert deck_idx > conv_idx


def test_voice_input_fills_the_box_and_never_sends_on_its_own():
    with TestClient(app) as client:
        html = client.get("/").text
        assert 'id="mic"' in html and 'id="mic-lang"' in html and 'id="intercept-speak"' in html
        js = client.get("/static/js/console.js").text
        assert "webkitSpeechRecognition" in js and "speechSynthesis" in js
        voice = js[js.index("function toggleMic"):js.index("function speechLang")]
        assert "send(" not in voice      # speech only fills the input; the user presses Send
        assert "continuous = true" in voice and "stopMic" in voice   # listens until the user presses stop
