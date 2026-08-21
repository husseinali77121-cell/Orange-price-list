# pages/1_Dashboard.py
# ============================================================
#  📊 Marketing Dashboard — فاز 3
#  بيقرا أحداث quote/converted/lost_sale اللي فاز 2 بيسجّلها،
#  ويلخّصها. مفيهوش أي كتابة — قراءة بس.
# ============================================================

from datetime import date

import pandas as pd
import streamlit as st

from bundles import BUNDLES as BUNDLE_DEFS
from bundles import BUNDLE_CATEGORY
from github_store import GithubStoreError, read_events_range, store_from_secrets
from labs_price_list import LABS_DB
from panels import BRANCHES
from price_utils import build_index
from tracking import month_key, summarize_events

st.set_page_config(page_title="Orange Lab - Dashboard", page_icon="📊", layout="wide")


@st.cache_resource(show_spinner=False)
def load_index():
    return build_index(LABS_DB, BUNDLE_DEFS, BUNDLE_CATEGORY)


IDX = load_index()
BUNDLE_NAMES = {b.name for b in IDX.bundles}

st.markdown("## 📊 Marketing Dashboard")
st.caption("قراءة بس — من غير ما يأثّر على شغل صفحة الفاتورة")

store = store_from_secrets(st.secrets)
if not store:
    st.warning(
        "⚠️ تتبّع العروض مش متظبط. ضيف في Streamlit Secrets:\n\n"
        "```\ngh_events_token = \"ghp_...\"\n"
        "gh_events_repo  = \"username/repo-name\"\n"
        "gh_events_branch = \"main\"\n```"
    )
    st.stop()


# ------------------------------------------------------------
# فلاتر: الفترة + الفرع
# ------------------------------------------------------------

f1, f2, f3 = st.columns([1, 1, 1])
with f1:
    preset = st.selectbox("الفترة", ["الشهر ده", "آخر 3 شهور", "آخر 6 شهور", "مخصّص"])

today = date.today()


def _shift_month(d: date, back: int) -> date:
    y, m = d.year, d.month - back
    while m < 1:
        m += 12
        y -= 1
    return date(y, m, 1)


if preset == "الشهر ده":
    start_m = end_m = month_key()
elif preset == "آخر 3 شهور":
    start_m, end_m = month_key(_shift_month(today, 2)), month_key()
elif preset == "آخر 6 شهور":
    start_m, end_m = month_key(_shift_month(today, 5)), month_key()
else:
    with f2:
        c_start = st.date_input("من شهر", value=_shift_month(today, 2))
    with f3:
        c_end = st.date_input("لغاية شهر", value=today)
    start_m, end_m = month_key(c_start), month_key(c_end)

if preset != "مخصّص":
    with f2:
        branch_filter = st.selectbox("الفرع", ["الكل"] + list(BRANCHES))
else:
    branch_filter = st.selectbox("الفرع", ["الكل"] + list(BRANCHES))

try:
    events = read_events_range(store, start_m, end_m)
except GithubStoreError as e:
    st.error(f"مقدرتش أجيب البيانات من GitHub: {e}")
    st.stop()

if branch_filter != "الكل":
    events = [e for e in events if e.get("branch") == branch_filter]

if not events:
    st.info(f"مفيش أي بيانات مسجّلة من {start_m} لغاية {end_m} "
           f"{'' if branch_filter == 'الكل' else f'(فرع {branch_filter})'}")
    st.stop()

s = summarize_events(events, bundle_names=BUNDLE_NAMES)

st.divider()


# ------------------------------------------------------------
# KPIs
# ------------------------------------------------------------

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("عروض", s["quotes"])
k2.metric("اتباعت", s["converted"])
k3.metric("فاتت", s["lost"])
k4.metric("لسه معلّقة", s["pending"])
k5.metric("نسبة التحويل", f"{s['conversion_pct']}%")

r1, r2 = st.columns(2)
r1.metric("💰 إيراد اتحقق (Converted)", f"{s['revenue_converted']:,} ج.م")
r2.metric("💸 إيراد ضايع (Lost)", f"{s['revenue_lost']:,} ج.م")

st.divider()


# ------------------------------------------------------------
# أكتر التحاليل/الباقات طلباً
# ------------------------------------------------------------

c_left, c_right = st.columns(2)

with c_left:
    st.markdown("#### 🔬 أكتر التحاليل والباقات طلباً")
    if s["top_tests"]:
        df = pd.DataFrame(s["top_tests"][:12], columns=["الاسم", "عدد الفواتير"])
        df = df.set_index("الاسم")
        st.bar_chart(df)
    else:
        st.caption("مفيش بيانات كفاية لسه")

with c_right:
    st.markdown("#### 📣 أكتر مصادر العملاء")
    if s["top_sources"]:
        df = pd.DataFrame(s["top_sources"], columns=["المصدر", "عدد العروض"])
        df = df.set_index("المصدر")
        st.bar_chart(df)
    else:
        st.caption("مفيش بيانات كفاية لسه")

st.divider()


# ------------------------------------------------------------
# نسبة تحويل كل باقة (Package A: 214/318 = 67%)
# ------------------------------------------------------------

st.markdown("#### 📦 نسبة تحويل كل باقة")
if s["package_stats"]:
    rows = []
    for name, ps in sorted(s["package_stats"].items(),
                           key=lambda x: -x[1]["conversion_pct"]):
        rows.append({
            "الباقة": name,
            "عروض": ps["quotes"],
            "اتباعت": ps["converted"],
            "فاتت": ps["lost"],
            "نسبة التحويل": f"{ps['conversion_pct']}%",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("ملحوظة: النسبة محسوبة من العروض اللي اتحدد مصيرها (اتباعت أو فاتت) بس — "
              "مش شاملة اللي لسه معلّقة")
else:
    st.caption("لسه مفيش باقة كفاية بيانات — هتظهر هنا أول ما تتباع أو تتفوّت باقات")

st.divider()


# ------------------------------------------------------------
# أسباب الفوات
# ------------------------------------------------------------

st.markdown("#### ❌ أسباب فوات العملاء")
if s["top_lost_reasons"]:
    total_lost = sum(c for _, c in s["top_lost_reasons"])
    for reason, count in s["top_lost_reasons"]:
        pct = round(100 * count / total_lost) if total_lost else 0
        st.write(f"**{reason}** — {count} ({pct}%)")
        st.progress(pct / 100)
else:
    st.caption("مفيش عروض اتسجّلت كـ 'فايتة' في الفترة دي")

st.caption(f"({len(events)} حدث مسجّل من {start_m} لغاية {end_m})")
