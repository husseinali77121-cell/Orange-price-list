# pages/6_Branches.py
# ============================================================
#  📍 Branch Information — بيانات الفروع قابلة للتعديل من الإدارة (مش مكتوبة في الكود):
#  الاسم، العنوان، مواعيد العمل، رقم التواصل (بيظهر على صور Marketing Studio)، لينك Google
#  Maps، والخدمات. بتتحفظ في config/app_config.json وكل تعديل بيتسجّل باسم اللي عمله.
#  البيانات دي بتتبعت مع عرض السعر وفي رسائل الاستوديو.
# ============================================================

import streamlit as st

import config_store
from access import require_access
from github_store import GithubStoreError, store_from_secrets
from navigation import render_nav

st.set_page_config(page_title="Orange Lab - Branches", page_icon="📍", layout="wide")
st.markdown("## 📍 Branch Information")
render_nav(st, "pages/6_Branches.py")
require_access(st, "صفحة الفروع", level="admin")

store = store_from_secrets(st.secrets)
cfg = config_store.load(store)
if not store:
    st.warning("التعديل بيتحفظ على GitHub — ظبّط gh_events_token / gh_events_repo في Secrets. "
               "دلوقتي بتشوف البيانات الافتراضية بس.")

who = st.text_input("اسمك (كل تعديل بيتسجّل باسمك)", key="br_who")

for key, info in cfg["branches"].items():
    with st.expander(f"📍 {info['name_ar']} — {info.get('name_en', key)}", expanded=True):
        c1, c2 = st.columns(2)
        name_ar = c1.text_input("الاسم بالعربي", info["name_ar"], key=f"br_{key}_name_ar")
        name_en = c2.text_input("Name (English)", info.get("name_en", ""), key=f"br_{key}_name_en")
        phone = c1.text_input("رقم التواصل (بيظهر على الصور والرسائل)", info.get("phone", ""), key=f"br_{key}_phone")
        maps = c2.text_input("لينك Google Maps", info["maps"], key=f"br_{key}_maps")
        address = st.text_area("العنوان", info["address"], key=f"br_{key}_address", height=90)
        hours = st.text_area("مواعيد العمل", info["hours"], key=f"br_{key}_hours", height=70)
        services = st.text_area("الخدمات المتاحة (سطر لكل خدمة)", "\n".join(info.get("services", [])),
                                key=f"br_{key}_services", height=80)
        new = {"name_ar": name_ar.strip(), "name_en": name_en.strip(), "phone": phone.strip(),
               "maps": maps.strip(), "address": address.strip(), "hours": hours.strip(),
               "services": [s.strip() for s in services.splitlines() if s.strip()]}
        st.markdown("**معاينة اللي هيوصل للعميل:**")
        st.code(config_store.branch_block(new), language=None)
        d1, d2 = st.columns(2)
        d1.link_button("🧭 Directions", new["maps"] or info["maps"], use_container_width=True)
        if d2.button("💾 احفظ الفرع", key=f"br_{key}_save", type="primary", use_container_width=True):
            errs = config_store.validate_branch(new)
            if errs:
                for e in errs:
                    st.error(e)
            elif not store:
                st.error("التتبّع مش متظبط — مقدرتش أحفظ")
            else:
                try:
                    merged = {k: dict(v) for k, v in cfg["branches"].items()}
                    merged[key] = new
                    config_store.save_section(store, "branches", merged, who=who, note=f"branch {key}")
                    st.success("اتحفظ ✅ — هيظهر في الفاتورة والاستوديو خلال دقيقتين")
                except ValueError as e:
                    st.error(str(e))
                except GithubStoreError as e:
                    st.error(f"مقدرتش أحفظ: {e}")
