# pages/9_Check_In.py
# ============================================================
#  ✅ Check-in (الاستقبال) — العميل وصل المعمل؟ اكتب رقمه أو كود العرض اللي في رسالته
#  (OR-…) ← عروضه المفتوحة ← «✅ حضر» بالمبلغ المدفوع فعلاً. ده اللي بيقفل الدايرة:
#  استفسار واتساب ← عرض سعر ← متابعة ← حجز ← **حضور فعلي** (Visit Rate في الداشبورد).
#  • مواعيد النهاردة + حجوزات عدّت ومحدّش أكّدها.
#  • بعد الحضور: رسالة شكر + طلب تقييم بضغطة (الرقم مكتوب قدامك، من غير تخزين).
#  البحث بالرقم بيستخدم بصمة HMAC (quote_secret) — الرقم نفسه مش بيتخزّن.
# ============================================================

from datetime import date, datetime, timedelta

import streamlit as st

import config_store
import replies as RP
from access import require_access, secret_str
from brand import LAB_NAME_AR
from github_store import (GithubStoreError, events_path, read_events_range,
                          store_from_secrets)
from marketing import share_url
from navigation import render_nav
from price_utils import format_phone_display, validate_phone
from tracking import (LOST_SALE_REASONS, appointments, make_event, month_key,
                      open_quotes_for, phone_key, stage_of)

st.set_page_config(page_title="Orange Lab - Check-in", page_icon="✅", layout="wide")
st.markdown("## ✅ Check-in — العميل وصل؟")
render_nav(st, "pages/9_Check_In.py")
require_access(st, "صفحة الاستقبال", level="staff")

store = store_from_secrets(st.secrets)
if not store:
    st.warning("تتبّع العروض مش متظبط (gh_events_token / gh_events_repo في Secrets).")
    st.stop()

QUOTE_SECRET = secret_str(st.secrets, "quote_secret")
now = datetime.now()


def _prev_month(d: datetime, back: int = 1) -> str:
    y, m = d.year, d.month - back
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"


@st.cache_data(ttl=60, show_spinner=False)
def load_events(start_m: str, end_m: str):
    return read_events_range(store_from_secrets(st.secrets), start_m, end_m)


@st.cache_data(ttl=120, show_spinner=False)
def load_cfg():
    return config_store.load(store_from_secrets(st.secrets))


try:
    events = load_events(_prev_month(now), month_key(now))
except GithubStoreError as e:
    st.error(f"مقدرتش أجيب البيانات: {e}")
    st.stop()

CFG = load_cfg()
LINKS = config_store.resolve_links(CFG, st.secrets)
st.session_state.setdefault("staff_name", "")
STAFF = st.text_input("اسمك (بيتسجّل على كل إجراء)", key="staff_name")


def log(ev: dict) -> bool:
    try:
        store.append(events_path(month_key()), ev)
        load_events.clear()
        return True
    except GithubStoreError as e:
        st.error(f"مقدرتش أسجّل: {e}")
        return False


def _label(r: dict) -> str:
    c = r.get("contact") or {}
    when = (r["appointment"] or r["sent_ts"] or r["quote_ts"])[:16].replace("T", " ")
    return (f"{r['quote_id']} · {r['total']:,} ج · {r['branch'] or '—'} · {when}"
            + (f" · {c['name']}" if c.get("name") else "")
            + (" · 🏠" if r["visit_type"] == "home" else ""))


def visit_controls(r: dict, key: str, phone_e164: str = ""):
    """«✅ حضر» بالمبلغ الفعلي + «❌ ماحضرش». بعد الحضور: رسالة شكر/تقييم لو الرقم معروف."""
    qid = r["quote_id"]
    st.caption(("🧪 " + "، ".join(r["items"])) if r["items"] else "—")
    meta = []
    if r["campaign_id"]:
        meta.append(f"🎯 حملة {r['campaign_id']}")
    if r["source"]:
        meta.append(f"📣 {r['source']}")
    if r["staff"]:
        meta.append(f"👤 {r['staff']}")
    if r["appointment"]:
        meta.append("📅 " + r["appointment"][:16].replace("T", " "))
    if meta:
        st.caption(" · ".join(meta))
    c1, c2 = st.columns([1, 1])
    paid = c1.number_input("المدفوع فعلاً (ج)", min_value=0, step=10, value=int(r["total"] or 0),
                           key=f"{key}_paid_{qid}", help="لو العميل زوّد/شال تحاليل في المعمل")
    if c2.button("✅ حضر", key=f"{key}_in_{qid}", type="primary", use_container_width=True):
        if log(make_event("converted", qid, branch=r["branch"], total=int(paid), staff=STAFF.strip(),
                          meta={"via": "checkin", "paid": int(paid), "quoted": int(r["total"] or 0)})):
            st.session_state[f"_ci_done_{qid}"] = phone_e164 or ((r.get("contact") or {}).get("phone") or "")
            st.rerun()
    with st.expander("❌ ماحضرش / اتلغى"):
        reason = st.selectbox("السبب", LOST_SALE_REASONS, key=f"{key}_rs_{qid}")
        if st.button("سجّل «ماحضرش»", key=f"{key}_no_{qid}", use_container_width=True):
            if log(make_event("lost_sale", qid, branch=r["branch"], reason=reason, total=int(r["total"] or 0),
                              staff=STAFF.strip(), meta={"via": "checkin"})):
                st.rerun()


# ---------------- بعد تسجيل الحضور: شكر + تقييم ----------------
for k in [k for k in list(st.session_state.keys()) if str(k).startswith("_ci_done_")]:
    qid, ph = str(k)[len("_ci_done_"):], st.session_state[k]
    st.success(f"✅ اتسجّل حضور {qid}")
    msg = RP.render_reply(RP.get("thanks"), "short", lab=LAB_NAME_AR, review_url=LINKS["review_url"])
    if ph:
        st.link_button("⭐ ابعت شكر + طلب تقييم على الواتساب", share_url(msg, ph), use_container_width=True)
    if not LINKS["review_url"]:
        st.caption("ضيف لينك تقييم Google من Branches ← Links عشان يتحط في الرسالة.")
    if st.button("تمام", key=f"ok_{qid}"):
        del st.session_state[k]
        st.rerun()

# ---------------- 🔎 العميل وصل ----------------
st.markdown("### 🔎 العميل وصل — دوّر برقمه أو بكود العرض")
s1, s2 = st.columns([2, 1])
raw = s1.text_input("رقم الموبايل أو كود العرض", key="ci_q", placeholder="01012345678  أو  OR-261111-0042")
q = (raw or "").strip()
pv = validate_phone(q) if q and not q.upper().startswith(("OR-", "RC-")) else None
pk = phone_key(pv.value, QUOTE_SECRET) if (pv and pv.ok and QUOTE_SECRET) else ""
if q:
    if pv is not None and not pv.ok:
        st.error("الرقم مش صالح — اكتبه 01XXXXXXXXX أو اكتب كود العرض")
    elif pv is not None and not QUOTE_SECRET:
        st.warning("البحث بالرقم محتاج quote_secret في Secrets — دوّر بكود العرض اللي في رسالة العميل.")
    found = open_quotes_for(events, pk=pk, code="" if pv is not None else q, now=now)
    if found:
        st.caption(f"{len(found)} عرض مفتوح" + (f" لـ {format_phone_display(pv.value)}" if pv and pv.ok else ""))
        for r in found:
            with st.expander(("📅 " if stage_of(r) == "booked" else "🧾 ") + _label(r), expanded=len(found) == 1):
                visit_controls(r, "s", pv.value if (pv and pv.ok) else "")
    elif pv is None or pv.ok:
        st.info("مفيش عرض مفتوح للرقم/الكود ده آخر 45 يوم — عميل جديد؟ اعمله فاتورة من صفحة Invoice.")

st.divider()

# ---------------- 📅 مواعيد النهاردة ----------------
ap = appointments(events, date.today())
m1, m2 = st.columns(2)
m1.metric("📅 مواعيد النهاردة", len(ap["today"]))
m2.metric("⏰ مواعيد عدّت من غير تأكيد", len(ap["overdue"]))
if st.button("🔄 تحديث"):
    load_events.clear()
    st.rerun()

st.markdown("### 📅 مواعيد النهاردة")
if not ap["today"]:
    st.caption("مفيش حجوزات النهاردة 👌")
for r in ap["today"]:
    with st.expander("📅 " + r["appointment"][11:16] + " · " + _label(r)):
        visit_controls(r, "t")
        c = r.get("contact") or {}
        if c.get("phone"):
            rem = RP.render_reply(RP.get("appt_reminder"), "short", name=c.get("name", ""), lab=LAB_NAME_AR,
                                  appt_text=RP.appt_line(r["appointment"]),
                                  branch_text=config_store.branch_block(CFG["branches"][r["branch"]], compact=True)
                                  if r["branch"] in CFG["branches"] else "")
            st.link_button("📲 تذكير بالميعاد", share_url(rem, c["phone"]), use_container_width=True)

with st.expander(f"⏰ مواعيد عدّت ومحدّش سجّل حضر/ماحضرش ({len(ap['overdue'])})"):
    for r in ap["overdue"]:
        st.markdown("**" + _label(r) + "**")
        visit_controls(r, "o")
        st.divider()
