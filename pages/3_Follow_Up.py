# pages/3_Follow_Up.py
# ============================================================
#  📞 متابعة النهاردة — عروض اتبعتت ولسه من غير قرار
#  الأحداث: sent (تأكيد الإرسال من صفحة الفاتورة) ← followup / converted /
#  lost_sale / optout من هنا. كلمة سر الإدارة (access_password) لو متظبطة.
# ============================================================

from datetime import datetime, timedelta

import streamlit as st

from navigation import render_nav

from access import require_access, secret_bool
from brand import LAB_NAME_AR
from github_store import (GithubStoreError, events_path, read_events_range,
                          store_from_secrets)
from marketing import build_followup_message, share_url
from price_utils import build_whatsapp_url
from tracking import (LOST_SALE_REASONS, followup_queue, make_event, month_key,
                      optout_keys)

st.set_page_config(page_title="Orange Lab - متابعة", page_icon="📞", layout="wide")
st.markdown("## 📞 متابعة النهاردة")
render_nav(st, "pages/3_Follow_Up.py")
require_access(st, "صفحة المتابعة")

store = store_from_secrets(st.secrets)
if not store:
    st.warning("تتبّع العروض مش متظبط (gh_events_token / gh_events_repo في Secrets).")
    st.stop()

store_contacts = secret_bool(st.secrets, "store_contacts")


def _prev_month(d: datetime) -> str:
    y, m = d.year, d.month - 1
    if m < 1:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


@st.cache_data(ttl=60, show_spinner=False)
def load_events(start_m: str, end_m: str):
    s = store_from_secrets(st.secrets)
    return read_events_range(s, start_m, end_m)


now = datetime.now()
try:
    events = load_events(_prev_month(now), month_key(now))
except GithubStoreError as e:
    st.error(f"مقدرتش أجيب البيانات: {e}")
    st.stop()

q = followup_queue(events, now)
m1, m2, m3, m4 = st.columns(4)
m1.metric("⏰ مستحقة دلوقتي", len(q["due"]))
m2.metric("🕒 جاية", len(q["upcoming"]))
m3.metric("⛔ خلّصت محاولاتها", len(q["exhausted"]))
m4.metric("💤 قديمة", len(q["stale"]))
if st.button("🔄 تحديث"):
    load_events.clear()
    st.rerun()
if not store_contacts:
    st.info("أرقام العملاء مش بتتخزّن (الوضع الافتراضي لحماية الخصوصية). القايمة بتظهر العروض "
            "بالتفاصيل من غير اسم/رقم — لتفعيل التخزين ضيف `store_contacts = true` في Secrets "
            "**وتأكد إن ريبو الأحداث Private**.")


def log(ev: dict):
    try:
        store.append(events_path(month_key()), ev)
        load_events.clear()
        return True
    except GithubStoreError as e:
        st.error(f"مقدرتش أسجّل: {e}")
        return False


def card(r: dict, due: bool):
    c = r.get("contact") or {}
    title = f"{r['quote_id']} · {r['total']:,} ج.م · {r['branch'] or '—'}"
    if c.get("name"):
        title += f" · {c['name']}"
    with st.expander(("🔴 " if due else "🕒 ") + title, expanded=due and len(q["due"]) <= 3):
        age = f"{r['age_days']:.1f} يوم"
        st.caption(f"اتبعت من {age} · محاولات المتابعة: {r['attempts']}"
                   + (f" · حملة: {r['campaign_id']}" if r["campaign_id"] else "")
                   + (f" · ميعادها: {r['due_at']:%d-%m %H:%M}"))
        if r["items"]:
            st.write("🧪 " + "، ".join(r["items"]))
        msg = build_followup_message(lab=LAB_NAME_AR, name=(c.get("name") or "").split(" ")[0],
                                     items=r["items"], total=r["total"], attempt=r["attempts"])
        msg = st.text_area("نص الرسالة", msg, key=f"m_{r['quote_id']}", height=120)
        phone = (c.get("phone") or "").strip()
        st.link_button("📲 افتح واتساب" if phone else "📲 واتساب (اختار جهة الاتصال)",
                       build_whatsapp_url(phone, msg) if phone else share_url(msg),
                       use_container_width=True)
        a1, a2, a3 = st.columns(3)
        if a1.button("✔ اتواصلت — بكرة", key=f"f1_{r['quote_id']}", use_container_width=True):
            if log(make_event("followup", r["quote_id"], branch=r["branch"],
                              meta={"next_due": (now + timedelta(hours=24)).isoformat(timespec="seconds")})):
                st.rerun()
        if a2.button("⏰ بعد 3 أيام", key=f"f3_{r['quote_id']}", use_container_width=True):
            if log(make_event("followup", r["quote_id"], branch=r["branch"],
                              meta={"next_due": (now + timedelta(days=3)).isoformat(timespec="seconds")})):
                st.rerun()
        if a3.button("🚫 مايتبعتلوش تاني", key=f"oo_{r['quote_id']}", use_container_width=True):
            if log(make_event("optout", r["quote_id"], branch=r["branch"], phone_key=r.get("pk", ""))):
                st.rerun()
        b1, b2 = st.columns(2)
        if b1.button("✅ اتباع / حجز", key=f"cv_{r['quote_id']}", use_container_width=True, type="primary"):
            if log(make_event("converted", r["quote_id"], branch=r["branch"], total=r["total"])):
                st.rerun()
        reason = b2.selectbox("سبب الفوات", LOST_SALE_REASONS, key=f"rs_{r['quote_id']}",
                              label_visibility="collapsed")
        if b2.button("❌ فاتت", key=f"ls_{r['quote_id']}", use_container_width=True):
            if log(make_event("lost_sale", r["quote_id"], branch=r["branch"], reason=reason,
                              total=r["total"])):
                st.rerun()


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
st.caption(f"عدد الموبايلات الموقوفة (opt-out): {len(optout_keys(events))}")
