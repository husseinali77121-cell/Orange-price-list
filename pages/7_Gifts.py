# pages/7_Gifts.py
# ============================================================
#  🎀 Gift Management — هدية الترحيب بالعميل الجديد (مع دكتور الزيارة المنزلية)
#  التنبيه: زيارة منزلية (حجز/حضور) لعميل جديد ولسه الهدية ماتسلّمتش:
#  «NEW CUSTOMER – WELCOME GIFT». الدكتور بيختار الهدية ويأكّد التسليم، وبيتسجّل
#  (النوع، التكلفة، اسم المسلِّم، التاريخ، ملاحظات) — ومنها عدد الهدايا وتكلفتها.
# ============================================================

from datetime import date, datetime, timedelta

import streamlit as st

import config_store
from access import require_access
from github_store import (GithubStoreError, events_path, read_events_range,
                          store_from_secrets)
from navigation import render_nav
from tracking import gift_queue, gift_stats, make_event, month_key, quote_records

st.set_page_config(page_title="Orange Lab - Gifts", page_icon="🎀", layout="wide")
st.markdown("## 🎀 Gift Management")
render_nav(st, "pages/7_Gifts.py")
require_access(st, "صفحة الهدايا", level="staff")

store = store_from_secrets(st.secrets)
if not store:
    st.warning("تتبّع العروض مش متظبط (gh_events_token / gh_events_repo في Secrets).")
    st.stop()


@st.cache_data(ttl=60, show_spinner=False)
def load_events():
    s = store_from_secrets(st.secrets)
    now = datetime.now()
    y, m = now.year, now.month - 5
    while m < 1:
        m += 12
        y -= 1
    return read_events_range(s, f"{y:04d}-{m:02d}", month_key(now))


@st.cache_data(ttl=120, show_spinner=False)
def load_cfg():
    return config_store.load(store_from_secrets(st.secrets))


try:
    events = load_events()
except GithubStoreError as e:
    st.error(f"مقدرتش أجيب البيانات: {e}")
    st.stop()
cfg = load_cfg()
gifts = {g["name"]: g for g in cfg["gifts"]}

stats = gift_stats(events)
m1, m2, m3 = st.columns(3)
m1.metric("🎀 هدايا اتسلّمت", stats["count"])
m2.metric("💰 تكلفتها", f"{stats['cost']:,} ج")
m3.metric("⏳ مستنية تسليم", len(gift_queue(events)))
if st.button("🔄 تحديث"):
    load_events.clear()
    st.rerun()

st.markdown("### NEW CUSTOMER – WELCOME GIFT")
queue = gift_queue(events)
if not queue:
    st.success("مفيش هدايا مستنية دلوقتي 👌")
for r in queue:
    c = r.get("contact") or {}
    head = f"🎀 {c.get('name') or r['quote_id']} · {r['branch'] or '—'}" + (f" · {r['area']}" if r["area"] else "")
    with st.expander(head, expanded=len(queue) <= 3):
        st.warning("NEW CUSTOMER – WELCOME GIFT" + (" (جديد غالباً — مفيش بصمة تتأكد بيها)" if r["unverified_new"] else ""))
        st.caption(f"{r['quote_id']} · ميعاد الزيارة: {r['appointment'] or '—'}")
        gtype = st.selectbox("الهدية", list(gifts), key=f"gt_{r['quote_id']}")
        by = st.text_input("اسم اللي سلّمها (الدكتور/المندوب)", key=f"gb_{r['quote_id']}")
        gdate = st.date_input("تاريخ التسليم", value=date.today(), key=f"gd_{r['quote_id']}")
        note = st.text_input("ملاحظات", key=f"gn_{r['quote_id']}")
        if st.button("✅ تأكيد التسليم", key=f"gc_{r['quote_id']}", type="primary", use_container_width=True):
            if not by.strip():
                st.error("اكتب اسم اللي سلّم الهدية")
            else:
                try:
                    store.append(events_path(month_key()), make_event(
                        "gift", r["quote_id"], branch=r["branch"], phone_key=r.get("pk", ""),
                        meta={"gift_type": gtype, "cost": int(gifts[gtype].get("cost", 0) or 0),
                              "delivered_by": by.strip(), "note": note.strip(), "date": str(gdate)}))
                    load_events.clear()
                    st.rerun()
                except GithubStoreError as e:
                    st.error(f"مقدرتش أسجّل: {e}")

st.markdown("### 📜 سجل الهدايا")
rows = [{"التاريخ": r["gift"].get("date", r["gift"]["ts"][:10]), "العرض": r["quote_id"],
         "الهدية": r["gift"].get("gift_type", ""), "التكلفة": r["gift"].get("cost", 0),
         "سلّمها": r["gift"].get("delivered_by", ""), "ملاحظات": r["gift"].get("note", ""),
         "الفرع": r["branch"]} for r in quote_records(events).values() if r["gift"]]
rows.sort(key=lambda x: x["التاريخ"], reverse=True)
if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.caption("لسه مفيش هدايا مسجّلة")
