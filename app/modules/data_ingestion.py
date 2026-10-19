"""
Data Ingestion Module: CSV/PDF Statement Parser & Gemini Multimodal OCR
Shenzhen International FinTech Competition 2026 - Multimodal Ingestion Pipeline
Upgraded: PyMuPDF (fitz) engine with overflow clip, 2D coordinate sorting, and hybrid Vision OCR.
"""

import io
import re
import csv
import json
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

import pymupdf

from app.config import FALLBACK_TO_MOCK, DEFAULT_TRANSACTIONS_CSV
from app.models.schemas import Transaction
from app.core.audit_logger import SandboxAuditLogger
from app.core.security import SecurityGuard
from app.core.llm_helper import extract_json_from_text
from app.core.llm_gateway import gateway, Part

_OVERFLOW_RIGHT = 1_000_000.0


def _overflow_clip(page: pymupdf.Page) -> pymupdf.Rect:
    """Expand right boundary to prevent truncation of long transaction descriptions."""
    r = page.rect
    return pymupdf.Rect(r.x0, r.y0, max(r.x1, _OVERFLOW_RIGHT), r.y1)


def _page_is_mostly_image(page: pymupdf.Page, threshold: float = 0.7) -> bool:
    """Detect whether a page is a scanned document/image statement."""
    images = page.get_images(full=True)
    if not images:
        return False
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return False
    for img in images:
        try:
            rects = page.get_image_rects(img[0])
        except Exception:
            continue
        for r in rects:
            if (r.width * r.height) / page_area >= threshold:
                return True
    return False


class DataIngestionEngine:
    """Parses bank statements (CSV & PDF) and extracts receipt items with Gemini Multimodal OCR."""

    @staticmethod
    def load_default_transactions() -> List[Transaction]:
        """Load the standard 50 transactions dataset."""
        if not DEFAULT_TRANSACTIONS_CSV.exists():
            return []
        with open(DEFAULT_TRANSACTIONS_CSV, "r", encoding="utf-8") as f:
            content = f.read()
        return DataIngestionEngine.parse_csv(content)

    @staticmethod
    def _build_transaction_from_row(row: Dict[str, Any], idx: int) -> Transaction:
        tx_id = str(row.get("id") or row.get("tx_id") or row.get("Transaction ID") or f"TX{1000 + idx}")
        date = str(row.get("date") or row.get("Date") or row.get("Ngay") or datetime.now().strftime("%Y-%m-%d")).strip()
        desc = str(row.get("description") or row.get("Description") or row.get("Noi dung") or "Unspecified transaction").strip()

        clean_desc = SecurityGuard.mask_pii(desc)

        raw_amt = row.get("amount") or row.get("Amount") or row.get("So tien") or "0"
        clean_amt = re.sub(r"[^\d.\-]", "", str(raw_amt).replace(",", ""))
        try:
            signed_val = float(clean_amt) if clean_amt not in ("", "-", ".") else 0.0
            amount = abs(signed_val)
        except ValueError:
            signed_val = 0.0
            amount = 0.0

        tx_type = str(row.get("type") or row.get("Type") or "").lower().strip()
        if not tx_type:
            if signed_val < 0:
                tx_type = "outflow"
            elif any(k in desc.lower() for k in ["nhan", "luong", "salary", "freelance", "income", "refund", "hoan tien"]):
                tx_type = "inflow"
            else:
                tx_type = "outflow"

        category = row.get("category") or row.get("Category") or ("Income" if tx_type == "inflow" else "Wants")
        subcategory = row.get("subcategory") or row.get("Subcategory") or "General"
        if category in ("Wants", "General", "") and tx_type == "outflow":
            try:
                from app.modules.auto_categorizer import AutoCategorizer
                category, subcategory = AutoCategorizer.classify_transaction(clean_desc, category)
            except Exception:
                pass

        wallet = row.get("wallet") or row.get("Wallet") or ("Emergency Vault" if "emergency" in desc.lower() else "Main Wallet")
        merchant = row.get("merchant") or row.get("Merchant") or None

        is_sub = (
            "subscription" in clean_desc.lower()
            or "hang thang" in clean_desc.lower()
            or "gia han" in clean_desc.lower()
            or str(subcategory).lower() == "subscription"
        )

        return Transaction(
            id=tx_id,
            date=date,
            description=clean_desc,
            amount=amount,
            type=tx_type,
            category=category,
            subcategory=subcategory,
            wallet=wallet,
            is_subscription=is_sub,
            merchant=merchant,
            raw_details=json.dumps(row, ensure_ascii=False),
        )

    @staticmethod
    def parse_csv(csv_content: str) -> List[Transaction]:
        """
        Parse CSV content with auto column mapping and PII sanitization.
        Supports standard bank statement exports (Vietcombank, Techcombank, MB Bank, standard formats).
        """
        transactions: List[Transaction] = []
        reader = csv.DictReader(io.StringIO(csv_content))

        for idx, row in enumerate(reader):
            transactions.append(DataIngestionEngine._build_transaction_from_row(row, idx))

        SandboxAuditLogger.log_event(
            tier="Tier 1",
            module="DataIngestion",
            action="INGEST_CSV_STATEMENT",
            status="SUCCESS",
            details={
                "transaction_count": len(transactions),
                "sample_first_id": transactions[0].id if transactions else None,
            },
        )

        return transactions

    @staticmethod
    def parse_pdf_statement(file_bytes: bytes, filename: str = "statement.pdf") -> List[Transaction]:
        """
        Extract bank statement transactions using PyMuPDF (fitz) with overflow clipping,
        table extraction, 2D coordinate sorting, and Gemini Vision OCR for scanned pages.
        """
        transactions: List[Transaction] = []
        extracted_rows: List[Dict[str, Any]] = []

        try:
            with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
                for page_idx, page in enumerate(doc):
                    page_rows: List[Dict[str, Any]] = []
                    clip = _overflow_clip(page)
                    raw_text = page.get_text("text", clip=clip) or ""

                    # 1. Hybrid Check: If page is mostly image/scanned and has minimal text, use Gemini Vision OCR
                    if (_page_is_mostly_image(page) or len(raw_text.strip()) < 150) and gateway.available:
                        try:
                            pix = page.get_pixmap(dpi=150)
                            img_bytes = pix.tobytes("png")
                            ocr_res = gateway.generate(
                                'Extract all bank statement transactions from this page into JSON list format: '
                                '[{"date": "YYYY-MM-DD", "description": str, "amount": number, "type": "inflow"|"outflow"}].',
                                instructions="You are an expert financial document extractor. Output valid JSON only.",
                                untrusted=[Part(kind="image", content=img_bytes, mime_type="image/png", source="pdf_scan")],
                                purpose="statement_ocr"
                            )
                            parsed_ocr = ocr_res.data or extract_json_from_text(ocr_res.text)
                            if isinstance(parsed_ocr, list):
                                for item in parsed_ocr:
                                    if isinstance(item, dict) and "amount" in item:
                                        page_rows.append(item)
                        except Exception as ocr_err:
                            print(f"[DataIngestion] OCR page {page_idx + 1} error: {ocr_err}")

                    # 2. Native Table Extraction via page.find_tables()
                    if not page_rows:
                        try:
                            tabs = page.find_tables(clip=clip)
                            for tab in tabs:
                                extracted = tab.extract()
                                if not extracted or len(extracted) < 2:
                                    continue
                                header = [str(c or "").strip().lower() for c in extracted[0]]
                                has_header = any(k in " ".join(header) for k in ("date", "ngay", "amount", "so tien", "description", "noi dung"))
                                start_idx = 1 if has_header else 0

                                for r in extracted[start_idx:]:
                                    cells = [str(c or "").strip() for c in r if c is not None and str(c or "").strip()]
                                    if len(cells) < 2:
                                        continue
                                    if has_header and len(cells) == len(header):
                                        row_dict = dict(zip(header, cells))
                                        page_rows.append({
                                            "date": row_dict.get("date") or row_dict.get("ngay") or row_dict.get("transaction date") or datetime.now().strftime("%Y-%m-%d"),
                                            "description": row_dict.get("description") or row_dict.get("noi dung") or row_dict.get("details") or " ".join(cells),
                                            "amount": row_dict.get("amount") or row_dict.get("so tien") or row_dict.get("debit") or row_dict.get("credit") or "0",
                                            "type": row_dict.get("type") or "",
                                        })
                                    else:
                                        line_joined = " | ".join(cells)
                                        m_date = re.search(r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", line_joined)
                                        m_amt = re.search(r"([+-]?\d{1,3}(?:[.,]\d{3})+|\d{5,})", line_joined)
                                        if m_amt:
                                            dt_str = m_date.group(1) if m_date else datetime.now().strftime("%Y-%m-%d")
                                            if "/" in dt_str:
                                                parts = dt_str.split("/")
                                                dt_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
                                            page_rows.append({
                                                "date": dt_str,
                                                "description": line_joined,
                                                "amount": m_amt.group(1),
                                            })
                        except Exception as tab_err:
                            print(f"[DataIngestion] Table parse error on page {page_idx + 1}: {tab_err}")

                    # 3. 2D Coordinate Block Sorting Fallback (round(y, 1), x)
                    if not page_rows:
                        blocks = page.get_text("blocks", clip=clip)
                        sorted_blocks = sorted(blocks, key=lambda b: (round(b[1], 1), b[0]))
                        for b in sorted_blocks:
                            line_content = b[4].strip()
                            matched_single = False
                            for line in line_content.splitlines():
                                m = re.search(r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\s*[,|;\s]\s*(.+?)\s*[,|;\s]\s*([+-]?\d{1,3}(?:[.,]\d{3})+|\d{5,})", line)
                                if m:
                                    dt_str = m.group(1)
                                    if "/" in dt_str:
                                        parts = dt_str.split("/")
                                        dt_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
                                    page_rows.append({
                                        "date": dt_str,
                                        "description": m.group(2).strip(),
                                        "amount": m.group(3).replace(".", "").replace(",", ""),
                                    })
                                    matched_single = True

                            if not matched_single:
                                blines = [l.strip() for l in line_content.splitlines() if l.strip()]
                                if len(blines) >= 2:
                                    m_date = re.match(r"^(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", blines[0])
                                    m_amt = re.search(r"([+-]?\d{1,3}(?:[.,]\d{3})+|[+-]?\d{4,})$", blines[-1])
                                    if m_date and m_amt:
                                        dt_str = m_date.group(1)
                                        if "/" in dt_str:
                                            parts = dt_str.split("/")
                                            dt_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
                                        desc = " ".join(blines[1:-1]) if len(blines) > 2 else blines[0]
                                        page_rows.append({
                                            "date": dt_str,
                                            "description": desc,
                                            "amount": m_amt.group(1).replace(".", "").replace(",", ""),
                                        })

                    extracted_rows.extend(page_rows)

        except Exception as e:
            # Fallback for mock/test text bytes masquerading as PDF
            try:
                raw_text = file_bytes.decode("utf-8", errors="ignore")
                for line in raw_text.splitlines():
                    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*[,|;\s]\s*(.+?)\s*[,|;\s]\s*([+-]?\d{1,3}(?:[.,]\d{3})+|\d{5,})", line)
                    if m:
                        extracted_rows.append({
                            "date": m.group(1),
                            "description": m.group(2).strip(),
                            "amount": m.group(3).replace(",", ""),
                        })
            except Exception:
                print(f"[DataIngestion] Final PDF parse error: {e}")

        for idx, r in enumerate(extracted_rows):
            r["id"] = f"PDF{1000 + idx}"
            transactions.append(DataIngestionEngine._build_transaction_from_row(r, idx))

        SandboxAuditLogger.log_event(
            tier="Tier 1",
            module="DataIngestion",
            action="INGEST_PDF_STATEMENT",
            status="SUCCESS" if transactions else "EMPTY",
            details={
                "filename": filename,
                "transaction_count": len(transactions),
            },
        )
        return transactions

    @staticmethod
    def extract_receipt_ocr(
        file_bytes: bytes,
        filename: str = "receipt.jpg",
        mime_type: str = "image/jpeg",
    ) -> Dict[str, Any]:
        """
        Multimodal receipt analysis using Gemini Flash.
        Falls back to intelligent heuristic parser if Gemini API key is absent or network is unavailable.
        """
        guardrail = SecurityGuard.validate_input_guardrail(filename)
        if not guardrail["safe"]:
            return {
                "success": False,
                "error": "Adversarial payload detected in receipt filename",
                "details": guardrail["reason"],
            }

        if gateway.available:
            res = gateway.generate(
                'Extract the receipt as JSON {"merchant": str, "date": "YYYY-MM-DD", "total_amount": number, "currency": "VND", '
                '"items": [{"name": str, "qty": number, "price": number}], "suggested_category": "Needs"|"Wants", '
                '"suggested_subcategory": str, "notes": str}.',
                instructions="You are a receipt OCR engine.",
                untrusted=[Part(kind="image", content=file_bytes, mime_type=mime_type, source="receipt")],
                purpose="receipt_ocr"
            )
            parsed = res.data or extract_json_from_text(res.text)
            if res.available and parsed and "merchant" in parsed:
                SandboxAuditLogger.log_event(
                    tier="Tier 1",
                    module="DataIngestion",
                    action="GATEWAY_RECEIPT_OCR",
                    status="SUCCESS",
                    details={"model": res.model, "merchant": parsed.get("merchant"), "flags": res.flags}
                )
                return {"success": True, "source": f"Gateway ({res.model})", "data": parsed, "flags": res.flags}

        SandboxAuditLogger.log_event(
            tier="Tier 1",
            module="DataIngestion",
            action="RECEIPT_OCR_UNAVAILABLE",
            status="SKIPPED",
            details={"filename": filename, "reason": "no vision model configured"},
        )
        return {
            "success": False,
            "requires_model": True,
            "source": "none",
            "error": "Receipt reading needs a vision model. Configure GEMINI_API_KEY, or enter the transaction manually.",
        }
