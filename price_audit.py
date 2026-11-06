# price_audit.py
# ============================================================
#  🧹 فحص جودة قاعدة الأسعار — بيرجّع قايمة مشاكل (مش بيعدّل حاجة).
#  بنود من غير سعر · من غير مدة نتيجة · من غير تعليمات عينة ·
#  أسماء مكررة بأسعار مختلفة · باقات مفيهاش توفير أو أغلى من مكوّناتها.
#  القرار التجاري (السعر الصح) بتاعك — الفحص بيدلّك على الأماكن بس.
# ============================================================

from __future__ import annotations

from typing import Dict, List

from price_utils import PriceIndex, bundle_saving, norm

SEVERITY = {"high": "🔴 مهم", "medium": "🟠 راجع", "low": "🟡 تحسين"}


def audit_prices(idx: PriceIndex) -> List[Dict]:
    issues: List[Dict] = []

    def add(kind, sev, rec, detail):
        issues.append({"kind": kind, "severity": sev, "category": rec.category,
                       "name": rec.name, "price": rec.price, "detail": detail})

    for r in idx.records:
        if r.is_bundle:
            continue
        if r.price == 0:
            add("zero_price", "high", r, "السعر صفر — هيتحسب مجاني أو يتقفل الإرسال")
        if not r.result_days:
            add("no_result_days", "medium", r, "مفيش مدة نتيجة")
        if not (r.collection_notes or "").strip():
            add("no_collection_notes", "low", r, "مفيش تعليمات سحب عينة")

    # أسماء مكررة بنفس الصياغة (بعد التطبيع) وأسعارها مختلفة
    for key, recs in idx.by_key.items():
        plain = [r for r in recs if not r.is_bundle]
        if len(plain) < 2:
            continue
        prices = sorted({r.price for r in plain})
        cats = " | ".join(f"{r.category}: {r.price}" for r in plain)
        if len(prices) > 1:
            add("duplicate_diff_price", "high", plain[0], f"نفس الاسم بأسعار مختلفة — {cats}")
        else:
            add("duplicate_same_price", "low", plain[0], f"مكرر بنفس السعر — {cats}")

    for b in idx.bundles:
        retail, saving = bundle_saving(b, idx)
        missing = [c for c in b.components if not idx.get(c)]
        if missing:
            add("bundle_component_missing", "high", b,
                "مكوّنات مش موجودة في القائمة: " + "، ".join(missing))
        if b.price == 0:
            add("zero_price", "high", b, "الباقة من غير سعر")
        elif saving == 0:
            add("bundle_no_saving", "medium", b,
                f"سعر الباقة = مجموع تحاليلها ({retail}) — ماتتسوّقش كخصم")
        elif saving < 0:
            add("bundle_pricier", "high", b,
                f"الباقة أغلى من تحاليلها منفصلة ({b.price} مقابل {retail})")
    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order[i["severity"]], i["kind"], i["category"], i["name"]))
    return issues


def summarize_audit(issues: List[Dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in issues:
        out[i["kind"]] = out.get(i["kind"], 0) + 1
    return out
