"""
Root entry point to launch SpendGuard AI server
Shenzhen International FinTech Competition 2026 - WeBank & Tsinghua PBCSF
Topic A: Personal Finance Assistant
"""

import os
import uvicorn

from app.config import HOST, PORT

if __name__ == "__main__":
    print("=" * 70)
    print("  SPENDGUARD AI – AUTONOMOUS FINANCIAL AUDITOR & COGNITIVE FRAUD DEFENSE")
    print("  Shenzhen International FinTech Competition 2026 (WeBank & Tsinghua PBCSF)")
    print("  Topic A: Personal Finance Assistant | Model: Gemini Flash Engine")
    print("=" * 70)
    print(f"  Server launching at: http://{HOST}:{PORT}")
    print(f"  API Docs available at: http://{HOST}:{PORT}/docs")
    print("=" * 70)
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=os.getenv("RELOAD", "1") == "1")
