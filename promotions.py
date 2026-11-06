# promotions.py
# ============================================================
#  🎁 Promotion Engine — عروض بتواريخ وفروع من غير ما نلمس أسعار القائمة
#  منطق بحت (من غير streamlit/شبكة) -> test_promotions.py
#
#  العرض = اسم + هدف (باقة أو تحليل) + سعر أصلي (لقطة وقت الإنشاء) + سعر عرض
#          + تاريخ بداية/نهاية (شاملين) + فروع (فاضي = كل الفروع) + حالة.
#  السعر الأساسي في labs_price_list.py / bundles.py بيفضل زي ما هو، والعرض
#  بيخلص لوحده بعد تاريخ النهاية. التخزين: promotions/promotions.json على GitHub.
#
#  كمان هنا سياسة الخصم: حد أقصى بيتطلب موافقة (PIN المسؤول).
# ============================================================

from __future__ import annotations

import hmac
import random
import string
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

from price_utils import norm

PROMO_PATH = "promotions/promotions.json"
PROMO_STATUSES = ("active", "paused", "cancelled")
STATE_LABELS = {"active": "🟢 شغّال", "scheduled": "🕒 لسه ما بدأش", "expired": "⚪ انتهى",
                "paused": "⏸️ موقوف", "cancelled": "🚫 ملغي"}


def _d(s) -> date:
    return s if isinstance(s, date) and not isinstance(s, datetime) else date.fromisoformat(str(s))


def new_promotion(*, name: str, target: str, original_price: int, promo_price: int,
                  start, end, branches: Iterable[str] = (), note: str = "",
                  floor_price: int = 0, now: Optional[datetime] = None,
                  rng=random) -> dict:
    """بيبني عرض جديد بعد التحقق — ValueError برسالة عربي لو فيه مشكلة."""
    name, target = (name or "").strip(), (target or "").strip()
    if not name:
        raise ValueError("اكتب اسم العرض")
    if not target:
        raise ValueError("اختار الباقة أو التحليل")
    original_price, promo_price = int(original_price), int(promo_price)
    if original_price <= 0:
        raise ValueError("السعر الأصلي مش متحدد — الهدف من غير سعر في القائمة")
    if promo_price <= 0:
        raise ValueError("سعر العرض لازم يكون أكبر من صفر")
    if promo_price >= original_price:
        raise ValueError(f"سعر العرض ({promo_price}) لازم يكون أقل من السعر الأصلي ({original_price})")
    if floor_price and promo_price < int(floor_price):
        raise ValueError(f"سعر العرض أقل من الحد الأدنى المسموح ({int(floor_price)})")
    s, e = _d(start), _d(end)
    if e < s:
        raise ValueError("تاريخ النهاية قبل البداية")
    now = now or datetime.now()
    tail = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return {
        "id": f"PR-{now:%y%m%d}-{tail}", "name": name, "target": target,
        "original_price": original_price, "promo_price": promo_price,
        "start": s.isoformat(), "end": e.isoformat(),
        "branches": sorted(set(branches or [])), "status": "active",
        "note": (note or "").strip(), "created": now.isoformat(timespec="seconds"),
    }


def promo_state(p: dict, today: date) -> str:
    if p.get("status") in ("paused", "cancelled"):
        return p["status"]
    s, e = _d(p["start"]), _d(p["end"])
    if today < s:
        return "scheduled"
    if today > e:
        return "expired"
    return "active"


def applies_to_branch(p: dict, branch: str) -> bool:
    return not p.get("branches") or branch in p["branches"]


def active_promotions(promos: List[dict], branch: str, today: date) -> List[dict]:
    return [p for p in promos if promo_state(p, today) == "active"
            and applies_to_branch(p, branch)]


def best_promo_for(promos: List[dict], name: str, branch: str, today: date) -> Optional[dict]:
    """أرخص عرض شغّال لهدف معيّن في فرع معيّن."""
    hits = [p for p in active_promotions(promos, branch, today) if norm(p["target"]) == norm(name)]
    return min(hits, key=lambda p: p["promo_price"]) if hits else None


def promo_discount_pct(p: dict) -> float:
    return round(100.0 * (p["original_price"] - p["promo_price"]) / p["original_price"], 1)


def overlaps(promos: List[dict], new: dict) -> List[dict]:
    """عروض شغّالة/جاية على نفس الهدف بتتقاطع معاها في التاريخ والفرع."""
    out = []
    for p in promos:
        if p.get("status") == "cancelled" or p.get("id") == new.get("id"):
            continue
        if norm(p["target"]) != norm(new["target"]):
            continue
        if not (_d(p["start"]) <= _d(new["end"]) and _d(new["start"]) <= _d(p["end"])):
            continue
        pb, nb = set(p.get("branches") or []), set(new.get("branches") or [])
        if pb and nb and not (pb & nb):
            continue
        out.append(p)
    return out


def drift_warnings(p: dict, idx) -> List[str]:
    """تحذيرات لو قائمة الأسعار اتغيّرت بعد إنشاء العرض."""
    hits = idx.get(p["target"])
    if not hits:
        return [f"«{p['target']}» مش موجود في القائمة دلوقتي"]
    cur = hits[0].price
    warns = []
    if cur != p["original_price"]:
        warns.append(f"سعر القائمة اتغيّر من {p['original_price']} إلى {cur} — راجع العرض")
    if p["promo_price"] >= cur:
        warns.append(f"سعر العرض ({p['promo_price']}) بقى مش أقل من سعر القائمة ({cur})")
    return warns


def upsert(promos: List[dict], p: dict) -> List[dict]:
    out = [x for x in promos if x.get("id") != p["id"]]
    out.append(p)
    return out


def set_status(promos: List[dict], promo_id: str, status: str) -> List[dict]:
    if status not in PROMO_STATUSES:
        raise ValueError(f"unknown status: {status}")
    return [{**p, "status": status} if p.get("id") == promo_id else p for p in promos]


def sorted_for_display(promos: List[dict], today: date) -> List[dict]:
    order = {"active": 0, "scheduled": 1, "paused": 2, "expired": 3, "cancelled": 4}
    return sorted(promos, key=lambda p: (order[promo_state(p, today)], p["start"]))


# ------------------------------------------------------------
# سياسة الخصم: خصم أكبر من الحد = لازم موافقة المسؤول (PIN)
# ------------------------------------------------------------

def discount_pct_of(totals: Dict) -> float:
    sub = totals.get("subtotal", 0)
    return 100.0 * totals.get("discount", 0) / sub if sub else 0.0


def needs_approval(totals: Dict, limit_pct: float) -> bool:
    """limit_pct <= 0 = السياسة مقفولة (مفيش حد)."""
    return limit_pct > 0 and discount_pct_of(totals) > limit_pct + 1e-9


def pin_ok(entered: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(str(entered or "").encode("utf-8"),
                                                 str(expected).encode("utf-8"))
