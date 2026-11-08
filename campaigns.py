# campaigns.py
# ============================================================
#  🎁 حملات المزايا (مش خصومات على التحاليل): زيارة منزلية مجانية لفواتير فوق حد معيّن.
#  القواعد في الإعدادات (config_store) وبتتعدّل من صفحة العروض — مش مكتوبة في الكود.
#
#  القاعدة الافتراضية (FREE HOME VISIT – OCTOBER & ZAYED):
#    صافي قيمة التحاليل بعد خصوماتها >= 6,000 ج · منطقة 6 October / Sheikh Zayed ·
#    لحد 30 نوفمبر 2026. الزيارة المجانية «ميزة» مش خصم نقدي من قيمة التحاليل.
#  منطق بحت (من غير streamlit/شبكة) -> test_crm.py
# ============================================================

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

FREE_HOME_VISIT_SEED = {
    "id": "FHV-OCT-ZAYED", "type": "free_home_visit",
    "name": "FREE HOME VISIT – OCTOBER & ZAYED",
    "min_net": 6000, "areas": ["6 October", "Sheikh Zayed"],
    "start": "2026-10-01", "end": "2026-11-30", "active": True,
    "text_ar": ("🎁 زيارة منزلية مجانية لحضرتك! للفواتير 6,000 ج أو أكثر "
                "في 6 أكتوبر والشيخ زايد — ساري حتى 30 نوفمبر 2026"),
    "text_en": ("🎁 FREE HOME VISIT — Enjoy a complimentary home visit from Orange Lab! "
                "For eligible laboratory invoices of 6,000 EGP or more. "
                "6 October & Sheikh Zayed · Valid until November 30, 2026"),
}

AREA_UNKNOWN = ("", None, "—", "Not specified")


def _d(s) -> date:
    return s if isinstance(s, date) else date.fromisoformat(str(s))


def campaign_state(c: dict, today: date) -> str:
    """inactive | scheduled | expired | running (التواريخ شاملة)."""
    if not c.get("active", True):
        return "inactive"
    if today < _d(c["start"]):
        return "scheduled"
    if today > _d(c["end"]):
        return "expired"
    return "running"


def evaluate(c: dict, *, net_total: int, area: Optional[str], today: date) -> dict:
    """
    eligible = الحملة شغّالة والمبلغ والمنطقة مناسبين.
    needs_area = المنطقة لسه ماتحدّدتش (مؤهل بشرط إنها من مناطق الحملة).
    missing = ناقص كام جنيه للحد الأدنى (لتلميح «ضيف تحليل»).
    """
    state = campaign_state(c, today)
    res = {"campaign": c, "eligible": False, "state": state, "needs_area": False,
           "missing": 0, "reason": ""}
    if state != "running":
        res["reason"] = state
        return res
    areas = c.get("areas") or []
    if areas and area not in AREA_UNKNOWN and area not in areas:
        res["reason"] = "area"
        return res
    if net_total < int(c.get("min_net", 0)):
        res["reason"] = "amount"
        res["missing"] = int(c["min_net"]) - int(net_total)
        return res
    res["eligible"] = True
    res["needs_area"] = bool(areas) and area in AREA_UNKNOWN
    return res


def evaluate_all(campaigns: List[dict], *, net_total: int, area: Optional[str],
                 today: date) -> List[dict]:
    return [evaluate(c, net_total=net_total, area=area, today=today) for c in campaigns
            if c.get("type") == "free_home_visit"]


def benefit_ids(results: List[dict]) -> List[str]:
    return [r["campaign"]["id"] for r in results if r["eligible"]]


def benefit_text(results: List[dict], lang: str = "ar") -> str:
    """نص الميزة اللي بيتضاف لرسالة العميل (للمؤهلين بس)."""
    key = "text_en" if lang == "en" else "text_ar"
    out = []
    for r in results:
        if r["eligible"] and r["campaign"].get(key):
            t = r["campaign"][key]
            if r["needs_area"] and lang != "en":
                t += " (بشرط إقامة العميل في مناطق الحملة)"
            out.append(t)
    return "\n".join(out)


def validate_campaign(c: dict) -> List[str]:
    errs = []
    if not (c.get("id") or "").strip():
        errs.append("كود الحملة مطلوب")
    if not (c.get("name") or "").strip():
        errs.append("اسم الحملة مطلوب")
    if int(c.get("min_net", 0) or 0) <= 0:
        errs.append("الحد الأدنى لازم يكون أكبر من صفر")
    try:
        if _d(c["end"]) < _d(c["start"]):
            errs.append("تاريخ النهاية قبل البداية")
    except Exception:
        errs.append("التواريخ مش صحيحة")
    return errs
