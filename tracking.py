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

import hashlib
import hmac
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

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

EVENT_TYPES = ("quote", "lost_sale", "converted", "campaign", "sent", "followup", "optout")


# ------------------------------------------------------------
# بناء حدث واحد — نفس الشكل يتحط في ملف الشهر على GitHub
# ------------------------------------------------------------

def make_event(event_type: str, quote_id: str, branch: str = "",
               referral_source: str = "", reason: str = "",
               note: str = "", total: int = 0, count: int = 0,
               items: Optional[List[str]] = None,
               now: Optional[datetime] = None,
               meta: Optional[dict] = None,
               campaign_id: str = "", phone_key: str = "", discount: int = 0,
               contact: Optional[dict] = None) -> dict:
    """
    event_type: "quote" (اتجهّز/اتبعت) | "lost_sale" (ماتحولش) |
                "converted" (اتباع فعلاً) | "campaign" (تصميم إعلاني اتنزّل/اتشارك —
                quote_id هنا = كود الحملة، والتفاصيل في meta) |
                "sent" (الموظف أكّد إن العرض اتبعت للعميل فعلاً — "quote" لوحده
                معناه اتجهّز بس) | "followup" (محاولة متابعة؛ meta.next_due = ميعاد
                التالية) | "optout" (العميل طلب إيقاف الرسائل — بالـ phone_key)
    phone_key: بصمة HMAC للموبايل (phone_key()) — بتخلّينا نعرف عميل متكرر/موقوف
               من غير ما نخزّن الرقم نفسه. contact: اسم+رقم — بيتخزّن بس لو
               secrets: store_contacts = true (ولازم الريبو يكون Private).
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
    if meta:
        ev["meta"] = dict(meta)
    if campaign_id:
        ev["campaign_id"] = campaign_id
    if phone_key:
        ev["pk"] = phone_key
    if discount:
        ev["discount"] = int(discount)
    if contact:
        ev["contact"] = dict(contact)
    return ev


def month_key(dt: Optional[datetime] = None) -> str:
    """YYYY-MM — اسم ملف الشهر (events/YYYY-MM.json)."""
    return (dt or datetime.now()).strftime("%Y-%m")


# ------------------------------------------------------------
# بصمة الموبايل (عميل متكرر / إيقاف الرسائل) من غير تخزين الرقم
# ------------------------------------------------------------

def phone_key(phone_e164: str, secret: str) -> str:
    """HMAC-SHA256(secret, رقم) مقصوص 16 حرف. فاضي لو مفيش secret أو رقم —
    من غير secret البصمة كانت هتتفك بتجربة كل الأرقام، فمبنعملهاش."""
    digits = re.sub(r"\D", "", phone_e164 or "")
    if not secret or len(digits) < 8:
        return ""
    mac = hmac.new(secret.encode("utf-8"), b"pk:" + digits.encode("ascii"),
                   hashlib.sha256).hexdigest()
    return mac[:16]


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def quote_records(events: List[dict]) -> Dict[str, dict]:
    """
    كل عرض بتاريخه الكامل (من أحداث quote/sent/followup/converted/lost_sale/optout):
      qid -> {quote_ts, sent_ts, branch, source, total, discount, items,
              campaign_id, pk, contact, decision, decision_ts, followups:[ts],
              next_due, optout}
    الأحدث بالوقت هو اللي بيكسب في القرار؛ campaign/غيره مابيتحسبش كعرض.
    """
    recs: Dict[str, dict] = {}

    def slot(q):
        return recs.setdefault(q, {
            "quote_id": q, "quote_ts": "", "sent_ts": "", "branch": "", "source": "",
            "total": 0, "discount": 0, "items": [], "campaign_id": "", "pk": "",
            "contact": None, "decision": "", "decision_ts": "", "followups": [],
            "next_due": "", "_nd_ts": "", "optout": False})

    for e in events:
        q = e.get("quote_id") or ""
        typ = e.get("type")
        if typ == "campaign" or not q:
            continue
        r = slot(q)
        if e.get("pk"):
            r["pk"] = e["pk"]
        if e.get("contact"):
            r["contact"] = e["contact"]
        if typ == "quote":
            r.update(quote_ts=e.get("ts", ""), branch=e.get("branch", ""),
                     source=e.get("referral_source", ""), total=int(e.get("total", 0)),
                     discount=int(e.get("discount", 0)), items=list(e.get("items", [])),
                     campaign_id=e.get("campaign_id", ""))
        elif typ == "sent":
            if not r["sent_ts"] or e.get("ts", "") >= r["sent_ts"]:
                r["sent_ts"] = e.get("ts", "")
                # الأرقام وقت الإرسال هي الأدق (الخصم/الإجمالي ممكن يتغيّر بعد أول quote)
                if e.get("total"):
                    r["total"] = int(e["total"])
                if "discount" in e:
                    r["discount"] = int(e["discount"])
                if e.get("items"):
                    r["items"] = list(e["items"])
            if not r["branch"]:
                r["branch"] = e.get("branch", "")
            if e.get("campaign_id") and not r["campaign_id"]:
                r["campaign_id"] = e["campaign_id"]
        elif typ == "followup":
            r["followups"].append(e.get("ts", ""))
            nd = (e.get("meta") or {}).get("next_due", "")
            if nd and e.get("ts", "") >= r["_nd_ts"]:     # آخر محاولة بالوقت هي اللي ميعادها يمشي
                r["next_due"], r["_nd_ts"] = nd, e.get("ts", "")
        elif typ == "optout":
            r["optout"] = True
        elif typ in ("converted", "lost_sale"):
            if e.get("ts", "") >= r["decision_ts"]:
                r["decision"], r["decision_ts"] = typ, e.get("ts", "")
                if e.get("total") and not r["total"]:
                    r["total"] = int(e["total"])
    return recs


def optout_keys(events: List[dict]) -> set:
    """بصمات الموبايلات اللي طلبت إيقاف الرسائل التسويقية/المتابعة."""
    return {e["pk"] for e in events if e.get("type") == "optout" and e.get("pk")}


def followup_queue(events: List[dict], now: Optional[datetime] = None, *,
                   first_after_hours: float = 24, stale_after_days: float = 14,
                   max_attempts: int = 3, require_sent: bool = True) -> dict:
    """
    قايمة «متابعة النهاردة»: عروض اتبعتت (sent) ولسه مفيش قرار ومش موقوفة.
      due       = ميعادها جه (متأخر الأول)
      upcoming  = لسه
      exhausted = اتعملها max_attempts محاولات من غير نتيجة
      stale     = أقدم من stale_after_days (بنعتبرها ماتت)
    كل عنصر: سجل quote_records + due_at (datetime) + attempts.
    """
    now = now or datetime.now()
    opted = optout_keys(events)
    out = {"due": [], "upcoming": [], "exhausted": [], "stale": []}
    for q, r in quote_records(events).items():
        if r["decision"] or r["optout"] or (r["pk"] and r["pk"] in opted):
            continue
        base_ts = r["sent_ts"] or ("" if require_sent else r["quote_ts"])
        base = _parse_ts(base_ts)
        if base is None:
            continue
        item = dict(r)
        item["attempts"] = len(r["followups"])
        nd = _parse_ts(r["next_due"]) if r["next_due"] else None
        last = _parse_ts(max(r["followups"])) if r["followups"] else None
        due_at = nd or ((last or base) + timedelta(hours=first_after_hours))
        item["due_at"] = due_at
        item["age_days"] = (now - base).total_seconds() / 86400.0
        if now - base > timedelta(days=stale_after_days):
            out["stale"].append(item)
        elif item["attempts"] >= max_attempts:
            out["exhausted"].append(item)
        elif due_at <= now:
            out["due"].append(item)
        else:
            out["upcoming"].append(item)
    out["due"].sort(key=lambda x: x["due_at"])
    out["upcoming"].sort(key=lambda x: x["due_at"])
    return out


def customer_profile(events: List[dict], pk: str, vip_after: int = 3) -> dict:
    """
    New / Returning / VIP من بصمة الموبايل:
      VIP = اتباع له >= vip_after مرات · Returning = عرض قبل كده أو اتباع له ·
      New = أول عرض. بيرجّع كمان إجمالي المشتريات وهل موقوف.
    """
    if not pk:
        return {"label": "New", "quotes": 0, "converted": 0, "revenue": 0, "optout": False}
    recs = [r for r in quote_records(events).values() if r["pk"] == pk]
    conv = [r for r in recs if r["decision"] == "converted"]
    label = "VIP" if len(conv) >= vip_after else ("Returning" if (len(recs) >= 2 or conv) else "New")
    return {"label": label, "quotes": len(recs), "converted": len(conv),
            "revenue": sum(r["total"] for r in conv),
            "optout": pk in optout_keys(events)}


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


# ------------------------------------------------------------
# مؤشرات إدارية (Dashboard): متوسط العرض/الخصم، المتكررين، الفروع، الحملات
# ------------------------------------------------------------

def _pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 1) if b else 0.0


def marketing_kpis(events: List[dict]) -> dict:
    """
    مؤشرات فوق summarize_events (نفس الأحداث، من غير ما نغيّر أرقامه):
      sent · prepared_not_sent · avg_quote_value · avg_discount_pct ·
      customers (بصمات مميّزة) · returning_customers · repeat_pct ·
      avg_hours_to_convert · lost_value (قيمة فرص البيع المفقودة — مش إيراد محقّق) ·
      by_branch · campaign_stats {campaign_id: {...}}
    ملاحظة: متوسط الخصم بيعتبر العروض القديمة (قبل تسجيل الخصم) من غير خصم.
    """
    recs = [r for r in quote_records(events).values() if r["quote_ts"]]
    priced = [r for r in recs if r["total"] > 0]
    gross = sum(r["total"] + r["discount"] for r in priced)
    sent = sum(1 for r in recs if r["sent_ts"])

    per_pk: Dict[str, set] = {}
    for r in recs:
        if r["pk"]:
            per_pk.setdefault(r["pk"], set()).add(r["quote_id"])
    returning = sum(1 for qs in per_pk.values() if len(qs) >= 2)

    hrs = []
    for r in recs:
        if r["decision"] == "converted":
            a, b = _parse_ts(r["sent_ts"] or r["quote_ts"]), _parse_ts(r["decision_ts"])
            if a and b and b >= a:
                hrs.append((b - a).total_seconds() / 3600.0)

    def group(key_fn):
        g: Dict[str, dict] = {}
        for r in recs:
            k = key_fn(r)
            if not k:
                continue
            s = g.setdefault(k, {"quotes": 0, "sent": 0, "converted": 0, "lost": 0,
                                 "revenue": 0, "lost_value": 0})
            s["quotes"] += 1
            s["sent"] += 1 if r["sent_ts"] else 0
            if r["decision"] == "converted":
                s["converted"] += 1
                s["revenue"] += r["total"]
            elif r["decision"] == "lost_sale":
                s["lost"] += 1
                s["lost_value"] += r["total"]
        for s in g.values():
            s["conversion_pct"] = _pct(s["converted"], s["converted"] + s["lost"])
        return g

    return {
        "sent": sent,
        "prepared_not_sent": len(recs) - sent,
        "avg_quote_value": round(sum(r["total"] for r in priced) / len(priced)) if priced else 0,
        "avg_discount_pct": _pct(sum(r["discount"] for r in priced), gross),
        "customers": len(per_pk),
        "returning_customers": returning,
        "repeat_pct": _pct(returning, len(per_pk)),
        "avg_hours_to_convert": round(sum(hrs) / len(hrs), 1) if hrs else None,
        "lost_value": sum(r["total"] for r in recs if r["decision"] == "lost_sale"),
        "by_branch": group(lambda r: r["branch"]),
        "campaign_stats": group(lambda r: r["campaign_id"]),
    }
