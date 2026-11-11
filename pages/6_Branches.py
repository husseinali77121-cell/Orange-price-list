# pages/6_Branches.py
# ============================================================
#  📍 Branch Information — بيانات الفروع قابلة للتعديل من الإدارة (مش مكتوبة في الكود):
#  الاسم، العنوان، مواعيد العمل، رقم التواصل (بيظهر على صور Marketing Studio)، لينك Google
#  Maps، والخدمات. بتتحفظ في config/app_config.json وكل تعديل بيتسجّل باسم اللي عمله.
#  البيانات دي بتتبعت مع عرض السعر وفي رسائل الاستوديو.
# ============================================================

import streamlit as st

import config_store
import setup_check
from access import require_access, secret_str
from github_store import GithubStoreError, store_from_secrets
from brand import DEFAULT_PHONE, OFFERS_PHONE
import offers_catalog as OC
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
tab_b, tab_l, tab_p, tab_s = st.tabs(["📍 Branches", "🔗 Links", "⚙️ Policy", "🩺 Setup check"])
with tab_b:
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


# ---------------- الروابط ----------------
with tab_l:
    st.caption("لينك التطبيق بيتكتب في لينكات عروض الأسعار المحفوظة. لينك التقييم والفيسبوك بيظهروا في الرسائل وأزرار المشاركة.")
    lk = cfg["links"]
    app_url = st.text_input("لينك التطبيق (Streamlit)", lk.get("app_url", ""), key="lk_app",
                            placeholder="https://your-app.streamlit.app")
    review_url = st.text_input("لينك تقييم Google Maps", lk.get("review_url", ""), key="lk_review")
    fb_url = st.text_input("لينك صفحة فيسبوك", lk.get("facebook_page_url", ""), key="lk_fb")
    if st.button("💾 احفظ الروابط", type="primary", key="lk_save"):
        new_links = {"app_url": app_url.strip().rstrip("/"), "review_url": review_url.strip(),
                     "facebook_page_url": fb_url.strip()}
        bad = [k for k, v in new_links.items() if v and not config_store.valid_url(v)]
        if bad:
            st.error("لينك مش صحيح (لازم https://…): " + "، ".join(bad))
        elif not store:
            st.error("التتبّع مش متظبط — مقدرتش أحفظ")
        else:
            try:
                config_store.save_section(store, "links", new_links, who=who, note="links")
                st.success("اتحفظ ✅")
            except ValueError as e:
                st.error(str(e))
            except GithubStoreError as e:
                st.error(f"مقدرتش أحفظ: {e}")

# ---------------- سياسة الخصم والمتابعة ----------------
with tab_p:
    pol = cfg["policy"]
    st.caption("أي خصم أكبر من الحد ده بيقفل إرسال الواتساب لحد ما المسؤول يكتب كود الموافقة "
               "(discount_approval_pin في Secrets). عروض الكتالوج الرسمية والاسترجاع المعتمد مش محتاجين كود.")
    lim = st.number_input("حد الخصم بدون موافقة (%)", min_value=0, max_value=100, step=5,
                          value=int(round(config_store.discount_limit(cfg))), key="pol_limit",
                          help="0 = مفيش حد. الافتراضي 50%.")
    _fh_opts = [3, 6, 24, 48, 72, 0]
    fh = st.selectbox("ميعاد المتابعة الافتراضي بعد إرسال العرض", _fh_opts,
                      index=_fh_opts.index(config_store.followup_hours(cfg)), key="pol_fu",
                      format_func=lambda h: {0: "من غير متابعة", 3: "بعد 3 ساعات", 6: "بعد 6 ساعات",
                                             24: "بكرة (24 ساعة)", 48: "بعد يومين", 72: "بعد 3 أيام"}[h])
    if not secret_str(st.secrets, "discount_approval_pin"):
        st.warning("⚠️ مفيش discount_approval_pin في Secrets — الخصم الكبير هيظهر تحذير بس ومش هيقفل الإرسال.")
    if st.button("💾 احفظ السياسة", type="primary", key="pol_save"):
        new_pol = {**pol, "discount_limit_pct": float(lim), "followup_hours": int(fh)}
        errs = config_store.validate_policy(new_pol)
        if errs:
            for e in errs:
                st.error(e)
        elif not store:
            st.error("التتبّع مش متظبط — مقدرتش أحفظ")
        else:
            try:
                config_store.save_section(store, "policy", new_pol, who=who,
                                          note=f"discount limit {lim}% · follow-up {fh}h")
                st.success(f"اتحفظ ✅ — الحد بقى {lim}% (بيتطبّق في الفاتورة خلال دقيقتين)")
            except ValueError as e:
                st.error(str(e))
            except GithubStoreError as e:
                st.error(f"مقدرتش أحفظ: {e}")

# ---------------- فحص الإعدادات ----------------
with tab_s:
    st.caption("فحص سريع قبل التشغيل الفعلي: Secrets، الروابط، أرقام الفروع، وحماية بيانات العملاء.")
    info_repo = store.repo_info() if store else None
    checks = setup_check.run_checks(
        st.secrets, cfg, config_store.resolve_links(cfg, st.secrets), info_repo,
        default_phone=DEFAULT_PHONE, offers_phone=OFFERS_PHONE,
        pending_offers=sum(1 for o in OC.OFFERS if o["status"] == "pending"))
    sm = setup_check.summary(checks)
    m1, m2, m3 = st.columns(3)
    m1.metric("✅ تمام", sm["ok"])
    m2.metric("⚠️ مراجعة", sm["warn"])
    m3.metric("❌ لازم تتصلّح", sm["fail"])
    for c in sorted(checks, key=lambda c: {"fail": 0, "warn": 1, "ok": 2}[c["status"]]):
        icon = {"ok": "✅", "warn": "⚠️", "fail": "❌"}[c["status"]]
        st.write(f"{icon} **{c['title']}**" + (f" — {c['hint']}" if c["hint"] else ""))
