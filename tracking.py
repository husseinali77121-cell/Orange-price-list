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

import tzsetup  # noqa: F401  (توقيت القاهرة لكل البرنامج)
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
    "مش بيرد",
    "تأجيل لوقت تاني",
    "مستني الدكتور",
    "مفيش وقت",
    "سبب تاني",
    "مش عارفين",
]

EVENT_TYPES = ("quote", "lost_sale", "converted", "campaign", "sent", "followup", "optout",
               "booked", "visited", "recovery_request", "recovery_decision", "gift",
               "vip_set", "vip_contact", "config_change", "reply", "lead", "recall_contact")

WHATSAPP_SOURCE = "💬 WhatsApp"


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
               contact: Optional[dict] = None, staff: str = "", visit_type: str = "",
               area: str = "", benefits: Optional[List[str]] = None, parent: str = "") -> dict:
    """
    event_type: "quote" (اتجهّز/اتبعت) | "lost_sale" (ماتحولش) |
                "converted" (اتباع فعلاً) | "campaign" (تصميم إعلاني اتنزّل/اتشارك —
                quote_id هنا = كود الحملة، والتفاصيل في meta) |
                "sent" (الموظف أكّد إن العرض اتبعت للعميل فعلاً — "quote" لوحده
                معناه اتجهّز بس) | "followup" (محاولة متابعة؛ meta.next_due = ميعاد
                التالية) | "optout" (العميل طلب إيقاف الرسائل — بالـ phone_key)
    دورة العميل: sent ← booked (meta.appointment) ← visited | lost_sale. الاسترجاع:
    recovery_request (meta: proposed_amount, reason, requested_by) ثم recovery_decision
    (meta: decision approved|rejected|counter, amount, approver, reason). gift: هدية
    عميل جديد (meta: gift_type, cost, delivered_by, note). vip_set / vip_contact: بصمة
    العميل (meta.vip / meta.result). config_change: سجل تعديلات إعدادات الإدارة.
    reply: الموظف استخدم رد جاهز (meta: objection, kind, reply, version) — أساس تحليل الاعتراضات.
    lead: عميل سأل على الواتساب ولسه مفيش عرض سعر (quote_id = LD-…؛ meta.next_due = ميعاد
          المتابعة) — بيظهر في المتابعة لحد ما يتعمله عرض بنفس البصمة.
    recall_contact: تذكير تحليل دوري اتبعت (meta: rule, result) — بيمنع التكرار.
    sent: ممكن يحمل meta.next_due (المتابعة اتجدولت مع الإرسال) و meta.followup_hours.
    quote: ممكن يحمل meta.inquiry_ts (وقت رسالة العميل) — لحساب سرعة الرد.
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
    if staff:
        ev["staff"] = staff
    if visit_type:
        ev["visit_type"] = visit_type            # "lab" | "home"
    if area:
        ev["area"] = area
    if benefits:
        ev["benefits"] = list(benefits)          # أكواد حملات المزايا (زيارة مجانية…)
    if parent:
        ev["parent"] = parent                    # عرض جديد مرتبط بعرض قديم (استرجاع عميل)
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


_LIFECYCLE = ("quote", "sent", "booked", "visited", "followup", "optout", "converted",
              "lost_sale", "recovery_request", "recovery_decision", "gift", "lead")


def new_lead_id(now: Optional[datetime] = None) -> str:
    """LD-YYMMDD-XXXX — عميل مستفسر من غير عرض سعر لسه."""
    import secrets as _s
    return f"LD-{(now or datetime.now()):%y%m%d}-{_s.token_hex(2).upper()}"


def quote_records(events: List[dict]) -> Dict[str, dict]:
    """
    كل عرض بدورة حياته الكاملة (من أحداث quote/sent/booked/visited/followup/converted/
    lost_sale/optout/recovery_*/gift):
      quote_ts, sent_ts, booked_ts, appointment, branch, source, total, discount, items,
      campaign_id, pk, contact, decision ("converted"|"lost_sale"), decision_ts, followups,
      next_due, optout, staff, visit_type, area, benefits, parent, recovery, gift
    "visited" = "converted" (نفس القرار — الحضور الفعلي). الأحدث بالوقت هو اللي بيكسب.
    """
    recs: Dict[str, dict] = {}

    def slot(q):
        return recs.setdefault(q, {
            "quote_id": q, "quote_ts": "", "sent_ts": "", "booked_ts": "", "appointment": "",
            "branch": "", "source": "", "total": 0, "discount": 0, "items": [],
            "campaign_id": "", "pk": "", "contact": None, "decision": "", "decision_ts": "",
            "followups": [], "next_due": "", "_nd_ts": "", "optout": False, "staff": "",
            "visit_type": "", "area": "", "benefits": [], "parent": "", "recoveries": [],
            "recovery": None, "gift": None, "lost_reason": "", "is_lead": False, "lead_ts": "",
            "inquiry_ts": "", "note": "", "no_followup": False})

    for e in events:
        q = e.get("quote_id") or ""
        typ = e.get("type")
        if typ not in _LIFECYCLE or not q:
            continue
        r = slot(q)
        ts = e.get("ts", "")
        if e.get("pk"):
            r["pk"] = e["pk"]
        if e.get("contact"):
            r["contact"] = e["contact"]
        for k in ("staff", "visit_type", "area", "parent"):
            if e.get(k):
                r[k] = e[k]
        if e.get("benefits"):
            r["benefits"] = list(e["benefits"])
        meta = e.get("meta") or {}
        if typ == "quote":
            r.update(quote_ts=ts, branch=e.get("branch", ""), source=e.get("referral_source", ""),
                     total=int(e.get("total", 0)), discount=int(e.get("discount", 0)),
                     items=list(e.get("items", [])), campaign_id=e.get("campaign_id", ""))
            if meta.get("inquiry_ts"):
                r["inquiry_ts"] = str(meta["inquiry_ts"])
        elif typ == "lead":
            # استفسار من غير عرض: بيدخل المتابعة كأنه «اتبعتله رد» من وقت التسجيل
            r.update(is_lead=True, lead_ts=ts, branch=r["branch"] or e.get("branch", ""),
                     source=r["source"] or e.get("referral_source", ""), note=e.get("note", "") or r["note"])
            if not r["sent_ts"]:
                r["sent_ts"] = ts
            if meta.get("inquiry_ts"):
                r["inquiry_ts"] = str(meta["inquiry_ts"])
            nd = meta.get("next_due", "")
            if nd and ts >= r["_nd_ts"]:
                r["next_due"], r["_nd_ts"] = nd, ts
        elif typ == "sent":
            nd = meta.get("next_due", "")
            if nd and ts >= r["_nd_ts"]:          # المتابعة اتجدولت مع الإرسال نفسه
                r["next_due"], r["_nd_ts"] = nd, ts
            if "followup_hours" in meta:          # آخر إرسال بيحدد: فيه متابعة ولا لأ
                r["no_followup"] = int(meta.get("followup_hours") or 0) <= 0
            if meta.get("inquiry_ts") and not r["inquiry_ts"]:
                r["inquiry_ts"] = str(meta["inquiry_ts"])
            src = e.get("referral_source", "")
            if src and (not r["source"] or r["source"] == "غير محدد"):
                r["source"] = src                 # المصدر اتحدد بعد ما العرض اتجهّز (لزق محادثة واتساب)
            if not r["sent_ts"] or ts >= r["sent_ts"]:
                r["sent_ts"] = ts
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
        elif typ == "booked":
            if ts >= r["booked_ts"]:
                r["booked_ts"] = ts
                r["appointment"] = (e.get("meta") or {}).get("appointment", "")
            if not r["branch"]:
                r["branch"] = e.get("branch", "")
        elif typ == "followup":
            r["followups"].append(ts)
            nd = (e.get("meta") or {}).get("next_due", "")
            if nd and ts >= r["_nd_ts"]:     # آخر محاولة بالوقت هي اللي ميعادها يمشي
                r["next_due"], r["_nd_ts"] = nd, ts
        elif typ == "optout":
            r["optout"] = True
        elif typ in ("converted", "visited", "lost_sale"):
            if ts >= r["decision_ts"]:
                r["decision"] = "lost_sale" if typ == "lost_sale" else "converted"
                r["decision_ts"] = ts
                r["lost_reason"] = e.get("reason", "") if typ == "lost_sale" else ""
                if e.get("total") and not r["total"]:
                    r["total"] = int(e["total"])
        elif typ in ("recovery_request", "recovery_decision"):
            r["recoveries"].append({"kind": "request" if typ == "recovery_request" else "decision",
                                    "ts": ts, **(e.get("meta") or {})})
        elif typ == "gift":
            if not r["gift"] or ts >= r["gift"]["ts"]:
                r["gift"] = {"ts": ts, **(e.get("meta") or {})}

    for r in recs.values():
        reqs = [x for x in r["recoveries"] if x["kind"] == "request"]
        decs = [x for x in r["recoveries"] if x["kind"] == "decision"]
        if reqs:
            lr = max(reqs, key=lambda x: x["ts"])
            ld = max(decs, key=lambda x: x["ts"]) if decs else None
            if ld is None or ld["ts"] < lr["ts"]:
                r["recovery"] = {"status": "pending", "request": lr, "decision": None}
            else:
                r["recovery"] = {"status": ld.get("decision", "rejected"), "request": lr, "decision": ld}
    return recs


def stage_of(r: dict) -> str:
    """new | sent | booked | visited | lost — حجز أحدث من القرار = العميل رجع (booked)."""
    if r["booked_ts"] and r["booked_ts"] > r["decision_ts"]:
        return "booked"
    if r["decision"] == "converted":
        return "visited"
    if r["decision"] == "lost_sale":
        return "lost"
    if r["booked_ts"]:
        return "booked"
    return "sent" if r["sent_ts"] else "new"


def optout_keys(events: List[dict]) -> set:
    """بصمات الموبايلات اللي طلبت إيقاف الرسائل التسويقية/المتابعة."""
    return {e["pk"] for e in events if e.get("type") == "optout" and e.get("pk")}


def followup_queue(events: List[dict], now: Optional[datetime] = None, *,
                   first_after_hours: float = 24, stale_after_days: float = 14,
                   max_attempts: int = 3, require_sent: bool = True,
                   visit_grace_hours: float = 3) -> dict:
    """
    قايمة المتابعة:
      due / upcoming / exhausted / stale = عروض اتبعتت (sent) من غير حجز ولا قرار
      visit_check = حجز ميعاده عدّى (أو عدّى 24 ساعة من الحجز من غير ميعاد) ولسه مفيش حضور
      booked      = حجوزات جاية
    كل عنصر: سجل quote_records + due_at + attempts + age_days.
    """
    now = now or datetime.now()
    opted = optout_keys(events)
    out = {"due": [], "upcoming": [], "exhausted": [], "stale": [], "visit_check": [], "booked": []}
    all_recs = quote_records(events)
    quoted_pk: Dict[str, str] = {}                 # آخر عرض سعر لكل بصمة (عشان نقفل الـ Lead)
    for r in all_recs.values():
        if r["pk"] and r["quote_ts"] and r["quote_ts"] > quoted_pk.get(r["pk"], ""):
            quoted_pk[r["pk"]] = r["quote_ts"]
    for q, r in all_recs.items():
        stage = stage_of(r)
        if stage in ("visited", "lost") or r["optout"] or (r["pk"] and r["pk"] in opted):
            continue
        if r["is_lead"] and not r["quote_ts"] and r["pk"] and quoted_pk.get(r["pk"], "") >= r["lead_ts"]:
            continue                               # المستفسر اتعمله عرض سعر بعدها — المتابعة على العرض
        if r["no_followup"] and stage != "booked":
            continue                               # الموظف اختار «من غير متابعة» وقت الإرسال
        item = dict(r)
        item["attempts"] = len(r["followups"])
        if stage == "booked":
            appt = _parse_ts(r["appointment"]) if r["appointment"] else None
            due_at = (appt + timedelta(hours=visit_grace_hours)) if appt else \
                (_parse_ts(r["booked_ts"]) + timedelta(hours=24))
            item["due_at"] = due_at
            item["age_days"] = (now - _parse_ts(r["booked_ts"])).total_seconds() / 86400.0
            out["visit_check" if due_at <= now else "booked"].append(item)
            continue
        base_ts = r["sent_ts"] or ("" if require_sent else r["quote_ts"])
        base = _parse_ts(base_ts)
        if base is None:
            continue
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
    for k in out:
        out[k].sort(key=lambda x: x["due_at"])
    return out


def recovery_queue(events: List[dict]) -> dict:
    """
    استرجاع العملاء اللي ماحضروش:
      pending = طلبات خصم إضافي مستنية قرار الإدارة
      ready   = موافق عليها (approved/counter) ولسه ماتعملش لها عرض جديد
      done    = اتعمل لها عرض جديد، أو اترفضت
    "عرض جديد" = quote فيه parent = العرض القديم.
    """
    recs = quote_records(events)
    children: Dict[str, List[dict]] = {}
    for r in recs.values():
        if r["parent"]:
            children.setdefault(r["parent"], []).append(r)
    out = {"pending": [], "ready": [], "done": []}
    for q, r in recs.items():
        rc = r["recovery"]
        if not rc:
            continue
        item = {**r, "children": children.get(q, [])}
        if rc["status"] == "pending":
            out["pending"].append(item)
        elif rc["status"] in ("approved", "counter") and not item["children"]:
            out["ready"].append(item)
        else:
            out["done"].append(item)
    out["pending"].sort(key=lambda x: x["recovery"]["request"]["ts"])
    return out


def customer_profile(events: List[dict], pk: str, vip_after: int = 3) -> dict:
    """
    New / Returning / VIP من بصمة الموبايل:
      VIP = اتباع له >= vip_after مرات · Returning = عرض قبل كده أو اتباع له ·
      New = أول عرض. بيرجّع كمان إجمالي المشتريات وهل موقوف.
    """
    if not pk:
        return {"label": "New", "quotes": 0, "converted": 0, "revenue": 0, "optout": False}
    recs = [r for r in quote_records(events).values() if r["pk"] == pk
            and not (r["is_lead"] and not r["quote_ts"])]        # الاستفسار لوحده مش «عرض»
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


# ------------------------------------------------------------
# العملاء (CRM): تصنيف + VIP + متابعة VIP شهرية + هدايا العملاء الجدد
# ------------------------------------------------------------

DEFAULT_VIP_RULES = {"min_visits": 3, "min_spend": 10000, "window_days": 365, "cooldown_days": 30}
CUSTOMER_LABELS = ("New", "Returning", "Regular", "VIP")


def customers(events: List[dict], vip: Optional[dict] = None,
              now: Optional[datetime] = None) -> List[dict]:
    """
    ملف لكل عميل (بالبصمة pk): عروضه، زياراته (stage visited)، إنفاقه، آخر زيارة/عرض/تواصل.
    التصنيف: New (مفيش زيارة) · Returning (زيارة واحدة) · Regular (زيارتين+) ·
    VIP = يدوي (vip_set) أو بالقواعد (زيارات >= min_visits أو إنفاق >= min_spend
    خلال window_days). vip_set false = استبعاد يدوي حتى لو القواعد اتحققت.
    الاسم/الرقم موجودين بس لو store_contacts شغّال وقت «تم الإرسال».
    """
    rules = {**DEFAULT_VIP_RULES, **(vip or {})}
    now = now or datetime.now()
    since = (now - timedelta(days=int(rules["window_days"]))).isoformat(timespec="seconds")
    manual: Dict[str, dict] = {}
    contacted: Dict[str, dict] = {}
    for e in events:
        pk = e.get("pk")
        if not pk:
            continue
        if e.get("type") == "vip_set" and e.get("ts", "") >= manual.get(pk, {}).get("ts", ""):
            manual[pk] = {"ts": e.get("ts", ""), "vip": bool((e.get("meta") or {}).get("vip"))}
        elif e.get("type") == "vip_contact" and e.get("ts", "") >= contacted.get(pk, {}).get("ts", ""):
            contacted[pk] = {"ts": e.get("ts", ""), **(e.get("meta") or {})}
    opted = optout_keys(events)
    by_pk: Dict[str, List[dict]] = {}
    lead_contacts: Dict[str, dict] = {}
    for r in quote_records(events).values():
        if r["is_lead"] and not r["quote_ts"]:              # الاستفسار: اسم/رقم بس، مش عرض
            if r["pk"] and r["contact"]:
                lead_contacts[r["pk"]] = r["contact"]
            continue
        if r["pk"]:
            by_pk.setdefault(r["pk"], []).append(r)
    out = []
    for pk, rs in by_pk.items():
        visited = [r for r in rs if stage_of(r) == "visited"]
        recent = [r for r in visited if r["decision_ts"] >= since]
        spend_recent = sum(r["total"] for r in recent)
        contact = next((r["contact"] for r in sorted(rs, key=lambda x: x["quote_ts"] or x["sent_ts"],
                                                     reverse=True) if r["contact"]), None) \
            or lead_contacts.get(pk) or {}
        m = manual.get(pk)
        if m is not None:
            is_vip = m["vip"]
        else:
            is_vip = len(recent) >= int(rules["min_visits"]) or spend_recent >= int(rules["min_spend"])
        label = "VIP" if is_vip else ("Regular" if len(visited) >= 2 else ("Returning" if visited else "New"))
        last_c = contacted.get(pk)
        out.append({
            "pk": pk, "name": contact.get("name", ""), "phone": contact.get("phone", ""),
            "has_contact": bool(contact.get("phone")), "label": label,
            "manual_vip": None if m is None else m["vip"],
            "quotes": len(rs), "visits": len(visited), "spend": sum(r["total"] for r in visited),
            "spend_recent": spend_recent, "visits_recent": len(recent),
            "last_visit": max((r["decision_ts"] for r in visited), default=""),
            "last_quote": max((r["quote_ts"] or r["sent_ts"] for r in rs), default=""),
            "last_branch": next((r["branch"] for r in sorted(rs, key=lambda x: x["quote_ts"], reverse=True)
                                 if r["branch"]), ""),
            "last_contact": last_c["ts"] if last_c else "",
            "last_contact_result": (last_c or {}).get("result", ""),
            "optout": pk in opted})
    out.sort(key=lambda c: (-c["spend"], c["pk"]))
    return out


def vip_followups(custs: List[dict], now: Optional[datetime] = None,
                  cooldown_days: int = 30) -> dict:
    """
    «Monthly VIP Follow-Up»: VIP عنده بيانات تواصل، مش موقوف، ومتكلّمش من cooldown_days.
      due = مستحق · recent = اتكلّم قريب (مايتكررش) · no_contact = VIP من غير رقم متخزّن
    """
    now = now or datetime.now()
    limit = (now - timedelta(days=int(cooldown_days))).isoformat(timespec="seconds")
    out = {"due": [], "recent": [], "no_contact": []}
    for c in custs:
        if c["label"] != "VIP" or c["optout"]:
            continue
        if not c["has_contact"]:
            out["no_contact"].append(c)
        elif c["last_contact"] and c["last_contact"] > limit:
            out["recent"].append(c)
        else:
            out["due"].append(c)
    return out


def gift_queue(events: List[dict]) -> List[dict]:
    """
    «NEW CUSTOMER – WELCOME GIFT»: زيارة منزلية (حجز/حضور) لعميل جديد ولسه الهدية
    ماتسلّمتش. عميل جديد = مفيش زيارة سابقة بنفس البصمة. من غير بصمة = بنفترض جديد
    ونعلّمه unverified_new عشان الدكتور يتأكد.
    """
    recs = quote_records(events)
    out = []
    for r in recs.values():
        if r["visit_type"] != "home" or stage_of(r) not in ("booked", "visited") or r["gift"]:
            continue
        mine = r["booked_ts"] or r["quote_ts"] or "9"
        new = not any(o is not r and o["pk"] == r["pk"] and stage_of(o) == "visited"
                      and o["decision_ts"] and o["decision_ts"] < mine
                      for o in recs.values()) if r["pk"] else True
        if new:
            out.append({**r, "unverified_new": not r["pk"]})
    out.sort(key=lambda x: x["appointment"] or x["booked_ts"] or x["quote_ts"])
    return out


def gift_stats(events: List[dict]) -> dict:
    """عدد الهدايا المسلّمة وتكلفتها (من meta.cost) وتوزيعها بالنوع."""
    gifts = [r["gift"] for r in quote_records(events).values() if r["gift"]]
    by_type: Dict[str, int] = {}
    for g in gifts:
        by_type[g.get("gift_type", "?")] = by_type.get(g.get("gift_type", "?"), 0) + 1
    return {"count": len(gifts), "cost": sum(int(g.get("cost", 0) or 0) for g in gifts),
            "by_type": by_type}


def crm_kpis(events: List[dict], fhv_ids=(), vip: Optional[dict] = None,
             now: Optional[datetime] = None) -> dict:
    """
    مؤشرات دورة العميل (الإدارة): عروض، قيمة العروض، حجوزات، حضور، فاتوا، استرجاع،
    خصومات إضافية، زيارات مجانية، VIP، هدايا، ومقارنة بالموظف.
      visit_rate_pct = حضروا ÷ اتبعتلهم العرض فعلاً (الحضور مش عدد الرسائل)
      recovered = عروض فاتت واتعمل لها عرض جديد (parent) واتحضر
      discounts_granted = مجموع الخصم الإضافي الموافق عليه (recovery_decision)
    """
    recs = list(quote_records(events).values())
    prepared = [r for r in recs if r["quote_ts"]]
    stages = {r["quote_id"]: stage_of(r) for r in prepared}
    sent = [r for r in prepared if r["sent_ts"]]
    visited = [r for r in prepared if stages[r["quote_id"]] == "visited"]
    by_id = {r["quote_id"]: r for r in recs}
    recovered = {r["parent"] for r in visited if r["parent"] and r["parent"] in by_id
                 and stage_of(by_id[r["parent"]]) == "lost"}
    granted = sum(int(r["recovery"]["decision"].get("amount", 0) or 0) for r in recs
                  if r["recovery"] and r["recovery"]["status"] in ("approved", "counter")
                  and r["recovery"]["decision"])
    fhv = [r for r in prepared if set(r["benefits"]) & set(fhv_ids)]
    by_staff: Dict[str, dict] = {}
    for r in prepared:
        k = r["staff"] or "—"
        s = by_staff.setdefault(k, {"quotes": 0, "sent": 0, "visited": 0, "value": 0})
        s["quotes"] += 1
        s["sent"] += 1 if r["sent_ts"] else 0
        s["visited"] += 1 if stages[r["quote_id"]] == "visited" else 0
        s["value"] += r["total"]
    for s in by_staff.values():
        s["visit_rate_pct"] = _pct(s["visited"], s["sent"])
    gs = gift_stats(events)
    return {
        "total_quotes": len(prepared), "quoted_value": sum(r["total"] for r in prepared),
        "sent": len(sent), "booked": sum(1 for v in stages.values() if v == "booked"),
        "visited": len(visited), "lost": sum(1 for v in stages.values() if v == "lost"),
        "visit_rate_pct": _pct(sum(1 for r in sent if stages[r["quote_id"]] == "visited"), len(sent)),
        "recovered": len(recovered), "discounts_granted": granted,
        "free_visits_offered": len(fhv),
        "free_visits_used": sum(1 for r in fhv if r["visit_type"] == "home" and stages[r["quote_id"]] == "visited"),
        "vip_customers": sum(1 for c in customers(events, vip, now) if c["label"] == "VIP"),
        "gifts_delivered": gs["count"], "gifts_cost": gs["cost"], "by_staff": by_staff,
    }


# ------------------------------------------------------------
# متابعة بعد «هفكر وأرد» — من غير تكرار، وتحليل الاعتراضات
# ------------------------------------------------------------

def can_schedule_followup(rec: dict, now: Optional[datetime] = None, *, opted: Optional[set] = None,
                          min_gap_hours: float = 12, max_attempts: int = 3) -> Tuple[bool, str]:
    """
    هل نسجّل متابعة جديدة لعرض؟ بيمنع التكرار: العرض اتقفل، العميل موقوف، خلّصت المحاولات،
    فيه متابعة مجدولة لسه، أو اتعملت متابعة من أقل من min_gap_hours. بيرجّع (مسموح، السبب).
    """
    now = now or datetime.now()
    if stage_of(rec) in ("visited", "lost"):
        return False, "العرض اتقفل (العميل حضر أو فات)"
    if rec["optout"] or (rec["pk"] and opted and rec["pk"] in opted):
        return False, "العميل طلب إيقاف الرسائل"
    if len(rec["followups"]) >= max_attempts:
        return False, f"خلّصت محاولات المتابعة ({max_attempts})"
    nd = _parse_ts(rec["next_due"]) if rec["next_due"] else None
    if nd and nd > now:
        return False, f"فيه متابعة مجدولة بالفعل ({nd:%d-%m %H:%M})"
    last = _parse_ts(max(rec["followups"])) if rec["followups"] else None
    if last and now - last < timedelta(hours=min_gap_hours):
        return False, f"اتعملت متابعة من أقل من {int(min_gap_hours)} ساعة"
    return True, ""


def objection_stats(events: List[dict]) -> Dict[str, dict]:
    """
    الاعتراضات اللي اتسجّلت بالردود الجاهزة (reply بـ meta.kind = objection)، ومصير العروض اللي حصل
    عليها الاعتراض: حضرت / فاتت / لسه مفتوحة، وأكتر أسباب الفوات ليها.
      {objection: {count, quotes, visited, lost, open, visit_rate_pct, top_reasons}}
    """
    recs = quote_records(events)
    raw: Dict[str, dict] = {}
    for e in events:
        m = e.get("meta") or {}
        if e.get("type") != "reply" or m.get("kind") != "objection" or not m.get("objection"):
            continue
        s = raw.setdefault(m["objection"], {"count": 0, "quotes": set()})
        s["count"] += 1
        if e.get("quote_id") in recs:
            s["quotes"].add(e["quote_id"])
    out: Dict[str, dict] = {}
    for k, s in raw.items():
        rs = [recs[q] for q in s["quotes"]]
        visited = sum(1 for r in rs if stage_of(r) == "visited")
        lost = [r for r in rs if stage_of(r) == "lost"]
        reasons: Dict[str, int] = {}
        for r in lost:
            if r["lost_reason"]:
                reasons[r["lost_reason"]] = reasons.get(r["lost_reason"], 0) + 1
        out[k] = {"count": s["count"], "quotes": len(rs), "visited": visited, "lost": len(lost),
                  "open": len(rs) - visited - len(lost), "visit_rate_pct": _pct(visited, len(rs)),
                  "top_reasons": sorted(reasons.items(), key=lambda x: -x[1])[:3]}
    return out


# ------------------------------------------------------------
# 💬 استفسارات الواتساب: Funnel + سرعة الرد · الاستقبال (Check-in) · ربط الحملة تلقائي
# ------------------------------------------------------------

RESPONSE_BUCKETS = (("أقل من 15 دقيقة", 15), ("15–60 دقيقة", 60), ("1–3 ساعات", 180),
                    ("أكتر من 3 ساعات", None))


def is_whatsapp(r: dict) -> bool:
    return bool(r.get("is_lead")) or "whatsapp" in (r.get("source") or "").lower()


def whatsapp_funnel(events: List[dict]) -> dict:
    """
    رحلة عميل الواتساب: استفسار (lead) ← عرض سعر ← اتبعت ← حجز ← حضر | فات.
      leads · leads_quoted (المستفسر اتعمله عرض بعدها بنفس البصمة) · quotes · sent · booked ·
      visited · lost · open · visit_rate_pct (حضروا ÷ اتبعتلهم) · quote_rate_pct ·
      median_response_min (من رسالة العميل لحد الإرسال) · by_response [{bucket, sent, visited, rate}]
    """
    recs = quote_records(events)
    quoted_pk: Dict[str, List[str]] = {}
    for r in recs.values():
        if r["pk"] and r["quote_ts"]:
            quoted_pk.setdefault(r["pk"], []).append(r["quote_ts"])
    wa = [r for r in recs.values() if is_whatsapp(r)]
    leads = [r for r in wa if r["is_lead"] and not r["quote_ts"]]
    leads_quoted = sum(1 for r in leads if r["pk"] and any(t >= r["lead_ts"] for t in quoted_pk.get(r["pk"], [])))
    quotes = [r for r in wa if r["quote_ts"]]
    sent = [r for r in quotes if r["sent_ts"]]
    st_ = {r["quote_id"]: stage_of(r) for r in quotes}
    visited = [r for r in quotes if st_[r["quote_id"]] == "visited"]
    lost = [r for r in quotes if st_[r["quote_id"]] == "lost"]
    booked = [r for r in quotes if r["booked_ts"]]
    resp, buckets = [], {b[0]: {"bucket": b[0], "sent": 0, "visited": 0} for b in RESPONSE_BUCKETS}
    for r in sent:
        a, b = _parse_ts(r["inquiry_ts"]) if r["inquiry_ts"] else None, _parse_ts(r["sent_ts"])
        if not a or not b or b < a:
            continue
        mins = (b - a).total_seconds() / 60.0
        resp.append(mins)
        label = next(lbl for lbl, lim in RESPONSE_BUCKETS if lim is None or mins < lim)
        buckets[label]["sent"] += 1
        buckets[label]["visited"] += 1 if st_[r["quote_id"]] == "visited" else 0
    resp.sort()
    median = None
    if resp:
        m = len(resp) // 2
        median = round(resp[m] if len(resp) % 2 else (resp[m - 1] + resp[m]) / 2, 1)
    by_resp = []
    for lbl, _ in RESPONSE_BUCKETS:
        b = buckets[lbl]
        if b["sent"]:
            by_resp.append({**b, "rate": _pct(b["visited"], b["sent"])})
    sent_visited = sum(1 for r in sent if st_[r["quote_id"]] == "visited")
    return {
        "leads": len(leads), "leads_quoted": leads_quoted, "quotes": len(quotes), "sent": len(sent),
        "booked": len(booked), "visited": len(visited), "lost": len(lost),
        "open": len(quotes) - len(visited) - len(lost),
        "visit_rate_pct": _pct(sent_visited, len(sent)),
        "quote_rate_pct": _pct(leads_quoted, len(leads)),
        "value_visited": sum(r["total"] for r in visited),
        "median_response_min": median, "by_response": by_resp,
    }


def open_quotes_for(events: List[dict], *, pk: str = "", code: str = "",
                    now: Optional[datetime] = None, days: int = 45) -> List[dict]:
    """
    الاستقبال: العميل وصل — عروضه المفتوحة (لسه ماحضرش ولا فات) بالبصمة أو بكود العرض.
    الأحدث الأول. الاستفسار لوحده (lead من غير عرض) مش بيظهر هنا.
    """
    now = now or datetime.now()
    since = (now - timedelta(days=days)).isoformat(timespec="seconds")
    code = (code or "").strip().upper()
    out = []
    for r in quote_records(events).values():
        if r["is_lead"] and not r["quote_ts"]:
            continue
        if not ((pk and r["pk"] == pk) or (code and r["quote_id"].upper() == code)):
            continue
        if stage_of(r) not in ("new", "sent", "booked"):
            continue
        if max(r["quote_ts"], r["sent_ts"], r["booked_ts"]) < since:
            continue
        out.append(r)
    out.sort(key=lambda r: max(r["quote_ts"], r["sent_ts"], r["booked_ts"]), reverse=True)
    return out


def appointments(events: List[dict], day=None, *, overdue_days: int = 7) -> dict:
    """
    مواعيد الاستقبال: today = حجوزات ميعادها النهاردة (مرتّبة بالساعة) ·
    overdue = حجوزات ميعادها عدّى (لحد overdue_days) ولسه محدّش سجّل حضر/ماحضرش.
    """
    from datetime import date as _date
    day = day or _date.today()
    lo = (day - timedelta(days=overdue_days)).isoformat()
    out = {"today": [], "overdue": []}
    for r in quote_records(events).values():
        if stage_of(r) != "booked" or not r["appointment"]:
            continue
        d = r["appointment"][:10]
        if d == day.isoformat():
            out["today"].append(r)
        elif lo <= d < day.isoformat():
            out["overdue"].append(r)
    for k in out:
        out[k].sort(key=lambda r: r["appointment"])
    return out


def last_campaign_for(events: List[dict], pk: str, *, now: Optional[datetime] = None,
                      days: int = 14) -> str:
    """كود آخر إعلان اتبعت للعميل ده من الاستوديو (campaign event بنفس البصمة) خلال days يوم."""
    if not pk:
        return ""
    now = now or datetime.now()
    since = (now - timedelta(days=days)).isoformat(timespec="seconds")
    best = ("", "")
    for e in events:
        if e.get("type") == "campaign" and e.get("pk") == pk and e.get("ts", "") >= since:
            if e.get("ts", "") >= best[0]:
                best = (e.get("ts", ""), e.get("quote_id", ""))
    return best[1]
