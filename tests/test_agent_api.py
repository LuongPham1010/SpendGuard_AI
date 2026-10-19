from fastapi.testclient import TestClient
from app.main import app


def test_chat_endpoint_and_approvals_roundtrip():
    with TestClient(app) as client:
        r = client.post("/api/agent/chat", data={"text": "move 7 million from main wallet to emergency vault", "session_id": "api1"})
        assert r.status_code == 200
        body = r.json()
        assert body["queued"] and body["queued"][0]["tool"] == "transfer_internal"
        rid = body["queued"][0]["id"]
        pending = client.get("/api/agent/approvals").json()
        assert any(p["id"] == rid for p in pending["pending"])
        otp = client.post(f"/api/agent/approvals/{rid}/otp").json()
        assert otp["channel"] == "simulated SMS" and len(otp["code"]) == 6
        d = client.post(f"/api/agent/approvals/{rid}/decide", json={"approve": True, "quiz_answers": None, "otp": otp["code"]}).json()
        assert d["status"] == "APPROVED"


def test_quiz_endpoint_hides_answers():
    with TestClient(app) as client:
        q = client.get("/api/agent/quiz").json()
        assert len(q["questions"]) == 3 and "correct_option_index" not in q["questions"][0]
