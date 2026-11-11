# pages/5_Customers.py
# ============================================================
#  👥 Customers CRM — تصنيف العملاء، VIP، متابعة VIP الشهرية، وسجل عروض الأسعار
#  التصنيف: New (مفيش زيارة) · Returning (زيارة) · Regular (زيارتين+) · VIP (يدوي من الإدارة
#  أو بقواعد قابلة للتعديل: زيارات/إنفاق خلال فترة). العملاء بالبصمة (من غير تخزين الرقم)؛
#  الاسم/الرقم موجودين بس لو store_contacts شغّال — من غيرهم متابعة VIP مش هتقدر تبعت.
#  الموظفين بيدخلوا (staff_password)، وتعديل الإعدادات والـ VIP اليدوي بكلمة سر الإدارة.
# ============================================================

from datetime import datetime, timedelta

import streamlit as st

import config_store
from access import admin_gate, require_access, secret_bool
from github_store import (GithubStoreError, events_path, read_events_range,
                          store_from_secrets)
from navigation import render_nav
from price_utils import build_whatsapp_url
from tracking import (CUSTOMER_LABELS, customers, make_event, month_key,
                      quote_records, stage_of, vip_followups)
from brand import LAB_NAME_AR
from marketing import share_url
from recall import RECALL_RULES, recall_due, recall_message

st.set_page_config(page_title="Orange Lab - Customers", page_icon="👥", layout="wide")
st.markdown("## 👥 Customers CRM")
render_nav(st, "pages/5_Customers.py")
require_access(st, "صفحة العملاء", level="staff")

store = store_from_secrets(st.secrets)
if not store:
    st.warning("تتبّع العروض مش متظبط (gh_events_token / gh_events_repo في Secrets).")
    st.stop()

store_contacts = secret_bool(st.secrets, "store_contacts")
now = datetime.now()


@st.cache_data(ttl=120, show_spinner=False)
def load_cfg():
    return config_store.load(store_from_secrets(st.secrets))


@st.cache_data(ttl=120, show_spinner=False)
def load_events():
    y, m = now.year, now.month - 11
    while m < 1:
        m += 12
        y -= 1
    return read_events_range(store_from_secrets(st.secrets), f"{y:04d}-{m:02d}", month_key(now))


try:
    events = load_events()
except GithubStoreError as e:
    st.error(f"مقدرتش أجيب البيانات: {e}")
    st.stop()

cfg = load_cfg()
custs = customers(events, cfg["vip"], now)
st.session_state.setdefault("staff_name", "")
STAFF = st.text_input("اسمك (بيتسجّل على كل إجراء)", key="staff_name")
if st.button("🔄 تحديث"):
    load_events.clear()
    load_cfg.clear()
    st.rerun()
if not store_contacts:
    st.info("أرقام العملاء مش بتتخزّن (الوضع الافتراضي). متابعة VIP محتاجة الاسم والرقم — "
            "فعّل `store_contacts = true` في Secrets **وريبو الأحداث Private**.")


def log(ev):
    try:
        store.append(events_path(month_key()), ev)
        load_events.clear()
        return True
    except GithubStoreError as e:
        st.error(f"مقدرتش أسجّل: {e}")
        return False


tab_c, tab_vip, tab_rc, tab_q, tab_set = st.tabs(["👥 Customers", "⭐ Monthly VIP Follow-Up", "🔁 Recall",
                                                   "🧾 Quotations", "⚙️ Settings"])

with tab_c:
    counts = {k: sum(1 for c in custs if c["label"] == k) for k in CUSTOMER_LABELS}
    cols = st.columns(4)
    for col, k in zip(cols, CUSTOMER_LABELS):
        col.metric(k, counts[k])
    pick = st.multiselect("التصنيف", list(CUSTOMER_LABELS), default=list(CUSTOMER_LABELS), key="cu_filter")
    term = st.text_input("بحث (اسم / رقم / بصمة)", key="cu_search").strip().lower()
    rows = [{"الاسم": c["name"] or "—", "الرقم": c["phone"] or "—", "التصنيف": c["label"],
             "زيارات": c["visits"], "إنفاق": c["spend"], "عروض": c["quotes"],
             "آخر زيارة": c["last_visit"][:10], "آخر تواصل": c["last_contact"][:10],
             "الفرع": c["last_branch"], "موقوف": "🚫" if c["optout"] else "", "بصمة": c["pk"]}
            for c in custs if c["label"] in pick
            and (not term or term in f"{c['name']} {c['phone']} {c['pk']}".lower())]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    with st.expander("⭐ تعيين / إلغاء VIP يدوي (للإدارة)"):
        if admin_gate(st, key="cu_admin_pw"):
            sel = st.selectbox("العميل", [c["pk"] for c in custs], key="cu_vip_pick",
                               format_func=lambda pk: next((f"{c['name'] or pk} — {c['label']}" for c in custs if c["pk"] == pk), pk)) if custs else None
            note = st.text_input("السبب", key="cu_vip_note")
            v1, v2 = st.columns(2)
            if sel and v1.button("⭐ اجعله VIP", key="cu_vip_on", use_container_width=True):
                if not STAFF.strip():
                    st.error("اكتب اسمك الأول")
                elif log(make_event("vip_set", "", phone_key=sel, staff=STAFF.strip(), meta={"vip": True, "note": note})):
                    st.rerun()
            if sel and v2.button("☆ شيل VIP", key="cu_vip_off", use_container_width=True):
                if not STAFF.strip():
                    st.error("اكتب اسمك الأول")
                elif log(make_event("vip_set", "", phone_key=sel, staff=STAFF.strip(), meta={"vip": False, "note": note})):
                    st.rerun()

VIP_MSG_EN = ("Dear Valued Customer,\n\nThank you for being part of the Orange Lab family.\n\n"
              "We truly appreciate your continued trust in our laboratory. Your health and satisfaction "
              "are always our priority.\n\nWe would be delighted to assist you with any upcoming laboratory "
              "tests or home sampling requests.\n\nThank you for choosing Orange Lab! 🧡")
VIP_MSG_AR = ("عزيزنا العميل المميز،\n\nشكراً لأنك جزء من عائلة أورانج لاب 🧡\n\n"
              "نقدّر ثقتك المستمرة في معملنا، وصحتك ورضاك دايماً أولويتنا.\n\n"
              "يسعدنا نخدمك في أي تحاليل جاية أو طلبات سحب منزلي.\n\nشكراً لاختيارك أورانج لاب!")

with tab_vip:
    month_label = now.strftime("%B %Y")
    vf = vip_followups(custs, now, int(cfg["vip"].get("cooldown_days", 30)))
    st.markdown(f"### ⭐ Monthly VIP Follow-Up — {month_label}")
    st.caption(f"مستحق: {len(vf['due'])} · اتكلّم قريب (مايتكررش قبل {cfg['vip'].get('cooldown_days', 30)} يوم): "
               f"{len(vf['recent'])} · VIP من غير رقم متخزّن: {len(vf['no_contact'])}")
    lang = st.radio("لغة الرسالة", ["en", "ar"], horizontal=True, key="vip_lang",
                    format_func=lambda k: {"en": "English", "ar": "العربية"}[k])
    base_msg = VIP_MSG_EN if lang == "en" else VIP_MSG_AR
    if not vf["due"]:
        st.success("مفيش VIP مستنيين متابعة الشهر ده 👌")
    for c in vf["due"]:
        with st.expander(f"⭐ {c['name'] or c['pk']} — {c['spend']:,} ج · {c['visits']} زيارة", expanded=len(vf["due"]) <= 3):
            st.caption(f"آخر زيارة: {c['last_visit'][:10] or '—'} · آخر عرض: {c['last_quote'][:10] or '—'} · "
                       f"آخر تواصل: {c['last_contact'][:10] or 'لسه'} · الفرع: {c['last_branch'] or '—'}")
            first = (c["name"] or "").split(" ")[0]
            text = st.text_area("الرسالة", base_msg if lang == "en" else base_msg, key=f"vm_{c['pk']}", height=170)
            greet = f"{'Dear ' + first + ',' if lang == 'en' else 'عزيزنا ' + first + '،'}\n\n" if first else ""
            st.link_button("📲 واتساب", build_whatsapp_url(c["phone"], greet + text if first else text),
                           use_container_width=True)
            res = st.selectbox("نتيجة التواصل", ["تم الرد", "مفيش رد", "طلب حجز", "طلب زيارة منزلية", "مش مهتم"],
                               key=f"vr_{c['pk']}")
            if st.button("✅ سجّل إنه اتكلّم", key=f"vc_{c['pk']}", type="primary", use_container_width=True):
                if log(make_event("vip_contact", "", phone_key=c["pk"], staff=STAFF.strip(), meta={"result": res, "by": STAFF.strip()})):
                    st.rerun()
    with st.expander(f"🕒 اتكلّموا قريب ({len(vf['recent'])})"):
        for c in vf["recent"]:
            st.write(f"• {c['name'] or c['pk']} — {c['last_contact'][:10]} · {c['last_contact_result']}")
    if vf["no_contact"]:
        with st.expander(f"⚠️ VIP من غير بيانات تواصل ({len(vf['no_contact'])})"):
            st.caption("اتحسبوا VIP بس الاسم/الرقم مش متخزّن (store_contacts كان مقفول وقت الإرسال).")
            for c in vf["no_contact"]:
                st.write(f"• {c['pk']} — {c['spend']:,} ج · {c['visits']} زيارة")

with tab_rc:
    st.markdown("### 🔁 تذكير التحاليل الدورية")
    st.caption("عملاء حضروا وعملوا تحليل بيتعاد دورياً (سكر تراكمي، فيتامين د، دهون، غدة…) وميعاده قرّب أو عدّى — "
               "ومارجعوش عملوه. الرسالة بتقول «لو الدكتور طالب متابعة دورية» ومابتقولش للعميل يعمل تحليل. "
               "الفترات من recall.py (راجعها طبياً).")
    rc = recall_due(events, now=now)
    st.caption(" · ".join(f"{r['label']}: كل {r['days']} يوم" for r in RECALL_RULES))
    m1, m2 = st.columns(2)
    m1.metric("مستحقين تذكير", len(rc))
    m2.metric("عندهم رقم متخزّن", sum(1 for x in rc if (x["contact"] or {}).get("phone")))
    if not rc:
        st.success("مفيش تذكيرات مستحقة دلوقتي 👌")
    for x in rc:
        c = x["contact"] or {}
        months = max(1, round(x["days"] / 30))
        with st.expander(f"🔁 {c.get('name') or x['pk']} — {x['label']} · آخر زيارة {x['last_visit'][:10]}"
                         + (f" · متأخر {x['overdue_days']} يوم" if x["overdue_days"] else " · قرّب")):
            binfo = cfg["branches"].get(x["branch"])
            msg = recall_message(lab=LAB_NAME_AR, name=c.get("name", ""), label=x["label"], months=months,
                                 branch_text=config_store.branch_block(binfo, compact=True) if binfo else "")
            msg = st.text_area("الرسالة", msg, key=f"rcm_{x['pk']}_{x['rule']}", height=150)
            if c.get("phone"):
                st.link_button("📲 واتساب", build_whatsapp_url(c["phone"], msg), use_container_width=True)
            else:
                st.link_button("📲 واتساب (اختار جهة الاتصال — الرقم مش متخزّن)", share_url(msg), use_container_width=True)
            res = st.selectbox("النتيجة", ["اتبعت", "حجز", "مش محتاج دلوقتي", "مفيش رد"], key=f"rcr_{x['pk']}_{x['rule']}")
            if st.button("✅ سجّل التذكير (مايتكررش 30 يوم)", key=f"rcl_{x['pk']}_{x['rule']}",
                         type="primary", use_container_width=True):
                if log(make_event("recall_contact", x["quote_id"], branch=x["branch"], phone_key=x["pk"],
                                  staff=STAFF.strip(), meta={"rule": x["rule"], "result": res})):
                    st.rerun()

with tab_q:
    recs = [r for r in quote_records(events).values() if r["quote_ts"]]
    stages = ["new", "sent", "booked", "visited", "lost"]
    pick_s = st.multiselect("المرحلة", stages, default=stages, key="qh_stage")
    rows = sorted(({"العرض": r["quote_id"], "التاريخ": r["quote_ts"][:16], "الفرع": r["branch"],
                    "الموظف": r["staff"], "الإجمالي": r["total"], "الخصم": r["discount"],
                    "المرحلة": stage_of(r), "نوع الزيارة": r["visit_type"], "المنطقة": r["area"],
                    "حملة": r["campaign_id"], "مزايا": ", ".join(r["benefits"]),
                    "مرتبط بـ": r["parent"], "هدية": (r["gift"] or {}).get("gift_type", "")}
                   for r in recs if stage_of(r) in pick_s), key=lambda x: x["التاريخ"], reverse=True)
    st.dataframe(rows, use_container_width=True, hide_index=True)

with tab_set:
    if admin_gate(st, key="cu_set_pw"):
        who = st.text_input("اسمك (كل تعديل بيتسجّل باسمك)", key="set_who")
        st.markdown("#### ⭐ قواعد VIP")
        v = cfg["vip"]
        c1, c2 = st.columns(2)
        mv = c1.number_input("عدد الزيارات", min_value=1, value=int(v["min_visits"]), key="vip_mv")
        ms = c2.number_input("أو إجمالي الإنفاق (ج)", min_value=0, step=500, value=int(v["min_spend"]), key="vip_ms")
        wd = c1.number_input("خلال (يوم)", min_value=30, value=int(v["window_days"]), key="vip_wd")
        cd = c2.number_input("مدة بين رسائل المتابعة (يوم)", min_value=1, value=int(v.get("cooldown_days", 30)), key="vip_cd")
        gifts_txt = st.text_area("🎀 الهدايا (سطر لكل هدية: الاسم | التكلفة)",
                                 "\n".join(f"{g['name']} | {g.get('cost', 0)}" for g in cfg["gifts"]), key="set_gifts", height=90)
        staff_txt = st.text_area("👤 الموظفين (سطر لكل اسم)", "\n".join(cfg["staff"]), key="set_staff", height=90)
        areas_txt = st.text_area("🗺️ مناطق العملاء (سطر لكل منطقة)", "\n".join(cfg["areas"]), key="set_areas", height=90)
        if st.button("💾 احفظ الإعدادات", type="primary", key="set_save", use_container_width=True):
            try:
                gifts = []
                for ln in gifts_txt.splitlines():
                    if ln.strip():
                        nm, _, cost = ln.partition("|")
                        gifts.append({"id": nm.strip().lower().replace(" ", "_"), "name": nm.strip(),
                                      "cost": int("".join(ch for ch in cost if ch.isdigit()) or 0)})
                config_store.save_section(store, "vip", {"min_visits": int(mv), "min_spend": int(ms),
                                                          "window_days": int(wd), "cooldown_days": int(cd)}, who=who)
                config_store.save_section(store, "gifts", gifts or cfg["gifts"], who=who)
                config_store.save_section(store, "staff", [s.strip() for s in staff_txt.splitlines() if s.strip()], who=who)
                config_store.save_section(store, "areas", [s.strip() for s in areas_txt.splitlines() if s.strip()] or cfg["areas"], who=who)
                load_cfg.clear()
                st.success("اتحفظ ✅")
            except ValueError as e:
                st.error(str(e))
            except GithubStoreError as e:
                st.error(f"مقدرتش أحفظ: {e}")
