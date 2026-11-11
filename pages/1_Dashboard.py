# pages/1_Dashboard.py
# ============================================================
#  📊 Marketing Dashboard — فاز 3
#  بيقرا أحداث quote/converted/lost_sale اللي فاز 2 بيسجّلها،
#  ويلخّصها. مفيهوش أي كتابة — قراءة بس.
# ============================================================

from datetime import date

import pandas as pd
import streamlit as st

from navigation import render_nav

from bundles import BUNDLES as BUNDLE_DEFS
from bundles import BUNDLE_CATEGORY
from github_store import GithubStoreError, read_events_range, store_from_secrets
from labs_price_list import LABS_DB
from panels import BRANCHES
from access import require_access
from price_utils import build_index
import config_store
import replies as RP
from tracking import (crm_kpis, marketing_kpis, month_key, objection_stats, quote_records,
                      summarize_events, whatsapp_funnel)

st.set_page_config(page_title="Orange Lab - Dashboard", page_icon="📊", layout="wide")


@st.cache_resource(show_spinner=False)
def load_index():
    return build_index(LABS_DB, BUNDLE_DEFS, BUNDLE_CATEGORY)


IDX = load_index()
BUNDLE_NAMES = {b.name for b in IDX.bundles}

st.markdown("## 📊 Marketing Dashboard")
render_nav(st, "pages/1_Dashboard.py")
st.caption("قراءة بس — من غير ما يأثّر على شغل صفحة الفاتورة")
require_access(st, "لوحة المبيعات (أرقام الإيراد ومصادر العملاء)")

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
kp = marketing_kpis(events)

st.divider()


# ------------------------------------------------------------
# KPIs
# ------------------------------------------------------------

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("عروض اتجهّزت", s["quotes"])
k2.metric("اتبعتت فعلاً", kp["sent"], help="الموظف أكّد الإرسال بزرار «تم الإرسال»")
k3.metric("اتباعت / اتحجزت", s["converted"])
k4.metric("فاتت", s["lost"])
k5.metric("لسه معلّقة", s["pending"])
k6.metric("نسبة التحويل", f"{s['conversion_pct']}%")

r1, r2 = st.columns(2)
r1.metric("💰 قيمة العروض المؤكَّد حجزها", f"{s['revenue_converted']:,} ج.م",
          help="قيمة العروض اللي اتسجّلت «اتباع / حجز» — مش بالضرورة المبلغ المحصّل فعلاً")
r2.metric("📉 قيمة فرص البيع المفقودة", f"{s['revenue_lost']:,} ج.م",
          help="قيمة العروض اللي فاتت — فرصة ضاعت مش إيراد محقّق")

a1, a2, a3, a4 = st.columns(4)
a1.metric("متوسط قيمة العرض", f"{kp['avg_quote_value']:,} ج.م")
a2.metric("متوسط الخصم", f"{kp['avg_discount_pct']}%",
          help="العروض القديمة قبل تسجيل الخصم بتتحسب من غير خصم")
a3.metric("عملاء متكررين", f"{kp['repeat_pct']}%",
          help=f"{kp['returning_customers']} من {kp['customers']} عميل (بالبصمة — من غير تخزين الأرقام)")
a4.metric("متوسط الوقت للحجز",
          f"{kp['avg_hours_to_convert']} ساعة" if kp["avg_hours_to_convert"] is not None else "—")
if kp["prepared_not_sent"]:
    st.caption(f"ℹ️ {kp['prepared_not_sent']} عرض اتجهّز ومحدّش أكّد إنه اتبعت — "
               "دول مش داخلين في «اتبعتت فعلاً».")

st.divider()

# ------------------------------------------------------------
# 💬 عملاء الواتساب: استفسار ← عرض ← اتبعت ← حجز ← حضر + سرعة الرد
# ------------------------------------------------------------
wf = whatsapp_funnel(events)
st.markdown("#### 💬 عملاء الواتساب — من السؤال للحضور")
if wf["leads"] or wf["quotes"]:
    w1, w2, w3, w4, w5, w6 = st.columns(6)
    w1.metric("🟡 استفسارات من غير عرض", wf["leads"], help="اتسجّلوا «مستفسر» ولسه مابعتوش الروشتة")
    w2.metric("🧾 عروض سعر", wf["quotes"])
    w3.metric("📲 اتبعتت", wf["sent"])
    w4.metric("📅 حجزوا", wf["booked"])
    w5.metric("✅ حضروا", wf["visited"])
    w6.metric("Visit Rate", f"{wf['visit_rate_pct']}%", help="حضروا ÷ اتبعتلهم العرض")
    x1, x2, x3 = st.columns(3)
    x1.metric("من مستفسر لعرض سعر", f"{wf['quote_rate_pct']}%", help=f"{wf['leads_quoted']} من {wf['leads']}")
    x2.metric("قيمة اللي حضروا", f"{wf['value_visited']:,} ج.م")
    x3.metric("سرعة الرد (الوسيط)",
              f"{wf['median_response_min']:.0f} دقيقة" if wf["median_response_min"] is not None else "—",
              help="من وقت رسالة العميل (من المحادثة الملزوقة) لحد «إرسال + متابعة»")
    if wf["by_response"]:
        st.dataframe(pd.DataFrame([{"سرعة الرد": b["bucket"], "اتبعتت": b["sent"], "حضروا": b["visited"],
                                    "Visit Rate %": b["rate"]} for b in wf["by_response"]]),
                     use_container_width=True, hide_index=True)
        st.caption("لو الـ Visit Rate بيقل كل ما الرد يتأخر — ده رقمك اللي يقنع الفريق يرد أسرع.")
else:
    st.caption("لسه مفيش عروض مصدرها واتساب. لما تلزق محادثة العميل في «💬 استفسار واتساب» بالفاتورة، "
               "المصدر ووقت الرسالة بيتسجّلوا لوحدهم.")

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

st.divider()

# ------------------------------------------------------------
# مقارنة الفروع
# ------------------------------------------------------------

st.markdown("#### 🏢 مقارنة الفروع")
if kp["by_branch"]:
    st.dataframe(pd.DataFrame([
        {"الفرع": b, "عروض": v["quotes"], "اتبعتت": v["sent"], "اتباعت": v["converted"],
         "فاتت": v["lost"], "نسبة التحويل": f"{v['conversion_pct']}%",
         "قيمة مؤكَّدة": v["revenue"], "قيمة مفقودة": v["lost_value"]}
        for b, v in sorted(kp["by_branch"].items())]),
        use_container_width=True, hide_index=True)
else:
    st.caption("مفيش بيانات فروع كفاية")

st.divider()

# ------------------------------------------------------------
# أداء الحملات + تكلفة اكتساب العميل (CAC)
# ------------------------------------------------------------

st.markdown("#### 🎯 أداء الحملات")
camp = kp["campaign_stats"]
if camp:
    base = pd.DataFrame([
        {"كود الحملة": cid, "عروض": v["quotes"], "اتباعت": v["converted"], "فاتت": v["lost"],
         "نسبة التحويل %": v["conversion_pct"], "قيمة مؤكَّدة": v["revenue"], "تكلفة الإعلان (ج.م)": 0}
        for cid, v in sorted(camp.items(), key=lambda x: -x[1]["revenue"])])
    edited = st.data_editor(base, use_container_width=True, hide_index=True,
                            disabled=[c for c in base.columns if c != "تكلفة الإعلان (ج.م)"],
                            key="camp_editor")
    spend = edited[edited["تكلفة الإعلان (ج.م)"] > 0]
    if len(spend):
        spend = spend.assign(**{"CAC (ج.م)": (spend["تكلفة الإعلان (ج.م)"] /
                                              spend["اتباعت"].where(spend["اتباعت"] > 0)).round()})
        st.dataframe(spend[["كود الحملة", "تكلفة الإعلان (ج.م)", "اتباعت", "CAC (ج.م)"]],
                     use_container_width=True, hide_index=True)
    st.caption("الحملة بتتربط بالعرض لما الموظف يكتب كود الحملة في صفحة الفاتورة. "
               "التكلفة بتدخلها بإيدك هنا (مش بتتخزّن). مشاهدات ونقرات فيسبوك/جوجل "
               "مش في البيانات دي — محتاجة تكامل مع المنصات.")
else:
    st.caption("لسه مفيش عروض مربوطة بكود حملة. حمّل تصميم من Marketing Studio، "
               "وخلّي الموظف يكتب الكود في صفحة الفاتورة.")

st.divider()

# ------------------------------------------------------------
# 🧡 دورة العميل (CRM): من عرض السعر للحضور الفعلي
# ------------------------------------------------------------

_cfg = config_store.load(store)
_fhv = {c["id"] for c in _cfg["campaigns"] if c.get("type") == "free_home_visit"}
ck = crm_kpis(events, _fhv, _cfg["vip"])
st.markdown("#### 🧡 Customer Journey — نجاح البرنامج = عملاء حضروا مش رسائل اتبعتت")
j1, j2, j3, j4 = st.columns(4)
j1.metric("Total Quotes", ck["total_quotes"])
j2.metric("Total Quoted Value", f"{ck['quoted_value']:,} ج")
j3.metric("Visit Rate", f"{ck['visit_rate_pct']}%", help="حضروا ÷ اتبعتلهم العرض فعلاً")
j4.metric("Booked (جاي)", ck["booked"])
j5, j6, j7, j8 = st.columns(4)
j5.metric("Visited", ck["visited"])
j6.metric("Lost Customers", ck["lost"])
j7.metric("Recovered Customers", ck["recovered"], help="فاتوا وبعد المتابعة/الخصم رجعوا وحضروا")
j8.metric("Discounts Granted", f"{ck['discounts_granted']:,} ج", help="الخصومات الإضافية الموافق عليها من الإدارة")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Free Home Visits (عُرضت)", ck["free_visits_offered"])
k2.metric("Free Home Visits (استُخدمت)", ck["free_visits_used"])
k3.metric("VIP Customers", ck["vip_customers"])
k4.metric("Gifts Delivered", ck["gifts_delivered"], help=f"تكلفتها {ck['gifts_cost']:,} ج")

st.markdown("##### 👤 المقارنة بالموظف")
if ck["by_staff"]:
    st.dataframe(pd.DataFrame([
        {"الموظف": k, "عروض": v["quotes"], "اتبعتت": v["sent"], "حضروا": v["visited"],
         "Visit Rate %": v["visit_rate_pct"], "قيمة العروض": v["value"]}
        for k, v in sorted(ck["by_staff"].items(), key=lambda x: -x[1]["quotes"])]),
        use_container_width=True, hide_index=True)
    st.caption("الموظف بيتسجّل من خانة «الموظف» في الفاتورة (قايمة الموظفين من إعدادات صفحة Customers).")

st.markdown("##### 💬 تحليل الاعتراضات (من الردود الجاهزة)")
_obj = objection_stats(events)
if _obj:
    st.dataframe(pd.DataFrame([
        {"الاعتراض": RP.OBJECTION_LABELS.get(k, k), "اتقال كام مرة": v["count"], "عروض مرتبطة": v["quotes"],
         "حضروا": v["visited"], "فاتوا": v["lost"], "لسه مفتوحة": v["open"], "Visit Rate %": v["visit_rate_pct"],
         "أكتر سبب فوات": "، ".join(f"{r} ({c})" for r, c in v["top_reasons"]) or "—"}
        for k, v in sorted(_obj.items(), key=lambda x: -x[1]["count"])]),
        use_container_width=True, hide_index=True)
    st.caption("بيتسجّل لما الموظف يضغط «سجّل المحادثة» في صفحة Replies. أسباب الفوات الأعم فوق (❌ أسباب فوات العملاء).")
else:
    st.caption("لسه مفيش اعتراضات متسجّلة — استخدم صفحة Replies وسجّل المحادثات.")

with st.expander("🔎 Audit Log — قرارات الخصم الإضافي وتعديلات الإعدادات"):
    _aud = [{"الوقت": r["recovery"]["decision"]["ts"][:16], "النوع": "خصم إضافي",
             "التفاصيل": f"{r['quote_id']}: {r['recovery']['decision'].get('decision', '')} "
                         f"{int(r['recovery']['decision'].get('amount', 0) or 0):,} ج — {r['recovery']['decision'].get('reason', '')}",
             "بواسطة": r["recovery"]["decision"].get("approver", "")}
            for r in quote_records(events).values() if r["recovery"] and r["recovery"]["decision"]]
    _aud += [{"الوقت": e["ts"][:16], "النوع": "تعديل إعدادات",
              "التفاصيل": f"{(e.get('meta') or {}).get('section', '')} {(e.get('meta') or {}).get('note', '')}",
              "بواسطة": (e.get("meta") or {}).get("by", "")} for e in events if e.get("type") == "config_change"]
    _aud.sort(key=lambda x: x["الوقت"], reverse=True)
    if _aud:
        st.dataframe(pd.DataFrame(_aud), use_container_width=True, hide_index=True)
    else:
        st.caption("مفيش قرارات أو تعديلات في الفترة دي")

st.caption(f"({len(events)} حدث مسجّل من {start_m} لغاية {end_m})")
