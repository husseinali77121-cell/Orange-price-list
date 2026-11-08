# recovery.py
# ============================================================
#  💸 استرجاع العميل اللي ماحضرش: بعد موافقة الإدارة على خصم إضافي، بنبني عرض جديد
#  مرتبط بالقديم (parent) فيه نفس التحاليل بأسعارها الحالية + الخصم القديم + الخصم
#  الموافق عليه. اللينك مشفّر وموقّع (quote_secret) فمحدّش يقدر يعدّل الخصم، ومعاه علامة
#  «معتمد» عشان الفاتورة ما تطلبش كود موافقة تاني. منطق بحت -> test_crm_pages.py
# ============================================================

from __future__ import annotations

import random
from datetime import datetime
from typing import List, Optional, Tuple

from price_utils import encode_quote


def new_quote_id(now: Optional[datetime] = None, rng=random) -> str:
    now = now or datetime.now()
    return f"OR-{now:%y%m%d}-{rng.randint(0, 9999):04d}"


def build_recovery_payload(rec: dict, extra_amount: int, idx, *, now: Optional[datetime] = None,
                           new_id: Optional[str] = None, signed: bool = True) -> Tuple[dict, List[str]]:
    """
    (payload, ناقص) — ناقص = أسماء تحاليل العرض القديم اللي مش موجودة في القائمة دلوقتي.
    الخصم الجديد = خصم العرض القديم + الخصم الإضافي الموافق عليه (مبلغ ثابت).
    """
    now = now or datetime.now()
    items, missing = [], []
    for n in rec.get("items", []):
        hits = idx.get(n)
        if not hits:
            missing.append(n)
            continue
        h = hits[0]
        items.append({"n": h.name, "p": h.price, "d": h.result_days, "c": h.collection_notes or "",
                      "cat": h.category})
    contact = rec.get("contact") or {}
    payload = {
        "id": new_id or new_quote_id(now), "ts": now.isoformat(timespec="seconds"), "items": items,
        "name": contact.get("name", ""), "phone": contact.get("phone", ""), "doctor": "",
        "date_iso": now.date().isoformat(), "dtype": "Fixed Amount",
        "dval": float(int(rec.get("discount", 0)) + int(extra_amount)),
        "cid": rec.get("campaign_id", ""), "area": rec.get("area", ""),
        "vt": "home" if rec.get("visit_type") == "home" else "lab",
        "par": rec["quote_id"], "appr": bool(signed),
    }
    return payload, missing


def recovery_link(rec: dict, extra_amount: int, idx, secret: str, *,
                  now: Optional[datetime] = None) -> Tuple[str, List[str]]:
    """('/?q=<token>', ناقص). «معتمد» (appr) بيتحط بس لو فيه quote_secret (اللينك موقّع)."""
    payload, missing = build_recovery_payload(rec, extra_amount, idx, now=now, signed=bool(secret))
    return "/?q=" + encode_quote(payload, secret), missing
