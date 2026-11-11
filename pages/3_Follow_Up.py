# pages/3_Follow_Up.py
# ============================================================
#  📞 Follow-up CRM — مصير كل عرض: اتبعت ← حجز ← حضر | ماحضرش ← استرجاع
#  • Follow-up: عروض اتبعتت من غير رد (بعد 24 ساعة): تواصل / حجز / حضر / فاتت
#  • Visits: حجوزات ميعادها عدّى — حضر؟ ولا ماحضرش؟
#  • Recovery: «Request Special Discount» لعميل فاتت — الإدارة بتوافق/ترفض/تعدّل، وبعدها
#    عرض جديد مرتبط بالقديم. الخصم الإضافي ماينفعش يبقى تلقائي: كل قرار بيتسجّل (مين
#    وافق، كام، وليه) وبيظهر في الداشبورد.
#  كلمة سر الموظفين (staff_password) أو الإدارة؛ الموافقات بكلمة سر الإدارة.
# ============================================================

from datetime import datetime, timedelta
from datetime import time as dtime

import streamlit as st

from access import admin_gate, require_access, secret_bool, secret_str
from brand import LAB_NAME_AR
from bundles import BUNDLES as BUNDLE_DEFS
from bundles import BUNDLE_CATEGORY
from github_store import (GithubStoreError, events_path, read_events_range,
                          store_from_secrets)
from labs_price_list import LABS_DB
from marketing import build_followup_message, share_url
from navigation import render_nav
from price_utils import build_index, build_whatsapp_url
from recovery import recovery_link
import config_store
import replies as RP
from patient_prep import prep_block
from tracking import (LOST_SALE_REASONS, followup_queue, make_event, month_key,
                      optout_keys, quote_records, recovery_queue, stage_of)

st.set_page_config(page_title="Orange Lab - Follow-up", page_icon="📞", layout="wide")
st.markdown("## 📞 Follow-up CRM")
render_nav(st, "pages/3_Follow_Up.py")
require_access(st, "صفحة المتابعة", level="staff")

store = store_from_secrets(st.secrets)
if not store:
    st.warning("تتبّع العروض مش متظبط (gh_events_token / gh_events_repo في Secrets).")
    st.stop()

store_contacts = secret_bool(st.secrets, "store_contacts")
QUOTE_SECRET = secret_str(st.secrets, "quote_secret")


@st.cache_resource(show_spinner=False)
def load_index():
    return build_index(LABS_DB, BUNDLE_DEFS, BUNDLE_CATEGORY)


IDX = load_index()
BUNDLE_COMPONENTS = {b["name"]: list(b.get("components", [])) for b in BUNDLE_DEFS}


@st.cache_data(ttl=120, show_spinner=False)
def load_cfg():
    return config_store.load(store_from_secrets(st.secrets))


CFG = load_cfg()
BRANCH_NAMES = [(v or {}).get("name_ar", k) for k, v in CFG["branches"].items()]


def _prev_month(d: datetime) -> str:
    y, m = d.year, d.month - 1
    if m < 1:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


@st.cache_data(ttl=60, show_spinner=False)
def load_events(start_m: str, end_m: str):
    return read_events_range(store_from_secrets(st.secrets), start_m, end_m)


now = datetime.now()
try:
    events = load_events(_prev_month(now), month_key(now))
except GithubStoreError as e:
    st.error(f"مقدرتش أجيب البيانات: {e}")
    st.stop()

st.session_state.setdefault("staff_name", "")
STAFF = st.text_input("اسمك (بيتسجّل على كل إجراء)", key="staff_name")

q = followup_queue(events, now)
rq = recovery_queue(events)
recs = quote_records(events)
opted = optout_keys(events)

m1, m2, m3, m4 = st.columns(4)
m1.metric("⏰ متابعات مستحقة", len(q["due"]))
m2.metric("📅 حضور للتأكيد", len(q["visit_check"]))
m3.metric("🗓️ حجوزات جاية", len(q["booked"]))
m4.metric("💸 مستنية قرار الإدارة", len(rq["pending"]))
if st.button("🔄 تحديث"):
    load_events.clear()
    st.rerun()
if not store_contacts:
    st.info("أرقام العملاء مش بتتخزّن (الوضع الافتراضي لحماية الخصوصية). لتفعيل واتساب المباشر "
            "وبيانات الاسترجاع ضيف `store_contacts = true` في Secrets **وتأكد إن ريبو الأحداث Private**.")


def log(ev: dict) -> bool:
    try:
        store.append(events_path(month_key()), ev)
        load_events.clear()
        return True
    except GithubStoreError as e:
        st.error(f"مقدرتش أسجّل: {e}")
        return False


def _appt(key: str):
    c1, c2 = st.columns(2)
    d = c1.date_input("الميعاد", value=(now + timedelta(days=1)).date(), key=f"{key}_d")
    t = c2.time_input("الساعة", value=dtime(10, 0), key=f"{key}_t")
    return datetime.combine(d, t).isoformat(timespec="seconds")


def _head(r, icon):
    c = r.get("contact") or {}
    if r.get("is_lead") and not r.get("quote_ts"):
        t = f"{icon} 🟡 مستفسر (من غير عرض) · {r['branch'] or '—'}"
    else:
        t = f"{icon} {r['quote_id']} · {r['total']:,} ج · {r['branch'] or '—'}"
    return t + (f" · {c['name']}" if c.get("name") else "")


def _lost_buttons(r, key_prefix_lost, key_prefix_reason):
    reason = st.selectbox("سبب عدم الحضور/الإتمام", LOST_SALE_REASONS, key=f"{key_prefix_reason}_{r['quote_id']}")
    return reason, st.button("❌ Not visited / فاتت", key=f"{key_prefix_lost}_{r['quote_id']}", use_container_width=True)


def card(r: dict, due: bool):
    c = r.get("contact") or {}
    qid = r["quote_id"]
    with st.expander(_head(r, "🔴" if due else "🕒"), expanded=due and len(q["due"]) <= 3):
        st.caption(f"اتبعت من {r['age_days']:.1f} يوم · محاولات: {r['attempts']}"
                   + (f" · حملة: {r['campaign_id']}" if r["campaign_id"] else "")
                   + (f" · {r['staff']}" if r["staff"] else "") + f" · ميعادها: {r['due_at']:%d-%m %H:%M}")
        if r["items"]:
            st.write("🧪 " + "، ".join(r["items"]))
        lead = bool(r.get("is_lead") and not r.get("quote_ts"))
        msg = build_followup_message(lab=LAB_NAME_AR, name=(c.get("name") or "").split(" ")[0],
                                     items=r["items"], total=r["total"], attempt=r["attempts"], lead=lead,
                                     cta="" if lead else RP.booking_cta(BRANCH_NAMES),
                                     code="" if lead else RP.code_line(qid))
        msg = st.text_area("نص الرسالة", msg, key=f"m_{qid}", height=120)
        phone = (c.get("phone") or "").strip()
        st.link_button("📲 افتح واتساب" if phone else "📲 واتساب (اختار جهة الاتصال)",
                       build_whatsapp_url(phone, msg) if phone else share_url(msg), use_container_width=True)
        a1, a2, a3 = st.columns(3)
        if a1.button("✔ اتواصلت — بكرة", key=f"f1_{qid}", use_container_width=True):
            if log(make_event("followup", qid, branch=r["branch"], staff=STAFF,
                              meta={"next_due": (now + timedelta(hours=24)).isoformat(timespec="seconds")})):
                st.rerun()
        if a2.button("⏰ بعد 3 أيام", key=f"f3_{qid}", use_container_width=True):
            if log(make_event("followup", qid, branch=r["branch"], staff=STAFF,
                              meta={"next_due": (now + timedelta(days=3)).isoformat(timespec="seconds")})):
                st.rerun()
        if a3.button("🚫 مايتبعتلوش تاني", key=f"oo_{qid}", use_container_width=True):
            if log(make_event("optout", qid, branch=r["branch"], phone_key=r.get("pk", ""))):
                st.rerun()
        if lead:
            st.caption("🟡 لو بعت الروشتة/التحاليل اعمله عرض سعر من Invoice بنفس الرقم — المستفسر بيتقفل لوحده.")
            reason, clicked = _lost_buttons(r, "ls", "rs")
            if clicked and log(make_event("lost_sale", qid, branch=r["branch"], reason=reason, staff=STAFF)):
                st.rerun()
            return
        st.markdown("**📅 العميل وافق وحجز؟**")
        appt = _appt(f"bk_{qid}")
        if st.button("📅 Booked", key=f"bk_{qid}", use_container_width=True):
            if log(make_event("booked", qid, branch=r["branch"], staff=STAFF, visit_type=r["visit_type"],
                              area=r["area"], meta={"appointment": appt})):
                st.rerun()
        b1, b2 = st.columns(2)
        if b1.button("✅ Visited / اتباع", key=f"cv_{qid}", use_container_width=True, type="primary"):
            if log(make_event("converted", qid, branch=r["branch"], total=r["total"], staff=STAFF)):
                st.rerun()
        with b2:
            reason, clicked = _lost_buttons(r, "ls", "rs")
        if clicked and log(make_event("lost_sale", qid, branch=r["branch"], reason=reason, total=r["total"], staff=STAFF)):
            st.rerun()


def visit_card(r: dict, check: bool):
    qid = r["quote_id"]
    c = r.get("contact") or {}
    with st.expander(_head(r, "📅"), expanded=check and len(q["visit_check"]) <= 3):
        st.caption(f"ميعاد الزيارة: {r['appointment'] or '—'} · {'🏠 زيارة منزلية' if r['visit_type'] == 'home' else '🏥 المعمل'}"
                   + (f" · {r['area']}" if r["area"] else ""))
        if r["items"]:
            st.write("🧪 " + "، ".join(r["items"]))
        # رسالة جاهزة: تذكير قبل الميعاد (بالتحضير) — أو «افتقدناك» لو الميعاد عدّى
        binfo = CFG["branches"].get(r["branch"])
        tpl = RP.get("missed_appt" if check else "appt_reminder")
        rmsg = RP.render_reply(tpl, "short", name=c.get("name", ""), lab=LAB_NAME_AR,
                               appt_text="" if check else RP.appt_line(r["appointment"]),
                               prep_text="" if check else prep_block(r["items"], BUNDLE_COMPONENTS),
                               branch_text=config_store.branch_block(binfo, compact=True) if (binfo and not check) else "")
        rmsg = st.text_area("رسالة " + ("«افتقدناك»" if check else "التذكير"), rmsg, key=f"vm_{qid}", height=110)
        phone = (c.get("phone") or "").strip()
        st.link_button(("📲 ابعت «افتقدناك» — نحجز ميعاد تاني" if check else "📲 ابعت تذكير بالميعاد")
                       + ("" if phone else " (اختار جهة الاتصال)"),
                       build_whatsapp_url(phone, rmsg) if phone else share_url(rmsg), use_container_width=True)
        if check:
            v1, v2 = st.columns(2)
            if v1.button("✅ Visited — حضر", key=f"vv_{qid}", use_container_width=True, type="primary"):
                if log(make_event("converted", qid, branch=r["branch"], total=r["total"], staff=STAFF)):
                    st.rerun()
            with v2:
                reason, clicked = _lost_buttons(r, "vn", "vr")
            if clicked and log(make_event("lost_sale", qid, branch=r["branch"], reason=reason,
                                          total=r["total"], staff=STAFF)):
                st.rerun()
        st.markdown("**إعادة جدولة**")
        appt = _appt(f"vs_{qid}")
        if st.button("📅 غيّر الميعاد", key=f"vs_{qid}", use_container_width=True):
            if log(make_event("booked", qid, branch=r["branch"], staff=STAFF, visit_type=r["visit_type"],
                              area=r["area"], meta={"appointment": appt})):
                st.rerun()


tab_fu, tab_visits, tab_rec, tab_admin = st.tabs(["⏰ Follow-up", "📅 Visits", "💸 Recovery", "🔐 Approvals"])

with tab_fu:
    st.markdown("### ⏰ مستحقة")
    if q["due"]:
        for r in q["due"]:
            card(r, True)
    else:
        st.success("مفيش متابعات مستحقة دلوقتي 👌")
    with st.expander(f"🕒 جاية ({len(q['upcoming'])})"):
        for r in q["upcoming"]:
            card(r, False)
    with st.expander(f"⛔ خلّصت المحاولات ({len(q['exhausted'])}) — قرّر: فاتت ولا تقفل"):
        for r in q["exhausted"]:
            card(r, False)
    st.caption(f"💤 قديمة (أكتر من 14 يوم): {len(q['stale'])} · موقوفين (opt-out): {len(opted)}")

with tab_visits:
    st.markdown("### 📅 حضر ولا لأ؟")
    if q["visit_check"]:
        for r in q["visit_check"]:
            visit_card(r, True)
    else:
        st.success("مفيش حجوزات محتاجة تأكيد حضور 👌")
    with st.expander(f"🗓️ حجوزات جاية ({len(q['booked'])})"):
        for r in q["booked"]:
            visit_card(r, False)

with tab_rec:
    st.caption("العميل اللي ماحضرش: اطلب خصم إضافي من الإدارة. مفيش خصم تلقائي — القرار للإدارة وبيتسجّل.")
    lost = [r for r in recs.values() if stage_of(r) == "lost" and not r["recovery"] and r["total"] > 0
            and r["decision_ts"] >= (now - timedelta(days=30)).isoformat(timespec="seconds")
            and not r["optout"] and not (r["pk"] and r["pk"] in opted)]
    lost.sort(key=lambda r: r["decision_ts"], reverse=True)
    st.markdown(f"### 🟠 عملاء فاتوا — آخر 30 يوم ({len(lost)})")
    for r in lost:
        qid, c = r["quote_id"], r.get("contact") or {}
        with st.expander(_head(r, "🟠")):
            st.caption(f"سبب الفوات: {r['lost_reason'] or '—'}")
            if r["items"]:
                st.write("🧪 " + "، ".join(r["items"]))
            amt = st.number_input("الخصم الإضافي المقترح (ج)", min_value=0, step=10,
                                  value=int(round(r["total"] * 0.05 / 10) * 10), key=f"rqa_{qid}")
            why = st.text_input("سبب عدم إتمام الحجز", value=r["lost_reason"], key=f"rqr_{qid}")
            note = st.text_input("ملاحظات للإدارة", key=f"rqn_{qid}")
            if st.button("💸 Request Special Discount", key=f"rq_{qid}", type="primary", use_container_width=True):
                if log(make_event("recovery_request", qid, branch=r["branch"], staff=STAFF,
                                  meta={"proposed_amount": int(amt), "reason": why.strip(), "note": note.strip(),
                                        "requested_by": STAFF.strip(), "total": r["total"]})):
                    st.rerun()

    st.markdown(f"### ⏳ مستنية قرار الإدارة ({len(rq['pending'])})")
    for r in rq["pending"]:
        rqs = r["recovery"]["request"]
        st.write(f"• {_head(r, '')} — مقترح {rqs.get('proposed_amount', 0):,} ج · {rqs.get('reason', '')}")

    st.markdown(f"### ✅ موافق عليها — اعمل العرض الجديد ({len(rq['ready'])})")
    for r in rq["ready"]:
        d = r["recovery"]["decision"]
        with st.expander(_head(r, "✅")):
            st.caption(f"وافق: {d.get('approver', '—')} · الخصم الإضافي: {int(d.get('amount', 0)):,} ج · {d.get('reason', '')}")
            url, missing = recovery_link(r, int(d.get("amount", 0)), IDX, QUOTE_SECRET)
            if missing:
                st.warning("تحاليل مش موجودة في القائمة دلوقتي: " + "، ".join(missing))
            st.link_button("🧾 افتح العرض الجديد في الفاتورة", url, use_container_width=True)
            if not QUOTE_SECRET:
                st.caption("⚠️ من غير quote_secret العرض الجديد مش معلَّم «معتمد» — هيطلب كود الموافقة لو الخصم فوق الحد.")
    with st.expander(f"📜 اتنفّذت / اترفضت ({len(rq['done'])})"):
        for r in rq["done"]:
            d = r["recovery"]["decision"] or {}
            st.write(f"• {_head(r, '')} — {d.get('decision', '')} {int(d.get('amount', 0) or 0):,} ج · {d.get('approver', '')}"
                     + (f" · عروض جديدة: {', '.join(c['quote_id'] for c in r['children'])}" if r["children"] else ""))

with tab_admin:
    st.caption("للإدارة: قرار الخصم الإضافي. بيتسجّل اسمك وقيمة الخصم والسبب.")
    if admin_gate(st, key="fu_admin_pw"):
        if not rq["pending"]:
            st.success("مفيش طلبات مستنية 👌")
        for r in rq["pending"]:
            qid, rqs, c = r["quote_id"], r["recovery"]["request"], r.get("contact") or {}
            with st.expander(_head(r, "💸"), expanded=True):
                st.write(f"👤 {c.get('name', '—')} · {c.get('phone', '—')} · قيمة العرض السابق: **{r['total']:,} ج**")
                st.write("🧪 " + ("، ".join(r["items"]) or "—"))
                st.write(f"❓ السبب: {rqs.get('reason', '—')} · طلب: {rqs.get('requested_by', '—')} · "
                         f"مقترح: **{int(rqs.get('proposed_amount', 0)):,} ج** — {rqs.get('note', '')}")
                dec = st.radio("القرار", ["approved", "counter", "rejected"], horizontal=True, key=f"dc_{qid}",
                               format_func=lambda k: {"approved": "✅ موافقة", "counter": "↔️ خصم مختلف",
                                                      "rejected": "🚫 رفض"}[k])
                amt = st.number_input("الخصم الإضافي الموافق عليه (ج)", min_value=0, step=10,
                                      value=int(rqs.get("proposed_amount", 0)), key=f"da_{qid}")
                who = st.text_input("اسم المعتمد", key=f"ap_{qid}")
                why = st.text_input("سبب القرار", key=f"dr_{qid}")
                if st.button("💾 سجّل القرار", key=f"dd_{qid}", type="primary", use_container_width=True):
                    if not who.strip():
                        st.error("اكتب اسم المعتمد — كل قرار بيتسجّل باسم اللي وافق")
                    elif dec != "rejected" and (int(amt) <= 0 or not why.strip()):
                        st.error("الموافقة محتاجة مبلغ أكبر من صفر وسبب")
                    elif log(make_event("recovery_decision", qid, branch=r["branch"],
                                        meta={"decision": dec, "amount": 0 if dec == "rejected" else int(amt),
                                              "approver": who.strip(), "reason": why.strip()})):
                        st.rerun()
        st.markdown("### 📜 سجل القرارات")
        rows = [{"العرض": r["quote_id"], "القرار": r["recovery"]["decision"].get("decision", ""),
                 "الخصم": r["recovery"]["decision"].get("amount", 0),
                 "المعتمد": r["recovery"]["decision"].get("approver", ""),
                 "السبب": r["recovery"]["decision"].get("reason", ""), "الوقت": r["recovery"]["decision"]["ts"][:16]}
                for r in recs.values() if r["recovery"] and r["recovery"]["decision"]]
        rows.sort(key=lambda x: x["الوقت"], reverse=True)
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
