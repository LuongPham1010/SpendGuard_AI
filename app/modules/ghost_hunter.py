"""
Ghost Subscription Hunter Module
Shenzhen International FinTech Competition 2026 - Topic A: Autonomous Participant
Detects recurring subscription fee leakage ($27 <= Delta t <= 32 days),
calculates annual financial loss, and synthesizes 1-click unsubscribe cancellation templates.
"""

from datetime import datetime
from typing import List, Dict, Any
from app.models.schemas import Transaction, SubscriptionDetection
from app.core.audit_logger import SandboxAuditLogger


class GhostSubscriptionHunter:
    """Proactive subscription audit engine detecting silent recurring charges"""

    KNOWN_PORTALS = {
        "netflix": "https://www.netflix.com/youraccount",
        "spotify": "https://www.spotify.com/account/subscription",
        "apple": "https://support.apple.com/billing",
        "icloud": "https://support.apple.com/billing",
        "california fitness": "https://cali.vn/member-service/membership-cancellation",
        "coursera": "https://www.coursera.org/my-purchases",
        "adobe": "https://account.adobe.com/plans",
        "youtube": "https://www.youtube.com/paid_memberships",
        "chatgpt": "https://chat.openai.com/#settings",
    }

    ESSENTIAL_SUBCATEGORIES = {"housing", "rent", "utilities", "insurance", "loan", "healthcare", "groceries", "transport"}

    _cancelled_merchants: set = set()

    @classmethod
    def cancel_subscription(cls, merchant: str) -> bool:
        """Mark a subscription as cancelled"""
        norm = merchant.strip().lower()
        cls._cancelled_merchants.add(norm)
        for k in cls.KNOWN_PORTALS:
            if k in norm:
                cls._cancelled_merchants.add(k)
        return True

    @classmethod
    def is_cancelled(cls, merchant: str) -> bool:
        norm = merchant.strip().lower()
        if norm in cls._cancelled_merchants:
            return True
        return any(k in norm for k in cls._cancelled_merchants)

    @classmethod
    def detect_subscriptions(cls, transactions: List[Transaction]) -> List[SubscriptionDetection]:
        """
        Group transactions by normalized merchant / description.
        Filter for cyclic occurrences where consecutive transaction time delta satisfies:
        27 <= Delta t <= 34 days (or explicitly flagged subscription).
        """
        # Filter outflows
        outflows = [t for t in transactions if t.type == "outflow" and t.category != "Income"]

        # Group by merchant key or normalized description
        groups: Dict[str, List[Transaction]] = {}
        for t in outflows:
            desc_l = t.description.lower()
            merch_l = (t.merchant or "").lower()

            # Ignore internal transfers, loan repayments, and savings sweeps
            if any(x in desc_l for x in ["internal transfer", "tiet kiem", "quy khan cap", "chuyen khoan", "tra no"]):
                continue

            # Ignore hardware or one-off shopping
            if any(x in desc_l for x in ["iphone", "laptop", "macbook", "mua ao", "mua quan"]):
                continue

            # Identify canonical key
            key = None
            if "netflix" in desc_l or "netflix" in merch_l:
                key = "Netflix"
            elif "spotify" in desc_l or "spotify" in merch_l:
                key = "Spotify"
            elif "icloud" in desc_l or ("apple" in merch_l and "storage" in desc_l):
                key = "Apple iCloud"
            elif "california fitness" in desc_l or "cali" in merch_l or "hoi vien" in desc_l:
                key = "California Fitness"
            elif "coursera" in desc_l or "coursera" in merch_l:
                key = "Coursera"
            elif "adobe" in desc_l or "adobe" in merch_l:
                key = "Adobe Creative Cloud"
            elif "youtube" in desc_l or "youtube" in merch_l:
                key = "YouTube Premium"
            elif t.is_subscription or t.subcategory.lower() == "subscription":
                key = t.merchant or t.description
            elif t.category == "Needs" or (t.subcategory or "").lower() in cls.ESSENTIAL_SUBCATEGORIES:
                # Rent, utilities and insurance recur monthly but are bills, not cancellable subscriptions
                continue
            elif t.merchant and t.merchant.strip():
                # Any recognized merchant with repeated charges
                key = t.merchant.strip()

            if not key:
                continue

            if key not in groups:
                groups[key] = []
            groups[key].append(t)

        detections: List[SubscriptionDetection] = []

        for merchant_name, tx_list in groups.items():
            if len(tx_list) < 2:
                continue

            # Sort by date
            sorted_txs = sorted(tx_list, key=lambda x: x.date)
            
            # Check delta t between successive transactions
            deltas: List[int] = []
            for i in range(1, len(sorted_txs)):
                try:
                    d1 = datetime.strptime(sorted_txs[i - 1].date, "%Y-%m-%d")
                    d2 = datetime.strptime(sorted_txs[i].date, "%Y-%m-%d")
                    delta_days = (d2 - d1).days
                    deltas.append(delta_days)
                except Exception:
                    continue

            if not deltas:
                continue

            # A valid monthly recurring subscription satisfies:
            # All deltas are in a reasonable monthly window (25 to 35 days)
            # or explicit subscription flag with average delta 27 to 34 days
            all_in_window = all(25 <= d <= 35 for d in deltas)
            avg_delta = sum(deltas) / len(deltas)
            is_valid_cycle = all_in_window or (27 <= avg_delta <= 34 and len(deltas) >= 2)

            if is_valid_cycle:
                last_tx = sorted_txs[-1]
                avg_amt = sum(t.amount for t in sorted_txs) / len(sorted_txs)
                avg_freq = avg_delta
                annual_leakage = avg_amt * 12.0

                portal_url = "https://www.google.com/search?q=" + merchant_name.replace(" ", "+") + "+cancel+subscription"
                for m_key, url in cls.KNOWN_PORTALS.items():
                    if m_key in merchant_name.lower():
                        portal_url = url
                        break

                en_email, vi_email = cls.generate_cancellation_templates(
                    merchant=merchant_name,
                    amount=avg_amt,
                    last_date=last_tx.date,
                )

                sub_status = "cancelled" if cls.is_cancelled(merchant_name) else "active"

                sub = SubscriptionDetection(
                    merchant=merchant_name,
                    amount=avg_amt,
                    frequency_days=round(avg_freq, 1),
                    occurrences=len(sorted_txs),
                    last_charged=last_tx.date,
                    annual_leakage=annual_leakage,
                    unsubscribe_url=portal_url,
                    email_template_en=en_email,
                    email_template_vi=vi_email,
                    status=sub_status,
                )
                detections.append(sub)

        # Audit log
        SandboxAuditLogger.log_event(
            tier="Tier 1",
            module="GhostSubscriptionHunter",
            action="SCAN_RECURRING_FEES",
            status="SUCCESS",
            details={
                "detected_count": len(detections),
                "total_annual_leakage": sum(s.annual_leakage for s in detections),
                "active_leakage": sum(s.annual_leakage for s in detections if s.status == "active"),
                "cancelled_savings": sum(s.annual_leakage for s in detections if s.status == "cancelled"),
                "merchants": [s.merchant for s in detections],
            },
        )

        return detections

    @staticmethod
    def generate_cancellation_templates(merchant: str, amount: float, last_date: str) -> tuple[str, str]:
        """Generate English and Vietnamese 1-click legal cancellation notices"""
        en_template = (
            f"Subject: Immediate Cancellation Request & Revocation of Recurring Billing – Account Associated with {merchant}\n\n"
            f"Dear {merchant} Billing & Customer Support Team,\n\n"
            f"I am writing to formally request the immediate cancellation of my subscription service ({merchant}) "
            f"and the termination of all recurring authorization charges on my payment card/account effective immediately.\n\n"
            f"Details of Recent Charge:\n"
            f"- Service / Merchant: {merchant}\n"
            f"- Amount Charged: {amount:,.0f} VND / billing cycle\n"
            f"- Most Recent Transaction Date: {last_date}\n\n"
            f"Under consumer financial protection guidelines and merchant service rules, please confirm in writing that:\n"
            f"1. My membership and all associated recurring billing profiles are cancelled.\n"
            f"2. No further automated debits or pre-authorized charges will occur.\n\n"
            f"Thank you for your prompt confirmation.\n\n"
            f"Sincerely,\n"
            f"[Your Full Name]\n"
            f"[Registered Email / Phone Number]"
        )

        vi_template = (
            f"Tiêu đề: Yêu cầu Hủy gói Đăng ký Dịch vụ & Chấm dứt Trừ tiền Tự động – {merchant}\n\n"
            f"Kính gửi Bộ phận Chăm sóc Khách hàng & Thanh toán {merchant},\n\n"
            f"Tôi gửi email này để chính thức yêu cầu hủy gói dịch vụ định kỳ ({merchant}) "
            f"và chấm dứt toàn bộ lệnh ủy quyền trừ tiền tự động trên thẻ/tài khoản ngân hàng của tôi kể từ ngày hôm nay.\n\n"
            f"Thông tin giao dịch gần nhất:\n"
            f"- Dịch vụ / Đơn vị cung cấp: {merchant}\n"
            f"- Mức phí định kỳ: {amount:,.0f} VND / chu kỳ\n"
            f"- Ngày giao dịch gần nhất: {last_date}\n\n"
            f"Theo quy định về bảo vệ quyền lợi người tiêu dùng và quy chế thanh toán điện tử, kính đề nghị quý công ty:\n"
            f"1. Xác nhận đã hủy bỏ gói thành viên và vô hiệu hóa cơ chế thanh toán lặp lại (Auto-Renewal).\n"
            f"2. Cam kết không thực hiện bất kỳ giao dịch trừ tiền phát sinh nào sau ngày nhận thông báo này.\n\n"
            f"Rất mong nhận được phản hồi xác nhận sớm từ quý công ty.\n\n"
            f"Trân trọng,\n"
            f"[Họ và tên của bạn]\n"
            f"[Email / Số điện thoại đăng ký]"
        )

        return en_template, vi_template
