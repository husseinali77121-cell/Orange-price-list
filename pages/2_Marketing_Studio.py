# pages/2_Marketing_Studio.py
# ============================================================
#  🎨 Marketing Studio — فاز 2
#  الموظف يكتب العرض -> البرنامج يحطّه على قالب Orange جاهز ->
#  تحميل الصورة + مشاركة (واتساب / فيسبوك / مشاركة الصورة من الموبايل).
#  الأسعار بتتسحب من الباقات الحقيقية (bundles.py) عشان الإعلان
#  ما يتعارضش مع السعر الفعلي.
# ============================================================

import io
import json
import zipfile
from datetime import date
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

import offers_catalog as OC
from brand import (DEFAULT_PHONE, FACEBOOK_PAGE_URL, LAB_NAME_AR, MAPS_URL,
                   branch_maps_url)
from campaign_library import CAMPAIGNS, DISCLAIMER, campaign_fields
from bundles import BUNDLES as BUNDLE_DEFS
from bundles import BUNDLE_CATEGORY, bundles_for
from github_store import GithubStoreError, events_path, store_from_secrets
from labs_price_list import LABS_DB
from marketing import share_url
from marketing_templates import (PRESETS, SAMPLE_PHOTOS, SIZE_LABELS, SIZES,
                                 TEMPLATES, build_caption, font_status,
                                 make_campaign_id, render_template,
                                 to_jpeg_bytes, to_png_bytes)
from navigation import render_nav
from panels import BRANCHES, DEFAULT_BRANCH
from share_widget import share_button_html
from price_utils import MAX_WA_URL, build_index, bundle_saving, resolve_test
from promotions import PROMO_PATH, active_promotions
from tracking import make_event, month_key

st.set_page_config(page_title="Orange Lab - Marketing Studio", page_icon="🎨",
                   layout="wide")

st.markdown("""
<style>
textarea, input[type="text"] {unicode-bidi: plaintext; text-align: start;}
div[data-testid="stVerticalBlock"] {gap:.6rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def load_index():
    return build_index(LABS_DB, BUNDLE_DEFS, BUNDLE_CATEGORY)


IDX = load_index()

# اسم عربي للباقات (العنوان على الصورة)
BUNDLE_AR = {
    "Lipid Profile": ("تحاليل", "الدهون"),
    "Liver Profile": ("تحاليل", "الكبد"),
    "Kidney Profile": ("تحاليل", "الكلى"),
    "Thyroid Profile": ("تحاليل", "الغدة الدرقية"),
}

PRESET_LABELS = {
    "sugar_offer": "🩸 عرض خصم — تحاليل السكر",
    "hair_awareness": "🥚 توعية — تساقط الشعر",
    "sun_tip": "☀️ نصيحة — كريمات الشمس",
}
FIELD_KEYS = ["title_small", "title_big", "subtitle", "badge_mode", "badge_top",
              "badge_value", "badge_sub", "badge_pill", "old_price", "list_title",
              "items", "cta", "valid_until", "show_trust", "headline", "body"]
DEFAULTS = {"badge_mode": "percent", "show_trust": True, "list_title": "الباقة تشمل",
            "cta": "احجز تحاليلك الآن"}


def apply_preset(name: str):
    p = PRESETS[name]
    st.session_state["ms_template"] = p["template"]
    st.session_state["ms_photo_src"] = "sample"
    st.session_state["ms_photo_sample"] = p.get("photo", "sugar")
    for k in FIELD_KEYS:
        st.session_state[f"ms_{k}"] = p.get(k, DEFAULTS.get(k, ""))
    st.session_state.pop("ms_ref_price", None)
    st.session_state.pop("ms_cap_txt", None)


def on_preset_change():
    apply_preset(st.session_state["ms_preset"])


def fill_from_bundle(branch: str):
    """يملا حقول العرض من باقة حقيقية: الاسم + السعر + السعر قبل + المكونات."""
    name = st.session_state.get("ms_bundle_pick")
    b = next((x for x in bundles_for(branch) if x["name"] == name), None)
    rec = resolve_test(name, IDX).best if name else None
    if not b or not rec:
        return
    retail, saving = bundle_saving(rec, IDX)
    small, big = BUNDLE_AR.get(name, ("باقة", name))
    st.session_state.update({
        "ms_template": "offer",
        "ms_title_small": small, "ms_title_big": big,
        "ms_subtitle": "باقة شاملة بسعر مميّز",
        "ms_badge_mode": "price", "ms_badge_top": "بسعر",
        "ms_badge_value": f"{rec.price:,}".replace(",", ""),
        "ms_old_price": f"{retail:,}".replace(",", "") if saving > 0 else "",
        "ms_badge_sub": "", "ms_badge_pill": name,
        "ms_list_title": "الباقة تشمل",
        "ms_items": "\n".join(b["components"]),
        "ms_ref_price": rec.price, "ms_ref_saving": saving, "ms_ref_name": name,
    })
    st.session_state.pop("ms_cap_txt", None)


def apply_library(branch: str):
    """حملة من المكتبة الموسمية: القالب + النص + التحاليل المقترحة (والسعر من القائمة)."""
    key = st.session_state.get("ms_lib")
    if key not in CAMPAIGNS:
        return
    c = CAMPAIGNS[key]
    f = campaign_fields(key)
    st.session_state["ms_template"] = f.pop("template")
    st.session_state["ms_photo_src"] = "sample"
    st.session_state["ms_photo_sample"] = f.pop("photo", "sugar")
    for k in FIELD_KEYS:
        st.session_state[f"ms_{k}"] = f.get(k, DEFAULTS.get(k, ""))
    retail = 0
    for t in c.get("tests", []):
        r = resolve_test(t, IDX).best
        retail += r.price if r else 0
    st.session_state["ms_lib_retail"] = retail
    st.session_state["ms_lib_review"] = bool(c.get("review"))
    st.session_state["ms_lib_key"] = key
    st.session_state.pop("ms_ref_price", None)
    st.session_state.pop("ms_cap_txt", None)


def fill_from_catalog():
    """يملا التصميم من عرض في كتالوج العروض (سعر قبل/بعد + تحاليل)."""
    o = OC.get(st.session_state.get("ms_cat"))
    if not o or not o.get("after"):
        return
    f = OC.studio_fields(o)
    st.session_state["ms_template"] = f.pop("template")
    st.session_state["ms_photo_src"] = "sample"
    st.session_state["ms_photo_sample"] = "sugar"
    for k in FIELD_KEYS:
        st.session_state[f"ms_{k}"] = f.get(k, DEFAULTS.get(k, ""))
    st.session_state.update({"ms_ref_price": o["after"], "ms_ref_name": o["title"],
                             "ms_ref_saving": OC.saving(o)})
    st.session_state.pop("ms_cap_txt", None)


@st.cache_data(ttl=120, show_spinner=False)
def load_promos():
    s = store_from_secrets(st.secrets)
    if not s:
        return []
    try:
        data, _ = s.read(PROMO_PATH)
        return data if isinstance(data, list) else []
    except GithubStoreError:
        return []


def fill_from_promo(branch: str):
    """يملا من عرض شغّال من «إدارة العروض»: السعر الأصلي + سعر العرض + المدة."""
    pid = st.session_state.get("ms_promo_pick")
    p = next((x for x in active_promotions(load_promos(), branch, date.today())
              if x["id"] == pid), None)
    if not p:
        return
    b = next((x for x in BUNDLE_DEFS if x["name"] == p["target"]), None)
    small, big = BUNDLE_AR.get(p["target"], ("عرض", p["target"]))
    d = date.fromisoformat(p["end"])
    st.session_state.update({
        "ms_template": "offer", "ms_title_small": small, "ms_title_big": big,
        "ms_subtitle": p["name"], "ms_badge_mode": "price", "ms_badge_top": "بسعر",
        "ms_badge_value": str(p["promo_price"]), "ms_old_price": str(p["original_price"]),
        "ms_badge_sub": "", "ms_badge_pill": p["target"],
        "ms_list_title": "الباقة تشمل" if b else "العرض يشمل",
        "ms_items": "\n".join(b["components"]) if b else p["target"],
        "ms_valid_until": f"العرض ساري حتى {d.day}/{d.month}",
        "ms_ref_price": p["promo_price"], "ms_ref_name": p["target"],
        "ms_ref_saving": p["original_price"] - p["promo_price"],
    })
    st.session_state.pop("ms_cap_txt", None)


# ------------------------------------------------------------
# حالة أولية
# ------------------------------------------------------------
if "ms_template" not in st.session_state:
    apply_preset("sugar_offer")
if "ms_cid" not in st.session_state:
    st.session_state["ms_cid"] = make_campaign_id()
st.session_state.setdefault("ms_branch", DEFAULT_BRANCH)
st.session_state.setdefault("ms_phone", DEFAULT_PHONE)
st.session_state.setdefault("ms_size", "post")
st.session_state.setdefault("ms_logged", set())

st.markdown("## 🎨 Marketing Studio")
render_nav(st, "pages/2_Marketing_Studio.py")
st.caption("اكتب العرض → اختار القالب → حمّل الصورة أو شاركها. الأسعار بتتسحب من الباقات.")

with st.sidebar:
    st.markdown("### 🎨 الاستوديو")
    st.selectbox("📂 ابدأ من مثال", list(PRESET_LABELS), key="ms_preset",
                 format_func=lambda k: PRESET_LABELS[k], index=None,
                 placeholder="اختار مثال جاهز…", on_change=on_preset_change)
    st.selectbox("📚 مكتبة الحملات الموسمية", list(CAMPAIGNS), key="ms_lib",
                 format_func=lambda k: CAMPAIGNS[k]["label"], index=None,
                 placeholder="اختار حملة…", on_change=apply_library,
                 args=(st.session_state.get("ms_branch", DEFAULT_BRANCH),))
    _cat_ids = [o["id"] for o in OC.selectable() if o["status"] == "current" and o.get("after")]
    st.selectbox("📋 كتالوج العروض (بالأرقام)", _cat_ids, key="ms_cat", index=None,
                 placeholder="اختار عرض…", on_change=fill_from_catalog,
                 format_func=lambda i: OC.option_label(OC.get(i)))
    st.selectbox("الفرع", BRANCHES, key="ms_branch")
    st.text_input("رقم التواصل على التصميم", key="ms_phone")
    st.divider()
    fs_ = font_status()
    st.caption(f"🔤 الخط: {fs_['bold']} · التشكيل: {'✅ raqm' if fs_['mode'] == 'raqm' else '⚠️ بديل'}")
    if fs_["skipped"]:
        st.warning("الخط " + "، ".join(fs_["skipped"]) + " اتخطّى لأن السيرفر مفيهوش FriBiDi "
                   "(الحروف كانت هتطير). ضيف ملف `packages.txt` فيه السطر `libfribidi0` "
                   "في جذر الريبو وأعد النشر، وبعدها الخط الجميل هيشتغل.")
    elif "DejaVu" in fs_["bold"]:
        st.caption("للشكل الأقرب لتصميماتك: حط `Cairo-Bold.ttf` و`Cairo-Regular.ttf` "
                   "في مجلد `Fonts/` (تفاصيل في Fonts/README.md).")
    st.caption(f"🆔 كود الحملة: `{st.session_state['ms_cid']}`")
    if st.button("🔄 كود حملة جديد", use_container_width=True):
        st.session_state["ms_cid"] = make_campaign_id()
        st.session_state["ms_logged"] = set()
        st.rerun()

left, right = st.columns([1.05, 1], gap="large")

# ------------------------------------------------------------
# 1) المحتوى
# ------------------------------------------------------------
with left:
    st.radio("القالب", list(TEMPLATES), key="ms_template", horizontal=True,
             format_func=lambda k: TEMPLATES[k])
    kind = st.session_state["ms_template"]

    if st.session_state.get("ms_lib_review"):
        st.warning("🩺 محتوى طبي — راجعه المسؤول الطبي قبل النشر، وماتقدّمهوش كتوصية شخصية.")
    if st.session_state.get("ms_lib_key") and st.session_state.get("ms_lib_retail"):
        st.info(f"💡 مجموع أسعار تحاليل الحملة في القائمة: **{st.session_state['ms_lib_retail']:,}** ج.م — "
                "حدّد سعر العرض بنفسك (مش بيتحط تلقائي).")

    if kind == "offer":
        promos_now = active_promotions(load_promos(), st.session_state["ms_branch"], date.today())
        if promos_now:
            with st.expander(f"🎁 عروض شغّالة دلوقتي ({len(promos_now)})", expanded=False):
                st.selectbox("العرض", [x["id"] for x in promos_now], key="ms_promo_pick",
                             format_func=lambda i: next(
                                 f"{x['name']} — {x['target']} ({x['promo_price']})"
                                 for x in promos_now if x["id"] == i))
                st.button("⚡ املا التصميم من العرض", on_click=fill_from_promo,
                          args=(st.session_state["ms_branch"],), use_container_width=True)
        with st.expander("📦 املا من باقة حقيقية (السعر بيتسحب أوتوماتيك)", expanded=False):
            names = [b["name"] for b in bundles_for(st.session_state["ms_branch"])]
            st.selectbox("الباقة", names, key="ms_bundle_pick")
            st.button("⚡ املا العرض من الباقة", on_click=fill_from_bundle,
                      args=(st.session_state["ms_branch"],), use_container_width=True)
            if st.session_state.get("ms_ref_saving") == 0 and \
                    st.session_state.get("ms_ref_name"):
                st.warning(f"⚠️ {st.session_state['ms_ref_name']}: سعرها = مجموع تحاليلها، "
                           "مفيش توفير. ماتسوّقهاش على إنها خصم.")

        c1, c2 = st.columns(2)
        c1.text_input("عنوان صغير (أبيض)", key="ms_title_small")
        c2.text_input("عنوان كبير (برتقالي)", key="ms_title_big")
        st.text_input("سطر شرح", key="ms_subtitle")

        st.radio("الشارة (الدايرة البرتقالي)", ["percent", "price", "none"],
                 key="ms_badge_mode", horizontal=True,
                 format_func=lambda k: {"percent": "٪ خصم", "price": "💰 سعر",
                                        "none": "بدون"}[k])
        mode = st.session_state["ms_badge_mode"]
        if mode != "none":
            b1, b2 = st.columns(2)
            b1.text_input("كلمة فوق (خصم / بسعر)", key="ms_badge_top")
            b2.text_input("القيمة (20% أو 700)", key="ms_badge_value")
            if mode == "price":
                st.text_input("السعر قبل العرض (اختياري)", key="ms_old_price")
            else:
                st.text_input("سطر تحت القيمة", key="ms_badge_sub")
            st.text_input("الكبسولة السودا (اسم الباقة)", key="ms_badge_pill")
            ref = st.session_state.get("ms_ref_price")
            val = (st.session_state.get("ms_badge_value") or "").strip()
            if mode == "price" and ref and val.isdigit() and int(val) != ref:
                st.warning(f"⚠️ السعر على الصورة ({val}) غير سعر "
                           f"{st.session_state.get('ms_ref_name', 'الباقة')} في القائمة ({ref}).")

        st.text_input("عنوان القائمة", key="ms_list_title")
        st.text_area("المحتويات (سطر لكل بند — لحد 8)", key="ms_items", height=130)
        c3, c4 = st.columns(2)
        c3.text_input("زرار الحجز", key="ms_cta")
        c4.text_input("مدة العرض (مثال: ساري حتى 30 نوفمبر)", key="ms_valid_until")
        st.toggle("إظهار المزايا (دقة · سرعة · رعاية)", key="ms_show_trust")
    else:
        st.text_input("العنوان", key="ms_headline")
        st.text_area("الشرح", key="ms_body", height=110,
                     help="لتلوين كلمات: ضعها بين [[ ]] — مثال: بسبب [[نقص الحديد]]")
        st.caption("💡 الكلمات بين [[ ]] بتتلوّن/تتبرّز في التصميم.")

    # الصورة
    st.markdown("**🖼️ الصورة**")
    st.radio("مصدر الصورة", ["sample", "upload", "none"], key="ms_photo_src",
             horizontal=True,
             format_func=lambda k: {"sample": "صورة جاهزة", "upload": "ارفع صورتك",
                                    "none": "بدون صورة"}[k])
    photo_value = None
    src = st.session_state["ms_photo_src"]
    if src == "sample":
        st.radio("الصور الجاهزة", list(SAMPLE_PHOTOS), key="ms_photo_sample",
                 horizontal=True, format_func=lambda k: SAMPLE_PHOTOS[k][0])
        photo_value = st.session_state["ms_photo_sample"]
        st.caption("الصور الجاهزة منخفضة الدقة — ارفع صورة أوضح للنتيجة الأفضل.")
    elif src == "upload":
        up = st.file_uploader("صورة JPG / PNG / WEBP", type=["jpg", "jpeg", "png", "webp"])
        if up is not None:
            if up.size > 12 * 1024 * 1024:
                st.error("الصورة أكبر من 12MB — صغّرها وجرّب تاني")
            else:
                photo_value = up.getvalue()


# ------------------------------------------------------------
# 2) الرسم (مع كاش)
# ------------------------------------------------------------

def collect_fields() -> dict:
    g = st.session_state.get
    f = {"phone": (g("ms_phone") or "").strip()}
    for k in FIELD_KEYS:
        v = g(f"ms_{k}")
        if v is not None:
            f[k] = v
    return f


@st.cache_data(show_spinner=False, max_entries=24)
def render_cached(kind: str, size: str, fields_json: str, photo_bytes: bytes):
    f = json.loads(fields_json)
    if photo_bytes:
        f["photo"] = photo_bytes
    img = render_template(kind, size, f)
    return to_png_bytes(img), to_jpeg_bytes(img, 90)


fields = collect_fields()
if isinstance(photo_value, str):
    fields["photo"] = photo_value
photo_bytes = photo_value if isinstance(photo_value, (bytes, bytearray)) else b""
fields_json = json.dumps(fields, ensure_ascii=False, sort_keys=True)

# ------------------------------------------------------------
# 3) المعاينة + المشاركة
# ------------------------------------------------------------
with right:
    st.radio("المقاس", list(SIZES), key="ms_size", horizontal=True,
             format_func=lambda k: SIZE_LABELS[k])
    size = st.session_state["ms_size"]
    try:
        png, jpg = render_cached(kind, size, fields_json, bytes(photo_bytes))
    except Exception as e:                       # noqa: BLE001
        st.error(f"مقدرتش أرسم التصميم: {e}")
        st.stop()
    st.image(png, use_container_width=True)

    cid = st.session_state["ms_cid"]
    title_for_log = (fields.get("title_big") or fields.get("headline") or "")[:60]

    def log_campaign(fmt: str):
        key = (cid, kind, size, fmt)
        if key in st.session_state["ms_logged"]:
            return
        store = store_from_secrets(st.secrets)
        if not store:
            return
        try:
            ev = make_event("campaign", quote_id=cid,
                            branch=st.session_state["ms_branch"], note=title_for_log,
                            meta={"template": kind, "size": size, "format": fmt,
                                  "badge": fields.get("badge_mode", "")})
            store.append(events_path(month_key()), ev)
            st.session_state["ms_logged"].add(key)
        except GithubStoreError:
            pass                                  # التتبّع ماينفعش يوقّف التحميل

    fname = f"orange-{kind}-{size}-{cid}"
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ تحميل الصورة (PNG)", png, file_name=f"{fname}.png",
                       mime="image/png", use_container_width=True, type="primary",
                       on_click=log_campaign, args=("png",))
    d2.download_button("⬇️ JPG (أخف للواتساب)", jpg, file_name=f"{fname}.jpg",
                       mime="image/jpeg", use_container_width=True,
                       on_click=log_campaign, args=("jpg",))

    # ---------------- نص المنشور ----------------
    st.markdown("**📝 نص المنشور**")
    inc_code = st.toggle("اكتب كود الحملة في النص (لتتبّع الحجوزات)", value=False,
                         key="ms_inc_code")
    add_disc = st.toggle("إضافة تنويه طبي في النص", value=(kind != "offer"), key="ms_disc")
    auto = build_caption(kind, fields, lab=LAB_NAME_AR,
                         phone=fields.get("phone", ""), maps_url=branch_maps_url(st.session_state["ms_branch"]),
                         campaign_id=cid, include_code=inc_code,
                         disclaimer=DISCLAIMER if add_disc else "")
    if st.session_state.get("ms_cap_auto") != auto:
        if st.session_state.get("ms_cap_txt") in (None, st.session_state.get("ms_cap_auto")):
            st.session_state["ms_cap_txt"] = auto
        st.session_state["ms_cap_auto"] = auto
    caption = st.text_area("تقدر تعدّله قبل الإرسال", key="ms_cap_txt", height=230)
    st.button("🔄 اعمل النص من جديد", on_click=lambda: st.session_state.update(
        ms_cap_txt=st.session_state.get("ms_cap_auto", "")), use_container_width=True)

    # ---------------- المشاركة ----------------
    st.markdown("**📲 شارك**")
    wa = share_url(caption)
    if len(wa) > MAX_WA_URL:
        st.warning("النص طويل على لينك واتساب — انسخه من تحت وابعته يدوي")
        st.code(caption, language=None)
    else:
        s1, s2 = st.columns(2)
        s1.link_button("🟢 واتساب (النص)", wa, use_container_width=True)
        fb_target = FACEBOOK_PAGE_URL or MAPS_URL
        fb = "https://www.facebook.com/sharer/sharer.php?u=" + quote(fb_target, safe="")
        if len(fb) + len(quote(caption, safe="")) < 1900:
            fb += "&quote=" + quote(caption, safe="")
        s2.link_button("🔵 فيسبوك", fb, use_container_width=True)

    # مشاركة الصورة نفسها (Web Share API — الموبايل)
    components.html(share_button_html(jpg, caption, f"{fname}.jpg"), height=90)
    st.caption("ℹ️ لينكات واتساب وفيسبوك بتحط **النص** بس — الويب ما بيسمحش يرفق صورة "
               "تلقائي. للصورة: زرار «شارك الصورة» فوق، أو **اضغط مطوّلاً على الصورة** "
               "← مشاركة/حفظ، أو حمّلها وأرفقها.")

    # كل المقاسات
    with st.expander("📦 كل المقاسات في ملف واحد (ZIP)"):
        if st.button("جهّز الـ ZIP", use_container_width=True):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for sz in SIZES:
                    p_, _ = render_cached(kind, sz, fields_json, bytes(photo_bytes))
                    z.writestr(f"orange-{kind}-{sz}-{cid}.png", p_)
            st.session_state["ms_zip"] = buf.getvalue()
        if st.session_state.get("ms_zip"):
            st.download_button("⬇️ حمّل الـ ZIP", st.session_state["ms_zip"],
                               file_name=f"orange-{kind}-{cid}.zip",
                               mime="application/zip", use_container_width=True,
                               on_click=log_campaign, args=("zip",))
            st.caption("الـ ZIP بيتجهّز من النص الحالي — اضغط «جهّز» تاني بعد أي تعديل.")
