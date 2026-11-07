# offers_catalog.py
# ============================================================
#  📋 منطق كتالوج العروض: القائمة الترحيبية، رسالة كل عرض، مقارنة السعر بقائمة
#  الأسعار، وحقول التصميم (Marketing Studio). بيانات في offers_data.py.
#  من غير streamlit/شبكة -> test_offers_catalog.py
# ============================================================

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from brand import (BRANCH_INFO, LAB_NAME_AR, OFFERS_PHONE, WORKING_HOURS_AR)
from offers_data import MENU, OFFERS

KEYCAPS = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣",
           9: "9️⃣", 10: "🔟"}
STATUS_LABELS = {"current": "🟢 شغّال", "legacy": "⚪ نسخة قديمة", "pending": "⚠️ من غير تفاصيل",
                 "service": "🛎️ خدمة", "bundles": "📦 من باقات التطبيق"}
SENDABLE = ("current", "service", "bundles")
CUR = "ج"
PRICE_TOLERANCE_PCT = 3.0


def get(offer_id: str) -> Optional[dict]:
    return next((o for o in OFFERS if o["id"] == offer_id), None)


def menu_title(no: int) -> str:
    return dict(MENU)[no]


def selectable() -> List[dict]:
    """اللي بيظهر في اختيار الموظف: كل شيء ما عدا النسخ القديمة، بترتيب الرقم."""
    rows = [o for o in OFFERS if o["status"] != "legacy"]
    return sorted(rows, key=lambda o: (o["no"] if o["no"] is not None else 999, o["id"]))


def option_label(o: dict) -> str:
    n = o["no"] if o["no"] is not None else "★"
    flag = {"pending": " ⚠️ بدون تفاصيل", "service": " 🛎️"}.get(o["status"], "")
    return f"{n} — {o['title']}{flag}"


def is_sendable(o: dict) -> bool:
    return o["status"] in SENDABLE


def saving(o: dict) -> int:
    return (o["before"] - o["after"]) if (o.get("before") and o.get("after")) else 0


def discount_pct(o: dict) -> float:
    return round(100.0 * saving(o) / o["before"], 1) if saving(o) > 0 else 0.0


def coverage() -> Dict[int, List[str]]:
    """رقم القائمة -> حالات العروض المرتبطة بيه (للتأكد إن كل الأرقام ليها مصير)."""
    cov: Dict[int, List[str]] = {n: [] for n, _ in MENU}
    for o in OFFERS:
        if o["no"] in cov:
            cov[o["no"]].append(o["status"])
    return cov


# ------------------------------------------------------------
# مقارنة بقائمة الأسعار
# ------------------------------------------------------------

def list_sum(o: dict, idx) -> Tuple[int, List[str]]:
    """(مجموع سعر مكوّنات العرض في القائمة الحالية، الأسماء اللي ملقيتهاش)."""
    total, missing = 0, []
    for name in o.get("db", []):
        hits = idx.get(name)
        if hits:
            total += hits[0].price
        else:
            missing.append(name)
    return total, missing


def price_check(o: dict, idx) -> dict:
    """
    مقارنة «قبل الخصم» (أو سعر العرض لو مفيش قبل) بمجموع القائمة الحالية.
      ok           ±3% — الأرقام متسقة مع القائمة
      list_higher  القائمة الحالية أغلى من «قبل الخصم» في الرسالة — الرسالة غالباً قديمة
      list_lower   القائمة أرخص من «قبل الخصم»
      no_before    مفيش «قبل الخصم»: بنحسب التوفير الضمني من القائمة
      unknown      مفيش مكوّنات مسمّاة نقارن بيها
    """
    if not o.get("db"):
        return {"status": "unknown", "list_sum": 0, "delta": 0, "pct": 0.0, "missing": []}
    total, missing = list_sum(o, idx)
    if missing:
        return {"status": "unknown", "list_sum": total, "delta": 0, "pct": 0.0, "missing": missing}
    ref = o.get("before")
    if not ref:
        return {"status": "no_before", "list_sum": total, "delta": 0, "pct": 0.0, "missing": [],
                "implied_saving": total - (o.get("after") or 0)}
    delta = total - ref
    pct = round(100.0 * delta / ref, 1)
    status = "ok" if abs(pct) <= PRICE_TOLERANCE_PCT else ("list_higher" if pct > 0 else "list_lower")
    return {"status": status, "list_sum": total, "delta": delta, "pct": pct, "missing": []}


def bundle_conflicts(idx) -> List[dict]:
    """عروض الكتالوج اللي نفس تحاليل باقة في التطبيق بس بسعر مختلف."""
    out = []
    for o in OFFERS:
        if o["status"] != "current" or not o.get("db") or not o.get("after"):
            continue
        for b in idx.bundles:
            if set(o["db"]) == set(b.components) and o["after"] != b.price:
                out.append({"offer_id": o["id"], "offer_price": o["after"], "bundle": b.name,
                            "bundle_price": b.price})
    return out


# ------------------------------------------------------------
# الرسائل
# ------------------------------------------------------------

def location_block(branch: str = "") -> str:
    infos = [BRANCH_INFO[branch]] if branch in BRANCH_INFO else list(BRANCH_INFO.values())
    return "\n\n".join(f"📍 {i['name_ar']}:\n{i['address']}\n🗺️ {i['maps']}" for i in infos)


def menu_message(*, with_branches: bool = True, with_hours: bool = True,
                 phone: str = OFFERS_PHONE) -> str:
    """القائمة الترحيبية بنفس نصك: رقم لكل خدمة/عرض (الرقم ده اللي العميل بيكتبه)."""
    lines = [f"مرحبًا بكم في {LAB_NAME_AR.replace('معمل أورانج للتحاليل الطبية', 'معمل أورانج لاب للتحاليل الطبية')} 🌟",
             "للاستفسار عن أي عرض، يُرجى كتابة رقم العرض، وسنرد عليك بكافة التفاصيل:"]
    for no, title in MENU:
        lines.append(f"{KEYCAPS[no]} {title}" if no in KEYCAPS else f"🔵 {no} - {title}")
        if no == 27 and phone:
            lines.append(f"📞 ت: {phone}")
    text = "\n".join(lines)
    if with_hours:
        text += "\n\n" + WORKING_HOURS_AR
    if with_branches:
        text += "\n\n" + "\n\n".join(
            f"{i['name_ar']}:\n{i['maps']}\n\n{i['address']}" for i in BRANCH_INFO.values())
    return text


def _items_block(tests: List[str]) -> str:
    if len(tests) <= 10:
        return "\n".join(f"• {t}" for t in tests)
    return "• " + "، ".join(tests)


def offer_message(o: dict, idx=None, *, branch: str = "", phone: str = OFFERS_PHONE,
                  with_hours: bool = False, with_location: bool = False) -> str:
    """رسالة العرض اللي الموظف يبعتها لما العميل يكتب الرقم. بترجّع "" للعرض اللي من غير تفاصيل."""
    if not is_sendable(o):
        return ""
    parts: List[str] = []
    cta = f"📞 للحجز والاستفسار: {phone}" if phone else ""

    if o["override"]:
        parts.append(o["override"])
        if o["status"] != "service" and cta:
            parts.append(cta)
    elif o["status"] == "bundles":
        parts.append(f"🍊 {o['title']}")
        lines = []
        for name in o["bundle_refs"]:
            hits = idx.get(name) if idx else None
            if not hits:
                continue
            rec = hits[0]
            retail = sum((idx.get(c) or [None])[0].price for c in rec.components if idx.get(c))
            sv = retail - rec.price
            lines.append(f"• {name}: {rec.price:,} {CUR}" + (f" (وفّر {sv:,} {CUR})" if sv > 0 else ""))
        parts.append("\n".join(lines) if lines else "اسأل عن الأسعار الحالية")
        if cta:
            parts.append(cta)
    else:
        parts.append(f"🍊 {o['title']}")
        if o["desc"]:
            parts.append(o["desc"])
        if o["tests"]:
            parts.append("التحاليل:\n" + _items_block(o["tests"]))
        extras = []
        if o["fasting"]:
            extras.append(f"⏰ يتطلب صيام {o['fasting']} ساعات")
        extras.extend(f"📝 {n}" for n in o["notes"])
        if extras:
            parts.append("\n".join(extras))
        if o["after"]:
            if o["before"]:
                price = (f"💰 قبل الخصم: {o['before']:,} {CUR}\n"
                         f"✅ بعد الخصم: {o['after']:,} {CUR}\n"
                         f"🎁 وفّر {saving(o):,} {CUR}")
            else:
                price = f"💰 السعر: {'ابتداءً من ' if o['from_price'] else ''}{o['after']:,} {CUR}"
            parts.append(price)
        if o["see_also"]:
            names = [f"{get(i)['title']} (رقم {get(i)['no']})" for i in o["see_also"] if get(i)]
            if names:
                parts.append("هناك عروض أخرى: " + " و".join(names))
        if cta:
            parts.append(cta)
    if with_hours:
        parts.append(WORKING_HOURS_AR)
    if with_location:
        parts.append(location_block(branch))
    return "\n\n".join(p for p in parts if p)


# ------------------------------------------------------------
# حقول تصميم Marketing Studio (قالب «عرض»)
# ------------------------------------------------------------

def studio_fields(o: dict) -> dict:
    """بيرجّع حقول القالب (من غير ms_) لعرض فيه سعر. ValueError لو مفيش سعر."""
    if not o.get("after"):
        raise ValueError("العرض ده مفيهوش سعر — مينفعش يتحوّل لتصميم")
    tests = list(o["tests"])
    items = tests[:7]
    if len(tests) > 7:
        items[-1] = f"و {len(tests) - 6} تحاليل أخرى"
    if o["pct"]:
        sub = f"خصم {o['pct']}"
    elif o["fasting"]:
        sub = f"يتطلب صيام {o['fasting']} ساعات"
    else:
        sub = "سعر خاص لفترة محدودة"
    return {
        "template": "offer", "title_small": "عرض", "title_big": o["short"] or o["title"],
        "subtitle": sub, "badge_mode": "price",
        "badge_top": "ابتداءً من" if o["from_price"] else "بسعر",
        "badge_value": str(o["after"]), "old_price": str(o["before"] or ""),
        "badge_sub": "", "badge_pill": o["pill"] or o["short"],
        "list_title": "العرض يشمل", "items": "\n".join(items),
        "cta": "احجز تحاليلك الآن", "valid_until": "", "show_trust": True,
    }
