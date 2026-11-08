# offer_matcher.py
# ============================================================
#  🔎 مطابقة عروض الكتالوج/العروض الشغّالة على فاتورة (روشتة) اتسعّرت:
#    full   = كل تحاليل العرض موجودة -> التطبيق = خصم فوري (مجموع التحاليل − سعر العرض)
#    near   = ناقص 1–2 تحليل: لو العميل ضافهم يدفع X زيادة ويوصله تحاليل بـ Y (توفير صافي)
#    promo  = عرض من «إدارة العروض» على تحليل/باقة موجودة بسعر أقل
#  الأسعار من الفاتورة + قائمة الأسعار (مفيش نسخة تانية من الأسعار). منطق بحت.
# ============================================================

from __future__ import annotations

from datetime import date
from typing import Dict, List

from price_utils import norm
from promotions import active_promotions


def _applied_offer_ids(items: List[dict]) -> set:
    return {str(i.get("source", ""))[6:] for i in items if str(i.get("source", "")).startswith("offer:")}


def match_offers(items: List[dict], idx, offers: List[dict], *, near_missing_max: int = 2,
                 min_saving: int = 1) -> List[dict]:
    """
    بيرجّع اقتراحات مرتّبة (full قبل near، والأكبر توفيراً الأول):
      {kind, offer, have, missing, saving, extra_cost, have_sum, missing_sum, after}
    saving (full)  = مجموع تحاليل العرض في الفاتورة − سعر العرض
    saving (near)  = قيمة الناقص بسعر القائمة − اللي هيدفعه زيادة
    """
    names = {i["name"]: int(i["price"]) for i in items}
    applied = _applied_offer_ids(items)
    out = []
    for o in offers:
        if o.get("status") != "current" or not o.get("db") or not o.get("after") or o["id"] in applied:
            continue
        db = list(dict.fromkeys(o["db"]))
        have = [n for n in db if n in names]
        missing = [n for n in db if n not in names]
        if not have:
            continue
        have_sum = sum(names[n] for n in have)
        if not missing:
            saving = have_sum - int(o["after"])
            if saving >= min_saving:
                out.append({"kind": "full", "offer": o, "have": have, "missing": [], "saving": saving,
                            "extra_cost": 0, "have_sum": have_sum, "missing_sum": 0, "after": int(o["after"])})
        elif len(missing) <= near_missing_max and len(have) * 2 >= len(db):
            miss_sum = sum((idx.get(n) or [None])[0].price for n in missing if idx.get(n))
            extra = int(o["after"]) - have_sum
            if miss_sum - extra >= min_saving:      # extra سالب = العميل أصلاً بيدفع أكتر من سعر العرض
                out.append({"kind": "near", "offer": o, "have": have, "missing": missing,
                            "saving": miss_sum - extra, "extra_cost": extra, "have_sum": have_sum,
                            "missing_sum": miss_sum, "after": int(o["after"])})
    out.sort(key=lambda m: (m["kind"] != "full", -m["saving"]))
    return out


def match_promotions(items: List[dict], promos: List[dict], branch: str, today: date) -> List[dict]:
    """عروض شغّالة (إدارة العروض) على تحاليل في الفاتورة سعرها الحالي أعلى من سعر العرض."""
    by_name = {norm(i["name"]): i for i in items}
    out = []
    for p in active_promotions(promos, branch, today):
        it = by_name.get(norm(p["target"]))
        if it and int(it["price"]) > int(p["promo_price"]):
            out.append({"kind": "promo", "promo": p, "item": it["name"],
                        "saving": int(it["price"]) - int(p["promo_price"])})
    out.sort(key=lambda m: -m["saving"])
    return out
