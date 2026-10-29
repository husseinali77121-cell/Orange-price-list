# tracking.py
# ============================================================
#  Orange Lab — Referral Source + Lost Sale tracking (Phase 2)
#  منطق بحت: لا استيراد لـ streamlit ولا شبكة -> قابل للاختبار
#  من الترمكس مباشرة (test_tracking.py)
#
#  التخزين الفعلي (قراءة/كتابة GitHub) في github_store.py.
#  الملف ده بيهتم بس بـ: شكل الحدث (event)، وتلخيص مجموعة أحداث.
# ============================================================

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

# ------------------------------------------------------------
# خيارات ثابتة تظهر في الواجهة (radio/selectbox)
# ------------------------------------------------------------

REFERRAL_SOURCES = [
    "👨‍⚕️ طبيب / عيادة",
    "🚶 Walk-in",
    "📱 Google",
    "📘 Facebook",
    "📸 Instagram",
    "💬 WhatsApp",
    "🗣️ توصية عميل",
    "غير محدد",
]

LOST_SALE_REASONS = [
    "السعر",
    "عدد التحاليل كتير",
    "هيفكر ويرد",
    "معمل تاني",
    "مستني الدكتور",
    "مفيش وقت",
    "سبب تاني",
    "مش عارفين",
]

EVENT_TYPES = ("quote", "lost_sale", "converted")


# ------------------------------------------------------------
# بناء حدث واحد — نفس الشكل يتحط في ملف الشهر على GitHub
# ------------------------------------------------------------

def make_event(event_type: str, quote_id: str, branch: str = "",
               referral_source: str = "", reason: str = "",
               note: str = "", total: int = 0, count: int = 0,
               items: Optional[List[str]] = None,
               now: Optional[datetime] = None) -> dict:
    """
    event_type: "quote" (اتجهّز/اتبعت) | "lost_sale" (ماتحولش) |
                "converted" (اتباع فعلاً)
    items: أسماء التحاليل/الباقات في الفاتورة — بتتحط مع "quote" بس
           (لتحليل "أكتر التحاليل طلباً" و"نسبة تحويل كل باقة" لاحقاً)
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type: {event_type}")
    ts = (now or datetime.now()).isoformat(timespec="seconds")
    ev = {
        "type": event_type,
        "quote_id": quote_id,
        "branch": branch,
        "ts": ts,
    }
    if referral_source:
        ev["referral_source"] = referral_source
    if reason:
        ev["reason"] = reason
    if note:
        ev["note"] = note
    if total:
        ev["total"] = int(total)
    if count:
        ev["count"] = int(count)
    if items:
        ev["items"] = list(items)
    return ev


def month_key(dt: Optional[datetime] = None) -> str:
    """YYYY-MM — اسم ملف الشهر (events/YYYY-MM.json)."""
    return (dt or datetime.now()).strftime("%Y-%m")


# ------------------------------------------------------------
# تلخيص مجموعة أحداث (ملف شهر واحد أو أكتر مجمّعين) -> أرقام Dashboard
# ------------------------------------------------------------

def _final_decisions(events: List[dict]) -> Dict[str, dict]:
    """
    آخر قرار لكل عرض (converted أو lost_sale) — الأحدث بالوقت يكسب، والتعادل
    للأحدث في الترتيب. كده الضغط مرتين ماكررش الإيراد، وتغيير القرار (فات ثم
    اتباع) بيتحسب مرة واحدة بس، حتى لو الأحداث المكررة متخزّنة فعلاً.
    """
    best: Dict[str, tuple] = {}
    for i, e in enumerate(events):
        if e["type"] not in ("converted", "lost_sale"):
            continue
        qid = e.get("quote_id") or ""
        key = (e.get("ts", ""), i)
        if qid not in best or key >= best[qid][0]:
            best[qid] = (key, e)
    return {q: v[1] for q, v in best.items()}


def summarize_events(events: List[dict],
                     bundle_names: Optional[set] = None) -> dict:
    """
    بيرجّع:
      quotes, lost, converted, pending, conversion_pct,
      top_lost_reasons: [(reason, count), ...] ترتيب تنازلي
      top_sources: [(source, count), ...] ترتيب تنازلي (من أحداث quote بس)
      top_tests: [(test_or_bundle_name, count), ...] ترتيب تنازلي —
                 كام فاتورة طلبت التحليل/الباقة دي (بغض النظر عن العدد)
      package_stats: {bundle_name: {"quotes":N,"converted":N,"lost":N,
                       "conversion_pct":X}} — بس للأسماء اللي في
                       bundle_names (لو اتبعتت)؛ من غيرها بترجع {}
      revenue_lost: مجموع total بتاع أحداث lost_sale
      revenue_converted: مجموع total بتاع أحداث converted
    """
    by_quote: Dict[str, dict] = {}
    quote_items: Dict[str, List[str]] = {}
    for e in events:
        qid = e.get("quote_id") or ""
        slot = by_quote.setdefault(qid, {})
        slot[e["type"]] = e
        if e["type"] == "quote":
            slot["referral_source"] = e.get("referral_source", "")
            if "items" in e:
                quote_items[qid] = e["items"]

    final = _final_decisions(events)
    quotes = sum(1 for s in by_quote.values() if "quote" in s)
    lost = sum(1 for e in final.values() if e["type"] == "lost_sale")
    converted = sum(1 for e in final.values() if e["type"] == "converted")
    # عرض اتعمله quote بس، ولسه ماتحددش مصيره (لا اتباع ولا اتفوّت)
    pending = sum(1 for q, s in by_quote.items() if "quote" in s and q not in final)

    decided = converted + lost
    conversion_pct = round(100.0 * converted / decided, 1) if decided else 0.0

    reason_counts: Dict[str, int] = {}
    for e in final.values():
        if e["type"] == "lost_sale":
            r = e.get("reason") or "مش عارفين"
            reason_counts[r] = reason_counts.get(r, 0) + 1
    top_lost_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])

    source_counts: Dict[str, int] = {}
    for s_ in by_quote.values():          # مرة واحدة لكل عرض
        if "quote" in s_:
            s = s_["quote"].get("referral_source") or "غير محدد"
            source_counts[s] = source_counts.get(s, 0) + 1
    top_sources = sorted(source_counts.items(), key=lambda x: -x[1])

    test_counts: Dict[str, int] = {}
    for names in quote_items.values():
        for n in set(names):   # مرة واحدة لكل فاتورة، حتى لو اتكرر الاسم
            test_counts[n] = test_counts.get(n, 0) + 1
    top_tests = sorted(test_counts.items(), key=lambda x: -x[1])

    package_stats: Dict[str, dict] = {}
    if bundle_names:
        for qid, names in quote_items.items():
            fin = final.get(qid)
            for n in set(names):
                if n not in bundle_names:
                    continue
                ps = package_stats.setdefault(
                    n, {"quotes": 0, "converted": 0, "lost": 0})
                ps["quotes"] += 1
                if fin and fin["type"] == "converted":
                    ps["converted"] += 1
                elif fin and fin["type"] == "lost_sale":
                    ps["lost"] += 1
        for ps in package_stats.values():
            dec = ps["converted"] + ps["lost"]
            ps["conversion_pct"] = round(100.0 * ps["converted"] / dec, 1) if dec else 0.0

    revenue_lost = sum(int(e.get("total", 0)) for e in final.values()
                       if e["type"] == "lost_sale")
    revenue_converted = sum(int(e.get("total", 0)) for e in final.values()
                            if e["type"] == "converted")

    return {
        "quotes": quotes,
        "lost": lost,
        "converted": converted,
        "pending": pending,
        "conversion_pct": conversion_pct,
        "top_lost_reasons": top_lost_reasons,
        "top_sources": top_sources,
        "top_tests": top_tests,
        "package_stats": package_stats,
        "revenue_lost": revenue_lost,
        "revenue_converted": revenue_converted,
    }
