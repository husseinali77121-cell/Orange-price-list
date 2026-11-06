# pages/4_Promotions.py
# ============================================================
#  🎁 العروض + 🧹 جودة الأسعار — إدارة من غير تعديل كود
#  العرض بيتخزّن في promotions/promotions.json على GitHub (نفس ريبو الأحداث)
#  وأسعار القائمة الأساسية ما بتتلمسش. كلمة سر الإدارة لو متظبطة.
# ============================================================

import csv
import io
from datetime import date, timedelta

import streamlit as st

from navigation import render_nav

from access import require_access
from bundles import BUNDLES as BUNDLE_DEFS
from bundles import BUNDLE_CATEGORY
from github_store import GithubStoreError, store_from_secrets
from labs_price_list import LABS_DB
from panels import BRANCHES
from price_audit import SEVERITY, audit_prices, summarize_audit
from price_utils import build_index, resolve_test
from promotions import (PROMO_PATH, STATE_LABELS, drift_warnings, new_promotion,
                        overlaps, promo_discount_pct, promo_state, set_status,
                        sorted_for_display, upsert)

st.set_page_config(page_title="Orange Lab - العروض", page_icon="🎁", layout="wide")
st.markdown("## 🎁 العروض وجودة الأسعار")
render_nav(st, "pages/4_Promotions.py")
require_access(st, "صفحة العروض")


@st.cache_resource(show_spinner=False)
def load_index():
    return build_index(LABS_DB, BUNDLE_DEFS, BUNDLE_CATEGORY)


IDX = load_index()
store = store_from_secrets(st.secrets)
today = date.today()
tab_promos, tab_quality = st.tabs(["🎁 العروض", "🧹 جودة الأسعار"])

# ------------------------------------------------------------
# 🎁 العروض
# ------------------------------------------------------------
with tab_promos:
    if not store:
        st.warning("العروض بتتخزّن على GitHub — ظبّط gh_events_token / gh_events_repo في Secrets الأول.")
    else:
        try:
            promos, _sha = store.read(PROMO_PATH)
            if not isinstance(promos, list):
                promos = []
        except GithubStoreError as e:
            st.error(f"مقدرتش أقرا العروض: {e}")
            promos = []

        st.markdown("#### ➕ عرض جديد")
        names = [b.name for b in IDX.bundles]
        c1, c2 = st.columns(2)
        pick = c1.selectbox("الهدف", names + ["— تحليل آخر —"], key="pr_pick")
        target = pick
        if pick == "— تحليل آخر —":
            typed = c2.text_input("اسم التحليل (زي القائمة)", key="pr_typed")
            res = resolve_test(typed, IDX) if typed.strip() else None
            if res and res.is_confident:
                target = res.best.name
                c2.caption(f"✔ {target}")
            else:
                target = ""
                if typed.strip():
                    c2.caption("مش لاقي تطابق دقيق — اكتب الاسم زي القائمة")
        hits = IDX.get(target) if target else []
        list_price = hits[0].price if hits else 0
        st.caption(f"سعر القائمة الحالي: **{list_price:,}**" if list_price else "اختار هدف له سعر")

        n1, n2, n3 = st.columns([2, 1, 1])
        name = n1.text_input("اسم العرض", key="pr_name", placeholder="مثال: Lipid Nov")
        promo_price = n2.number_input("سعر العرض", min_value=0, step=10, key="pr_price")
        pct = round(100 * (list_price - promo_price) / list_price, 1) if list_price and promo_price else 0
        n3.metric("نسبة الخصم", f"{pct}%")
        d1, d2, d3 = st.columns([1, 1, 2])
        start = d1.date_input("من", value=today, key="pr_start")
        end = d2.date_input("لغاية (شامل)", value=today + timedelta(days=29), key="pr_end")
        branches = d3.multiselect("الفروع (فاضي = كل الفروع)", BRANCHES, key="pr_br")
        note = st.text_input("ملاحظة داخلية (اختياري)", key="pr_note")

        if st.button("💾 احفظ العرض", type="primary"):
            try:
                p = new_promotion(name=name, target=target, original_price=list_price,
                                  promo_price=int(promo_price), start=start, end=end,
                                  branches=branches, note=note)
                clash = overlaps(promos, p)
                if clash:
                    st.warning("⚠️ بيتقاطع مع عرض تاني على نفس الهدف: "
                               + "، ".join(f"{c['name']} ({c['start']}→{c['end']})" for c in clash)
                               + " — اتحفظ، والأرخص هو اللي هيظهر للموظف.")
                store.update(PROMO_PATH, lambda d: upsert(d if isinstance(d, list) else [], p),
                             message=f"promotion: {p['id']} {p['name']}")
                st.success(f"اتحفظ ✅ {p['id']}")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except GithubStoreError as e:
                st.error(f"مقدرتش أحفظ: {e}")

        st.divider()
        st.markdown("#### 📋 العروض")
        if not promos:
            st.caption("مفيش عروض لسه")
        for p in sorted_for_display(promos, today):
            state = promo_state(p, today)
            head = (f"{STATE_LABELS[state]} · {p['name']} · {p['target']} · "
                    f"{p['original_price']:,} → {p['promo_price']:,} ({promo_discount_pct(p)}%)")
            with st.expander(head):
                st.caption(f"{p['id']} · {p['start']} → {p['end']} · "
                           f"{'، '.join(p['branches']) or 'كل الفروع'}"
                           + (f" · {p['note']}" if p.get("note") else ""))
                for w in drift_warnings(p, IDX):
                    st.warning("⚠️ " + w)
                b1, b2, b3 = st.columns(3)
                changes = [("⏸️ وقف", "paused", state == "active" or state == "scheduled"),
                           ("▶️ شغّل", "active", p.get("status") == "paused"),
                           ("🚫 إلغاء", "cancelled", p.get("status") != "cancelled")]
                for col, (label, status, show) in zip((b1, b2, b3), changes):
                    if show and col.button(label, key=f"{status}_{p['id']}", use_container_width=True):
                        try:
                            store.update(PROMO_PATH, lambda d, s=status, i=p["id"]: set_status(d, i, s),
                                         message=f"promotion {status}: {p['id']}")
                            st.rerun()
                        except GithubStoreError as e:
                            st.error(str(e))

# ------------------------------------------------------------
# 🧹 جودة الأسعار
# ------------------------------------------------------------
with tab_quality:
    issues = audit_prices(IDX)
    sm = summarize_audit(issues)
    LABELS = {"zero_price": "سعر صفر", "no_result_days": "من غير مدة نتيجة",
              "no_collection_notes": "من غير تعليمات عينة",
              "duplicate_diff_price": "مكرر بأسعار مختلفة", "duplicate_same_price": "مكرر بنفس السعر",
              "bundle_no_saving": "باقة من غير توفير", "bundle_pricier": "باقة أغلى من مكوّناتها",
              "bundle_component_missing": "مكوّن باقة مش موجود"}
    cols = st.columns(4)
    for i, (k, label) in enumerate(LABELS.items()):
        cols[i % 4].metric(label, sm.get(k, 0))
    st.caption("الفحص بيدلّك على الأماكن بس — السعر الصح قرارك. بعد أي تعديل شغّل `python3 test_price_utils.py`.")

    kinds = st.multiselect("نوع المشكلة", list(LABELS), default=["zero_price", "duplicate_diff_price",
                                                                "bundle_no_saving", "bundle_pricier",
                                                                "bundle_component_missing"],
                           format_func=lambda k: LABELS[k])
    rows = [{"الأهمية": SEVERITY[i["severity"]], "المشكلة": LABELS[i["kind"]],
             "القسم": i["category"], "الاسم": i["name"], "السعر": i["price"], "التفاصيل": i["detail"]}
            for i in issues if i["kind"] in kinds]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    def to_csv(rows_, fields):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_)
        return ("\ufeff" + buf.getvalue()).encode("utf-8")        # BOM عشان Excel يقرا العربي

    if rows:
        st.download_button("⬇️ تقرير المشاكل (CSV)", to_csv(rows, list(rows[0])),
                           file_name=f"price-audit-{today}.csv", mime="text/csv")
    export = [{"category": r.category, "name": r.name, "price": r.price,
               "result_days": r.result_days or "", "collection_notes": r.collection_notes,
               "is_bundle": int(r.is_bundle)} for r in IDX.records]
    st.download_button("⬇️ تصدير قائمة الأسعار الحالية (CSV)",
                       to_csv(export, list(export[0])), file_name=f"price-list-{today}.csv",
                       mime="text/csv")
