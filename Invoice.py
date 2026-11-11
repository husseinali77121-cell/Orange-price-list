# Invoice.py
# ============================================================
#  Orange Lab - Medical Test Invoice
#  Developed by Dr/Hussein Ali
#
#  التشغيل:  streamlit run Invoice.py
#  الاختبار: python3 test_price_utils.py   (قبل أي رفع)
# ============================================================

import json
import re
import uuid
from dataclasses import replace as dc_replace
from datetime import date, datetime, timedelta
from datetime import time as dtime
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Orange Lab - Invoice", page_icon="🍊", layout="wide")

st.markdown("""
<style>
.stActionButton {display:none !important;}
#MainMenu, footer {visibility:hidden !important;}
header[data-testid="stHeader"] {background:transparent !important; height:2.4rem !important;}
[data-testid="stToolbar"], [data-testid="stDecoration"] {display:none !important;}
div[data-testid="stVerticalBlock"] {gap:.55rem;}
.stButton>button {
  font-size:.82rem; padding:.32rem .35rem;
  white-space:normal; line-height:1.18; min-height:2.5rem;
}

/* الموبايل: أي صف فيه أزرار يفضل جنب بعض بدل ما يتفرد سطر لكل زرار */
div[data-testid="stHorizontalBlock"]:has(div[data-testid="stButton"]) {
  flex-wrap:nowrap !important; gap:.4rem !important;
}
div[data-testid="stHorizontalBlock"]:has(div[data-testid="stButton"]) > div[data-testid="column"],
div[data-testid="stHorizontalBlock"]:has(div[data-testid="stButton"]) > div[data-testid="stColumn"] {
  min-width:0 !important; flex:1 1 0 !important;
}
.ok-badge   {color:#0a7d33; font-weight:600;}
.bad-badge  {color:#c62828; font-weight:600;}
.warn-badge {color:#b26a00; font-weight:600;}
</style>
""", unsafe_allow_html=True)

from bundles import BUNDLES as BUNDLE_DEFS
from bundles import BUNDLE_CATEGORY, bundles_for
from labs_price_list import LABS_DB
from panels import (BRANCHES, DEFAULT_BRANCH, QUICK_PANELS, panel_bundle_name,
                    validate_panels)
from price_utils import (MATCH_ALIAS, MATCH_AMBIGUOUS, MATCH_EXACT,
                         MATCH_NOT_FOUND, MATCH_SUGGEST, build_index,
                         MAX_WA_URL, build_whatsapp_link_safe, build_whatsapp_message,
                         build_whatsapp_url, bundle_saving, check_add,
                         compute_totals, decode_quote_checked, encode_quote,
                         generate_quote_id, parse_bulk_tests, quote_age_hours,
                         format_phone_display, name_is_pdf_safe, norm,
                         reprice_saved_items, resolve_test, search_tests,
                         suggest_bundle_offers,
                         validate_patient_name, validate_phone)
from tracking import (LOST_SALE_REASONS, REFERRAL_SOURCES, WHATSAPP_SOURCE, customer_profile,
                      last_campaign_for, make_event, month_key, new_lead_id, phone_key,
                      summarize_events)
import replies as RP
import wa_inquiry as WI
from patient_prep import eta_text, prep_block
from wa_bridge import BRIDGE_ARIA, BRIDGE_CSS, make_token, parse_token, send_button_html
import campaigns as CP
import config_store
import offer_matcher as OM
from access import secret_bool, secret_float
from promotions import (PROMO_PATH, active_promotions, best_promo_for,
                        discount_pct_of, needs_approval, pin_ok)
from marketing import MARKETING_KINDS, build_marketing_message, share_url
from navigation import render_nav

try:                                   # كتالوج العروض (القائمة الترحيبية + الأرقام)
    import offers_catalog as OC
    HAS_CATALOG = True
except Exception:  # noqa: BLE001
    HAS_CATALOG = False

try:                                   # الصور محتاجة Pillow — لو مش موجود الفاتورة تكمّل من غيرها
    from marketing_templates import (SIZE_LABELS, SIZES, render_template,
                                     to_jpeg_bytes, to_png_bytes)
    from share_widget import share_button_html
    HAS_IMAGES = True
except Exception:  # noqa: BLE001
    HAS_IMAGES = False
from voice import VOICE_ARIA, mic_html, split_voice_command
from github_store import (GithubEventStore, GithubStoreError, events_path,
                          read_events_range, store_from_secrets)

CURRENCY = "ج.م"
LAB_NAME_AR = "معمل أورانج للتحاليل الطبية"
MAPS_URL = "https://maps.app.goo.gl/vLdtTk9KctLXtpE4A?g_st=ac"

# TODO: حط هنا لينك التطبيق المنشور فعلياً على Streamlit Cloud
# (من غير كده زرار "حفظ العرض" هيولّد لينك مايفتحش صح)
APP_URL = "https://REPLACE-WITH-YOUR-STREAMLIT-APP-URL"
REVIEW_URL = ""   # لينك تقييم المعمل على Google Maps — بيظهر في رسالة «طلب تقييم»


# ------------------------------------------------------------
# Load + startup self-check
# ------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def load_index():
    return build_index(LABS_DB, BUNDLE_DEFS, BUNDLE_CATEGORY)


@st.cache_data(show_spinner=False)
def load_panel_report():
    return validate_panels(load_index(), resolve_test)


IDX = load_index()
BROKEN_PANELS = load_panel_report()


@st.cache_resource(show_spinner=False)
def get_event_store():
    """
    None لو التتبّع مش متظبط في secrets — البرنامج بيكمل شغل عادي
    من غيره، التسويق مش المفروض يوقف الفاتورة أبداً.
    """
    return store_from_secrets(st.secrets)


def get_quote_secret() -> str:
    """مفتاح توقيع لينكات العروض (secrets: quote_secret). فاضي = التوقيع مقفول."""
    try:
        return str(st.secrets.get("quote_secret", "") or "")
    except Exception:
        return ""


QUOTE_SECRET = get_quote_secret()


def _secret_str(key: str) -> str:
    try:
        return str(st.secrets.get(key, "") or "")
    except Exception:
        return ""


QUOTE_TTL_HOURS = secret_float(st.secrets, "quote_ttl_hours", 48) or 48   # لينك العرض بيقفل بعدها
STORE_CONTACTS = secret_bool(st.secrets, "store_contacts")              # تخزين اسم/رقم في «تم الإرسال»
# حد الخصم بقى من الإعدادات (Branches ← Policy) — الافتراضي 50% (كان 20% في Secrets)
DISCOUNT_PIN = _secret_str("discount_approval_pin")                     # كود موافقة المسؤول
CAMPAIGN_RE = re.compile(r"^OL-\d{6}-[A-Z0-9]{4}$")


@st.cache_data(ttl=120, show_spinner=False)
def load_promos():
    """عروض «إدارة العروض» (promotions/promotions.json) — فاضية لو التتبّع مش متظبط."""
    s_ = store_from_secrets(st.secrets)
    if not s_:
        return []
    try:
        data, _ = s_.read(PROMO_PATH)
        return data if isinstance(data, list) else []
    except GithubStoreError:
        return []


@st.cache_data(ttl=120, show_spinner=False)
def load_config():
    """إعدادات الإدارة: بيانات الفروع، حملات المزايا، المناطق، قايمة الموظفين (config_store)."""
    return config_store.load(store_from_secrets(st.secrets))


@st.cache_data(show_spinner=False, max_entries=12)
def packages_card(rows_json: str, size: str, phone: str):
    """صورة «عروض الباقات» بقالب Orange — (PNG, JPG). الأسعار من القائمة الحالية."""
    rows = json.loads(rows_json)
    items = "\n".join(
        f"{r['name']} — {r['price']:,}" + (f" (وفّر {r['saving']:,})" if r["saving"] > 0 else "")
        for r in rows)
    img = render_template("offer", size, {
        "title_small": "عروض", "title_big": "الباقات", "subtitle": "اختار الباقة المناسبة ليك",
        "badge_mode": "none", "list_title": "الأسعار بالجنيه", "items": items,
        "cta": "احجز الآن", "photo": "sugar", "phone": phone, "show_trust": True})
    return to_png_bytes(img), to_jpeg_bytes(img, 90)


@st.cache_data(show_spinner=False, max_entries=24)
def catalog_card(offer_id: str, size: str, phone: str):
    """صورة عرض من الكتالوج بقالب Orange — (PNG, JPG)."""
    f = OC.studio_fields(OC.get(offer_id))
    f.pop("template", None)
    f.update({"phone": phone, "photo": "sugar"})
    img = render_template("offer", size, f)
    return to_png_bytes(img), to_jpeg_bytes(img, 90)


@st.cache_data(ttl=300, show_spinner=False)
def recent_events():
    """آخر 6 شهور أحداث — لمعرفة عميل متكرر/موقوف بالبصمة (بيتحدّث كل 5 دقايق)."""
    s_ = store_from_secrets(st.secrets)
    if not s_:
        return []
    now_ = datetime.now()
    y, m = now_.year, now_.month - 5
    while m < 1:
        m += 12
        y -= 1
    try:
        return read_events_range(s_, f"{y:04d}-{m:02d}", month_key())
    except GithubStoreError:
        return []


# ------------------------------------------------------------
# Session state
# ------------------------------------------------------------

DEFAULTS = {
    "items": [],              # [{uid,name,price,result_days,collection_notes,category,source}]
    "pending": None,          # Resolution محتاجة تأكيد
    "conflict": None,         # (Conflict, TestRec) محتاجة قرار
    "pending_panel": None,    # panel محتاج اختيار باقة/مفرّق
    "bulk": None,             # نتيجة تحليل قائمة ملزوقة
    "branch": DEFAULT_BRANCH,
    "prefer_bundle": True,
    "discount_type": "Percentage",
    "discount_value": 0.0,
    "disc_gen": 0,            # بيتغيّر عشان خانة الخصم تتبني من جديد (reset/تغيير النوع)
    "voice_gen": 0,           # بيتغيّر عشان خانة الصوت تتفضّى بعد كل أمر
    "p_name": "",
    "p_phone": "",
    "p_doctor": "",
    "p_date": date.today(),
    "wa_lang": "ar",
    "flash": [],
    "quote_id": "",           # OR-YYMMDD-NNNN — تتبّع داخلي بس
    "dismissed_offers": [],   # مفاتيح باقات اتقفلت في السيشن دي
    "saved_link": "",         # آخر لينك "حفظ العرض" اتولّد
    "saved_at": "",           # وقت توليده (ISO) — لحساب صلاحية الـ 48 ساعة
    "referral_source": REFERRAL_SOURCES[-1],
    "campaign_id": "",        # كود حملة Marketing Studio (اختياري) — بيربط العرض بالحملة
    "staff_name": "",         # الموظف (للمقارنة في الداشبورد) — بيفضل بين الفواتير
    "area": "",               # منطقة العميل (لحملات المزايا زي الزيارة المجانية)
    "visit_type": "lab",      # lab | home
    "parent_quote": "",       # عرض قديم اتعمل منه الجديد (استرجاع عميل بموافقة الإدارة)
    "inquiry_ts": "",         # وقت رسالة العميل على الواتساب (من المحادثة الملزوقة) — لسرعة الرد
    "bridge_gen": 0,          # بيتغيّر عشان خانة جسر «إرسال + متابعة» تتفضّى
    "bulk_src": "",           # "wa" = القائمة جاية من استفسار واتساب (المراجعة بتظهر جوه صندوقه)
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


def flash(kind, msg):
    st.session_state.flash.append((kind, msg))


# ---- استرجاع عرض محفوظ من لينك "حفظ العرض" (Save Quote) ----
if not st.session_state.get("_quote_link_checked"):
    st.session_state["_quote_link_checked"] = True
    q = st.query_params.get("q")
    if q:
        data, _qstatus = decode_quote_checked(q, QUOTE_SECRET, max_age_hours=QUOTE_TTL_HOURS)
        if data:
            # السعر المخزّن في اللينك مش مصدر حقيقة — بنعيد التسعير من القائمة الحالية
            _qitems, _qchg, _qmiss = reprice_saved_items(data.get("items", []), IDX)
            # عرض ترويجي شغّال دلوقتي = السعر الحالي (والمنتهي بيرجع لسعر القائمة)
            _promo_applied = []
            _pm_all = load_promos()
            for _it in _qitems:
                _bp = best_promo_for(_pm_all, _it["name"], st.session_state.branch, date.today())
                if _bp and _bp["promo_price"] < int(_it["price"]):
                    _it["price"] = _bp["promo_price"]
                    _promo_applied.append(f"{_it['name']} ({_bp['promo_price']:,})")
            st.session_state["items"] = [
                {"uid": uuid.uuid4().hex[:8], **it, "source": "saved_quote"}
                for it in _qitems
            ]
            st.session_state["p_name"] = data.get("name", "")
            st.session_state["p_phone"] = data.get("phone", "")
            st.session_state["p_doctor"] = data.get("doctor", "")
            try:
                st.session_state["p_date"] = date.fromisoformat(data.get("date_iso", ""))
            except Exception:
                pass
            st.session_state["discount_type"] = data.get("dtype", "Percentage")
            st.session_state["discount_value"] = data.get("dval", 0.0)
            st.session_state["quote_id"] = data.get("id", "")
            _cid = str(data.get("cid", "") or "")
            st.session_state["campaign_id"] = _cid if CAMPAIGN_RE.match(_cid) else ""
            st.session_state["area"] = str(data.get("area", "") or "")
            st.session_state["visit_type"] = "home" if data.get("vt") == "home" else "lab"
            st.session_state["parent_quote"] = str(data.get("par", "") or "")
            if data.get("appr"):           # عرض استرجاع: خصمه معتمد من الإدارة (اللينك موقّع ومشفّر)
                try:
                    st.session_state[f"_appr_{data.get('id', '')}_{int(round(float(data.get('dval', 0))))}"] = True
                except (TypeError, ValueError):
                    pass
            flash("info", f"📂 اتفتح عرض محفوظ: {data.get('id','')}"
                  + (f" — مرتبط بالعرض {data['par']}" if data.get("par") else ""))
            if _promo_applied:
                flash("info", "🎁 اتطبّق سعر العرض الشغّال: " + "، ".join(_promo_applied))
            if _qchg:
                flash("warning", "💱 الأسعار اتحدّثت من القائمة الحالية: " + "، ".join(
                    f"{n} ({o:,} ← {pr:,})" for n, o, pr in _qchg))
            if _qmiss:
                flash("warning", "⚠️ مش موجودين في القائمة دلوقتي (لسه بسعرهم القديم): "
                                 + "، ".join(_qmiss))
            if _qstatus == "unverified":
                flash("warning", "🔓 توقيع اللينكات مش متفعّل — سلامة اللينك ده ماتتأكدتش")
        else:
            flash("error", {
                "unsigned": "⚠️ لينك قديم من غير توقيع — اتقفل لحماية البيانات، اعمل العرض من جديد",
                "expired": f"⏱️ لينك العرض انتهت صلاحيته (أكتر من {QUOTE_TTL_HOURS:.0f} ساعة) — "
                           "اعمل عرض جديد بالأسعار الحالية",
            }.get(_qstatus, "⚠️ لينك العرض ده تالف أو معدَّل — مش هينفتح"))

if not st.session_state["quote_id"]:
    st.session_state["quote_id"] = generate_quote_id()


def has_test(name: str) -> bool:
    from price_utils import norm
    return any(norm(i["name"]) == norm(name) for i in st.session_state["items"])


def add_item(name, price, result_days=None, collection_notes="", category="",
             source="manual") -> bool:
    if has_test(name):
        return False
    st.session_state["items"].append({
        "uid": uuid.uuid4().hex[:8],
        "name": name, "price": int(price), "result_days": result_days,
        "collection_notes": collection_notes or "", "category": category,
        "source": source,
    })
    return True


def add_record(rec, source="manual") -> bool:
    return add_item(rec.name, rec.price, rec.result_days, rec.collection_notes,
                    rec.category, source)


def try_add(rec, source="manual") -> str:
    """
    إضافة محمية من التعارض.
    بترجّع: "added" | "duplicate" | "conflict"
    """
    if has_test(rec.name):
        return "duplicate"
    c = check_add(st.session_state["items"], rec, IDX)
    if c:
        st.session_state.conflict = (c, rec, source)
        return "conflict"
    add_record(rec, source)
    return "added"


def replace_with_bundle(rec, names, source="manual"):
    """يشيل المفرّق ويحط الباقة مكانه."""
    drop = {norm(n) for n in names}
    st.session_state["items"] = [i for i in st.session_state["items"]
                                 if norm(i["name"]) not in drop]
    add_record(rec, source)

def add_many(recs, source):
    """
    إضافة مجموعة تحاليل مع حماية الدفع مرتين.

    الباقات بتتضاف الأول عن قصد: كده لو القائمة فيها باقة ومكوّن
    منها، المكوّن هيتمسك كـ covered ويتخطى بدل ما يتحاسب مرتين.

    covered    -> يتخطى (قرار محسوم، العميل دافع تمنه في الباقة)
    supersedes -> ماينفعش يتقرر جماعي (فيه فلوس) -> يتأجل للبوابة اليدوية

    بترجّع: (added, dup, covered, deferred)
    """
    # سطرين مختلفين ممكن يوصّلوا لنفس التحليل ("دهون" و "Lipid Profile")
    seen, uniq = set(), []
    for rec in sorted(recs, key=lambda r: not r.is_bundle):
        if norm(rec.name) in seen:
            continue
        seen.add(norm(rec.name))
        uniq.append(rec)

    added, dup, covered, deferred = [], [], [], []
    for rec in uniq:
        if has_test(rec.name):
            dup.append(rec.name)
            continue
        c = check_add(st.session_state["items"], rec, IDX)
        if c and c.kind == "covered":
            covered.append((rec.name, c.bundle, rec.price))
            continue
        if c and c.kind == "supersedes":
            deferred.append(rec.name)
            continue
        add_record(rec, source)
        added.append(rec.name)
    return added, dup, covered, deferred


def add_panel_tests(names, source):
    """أسماء -> سجلات مؤكدة -> add_many."""
    recs = []
    for t in names:
        r = resolve_test(t, IDX)
        if r.is_confident:
            recs.append(r.best)
    return add_many(recs, source)


def flash_panel_result(p, added, dup, covered, deferred=()):
    if added:
        flash("success", f"تمت إضافة {len(added)} تحليل من {p}")
    if dup:
        flash("warning", f"موجودين قبل كده: {', '.join(dup)}")
    if covered:
        saved = sum(pr for _, _, pr in covered)
        bundle = covered[0][1]
        flash("warning",
              f"⛔ اتخطّى {', '.join(n for n, _, _ in covered)} — "
              f"داخلين في باقة {bundle} الموجودة في الفاتورة. "
              f"وفّرت على العميل {saved:,} {CURRENCY}")
    if deferred:
        flash("warning",
              f"📦 {', '.join(deferred)} ما اتضافتش — بتغطي تحاليل مفرّقة "
              f"موجودة في الفاتورة. ضيفها من خانة البحث عشان تشوف الاستبدال")


def bulk_review(BULK):
    """مراجعة قائمة تحاليل (ملزوقة / من الصوت / من استفسار واتساب): المؤكد متعلّم، والمشكوك فيه بيتختار."""
    st.caption(f"مؤكد {len(BULK['confident'])}  ·  محتاج اختيار "
               f"{len(BULK['choose'])}  ·  مش متعرف عليه "
               f"{len(BULK['missing'])}")
    chosen = []

    if BULK["confident"]:
        st.markdown("**✅ اتعرف عليها — شيل علامة أي حاجة مش عايزها**")
        for i, (t, rec) in enumerate(BULK["confident"]):
            tag = " 📦" if rec.is_bundle else ""
            lbl = f"{rec.name}{tag} — {rec.price:,} {CURRENCY}"
            if t.strip().lower() != rec.name.lower():
                lbl += f"   ‹ {t}"
            if st.checkbox(lbl, value=True, key=f"bulk_ok_{i}"):
                chosen.append(rec)

    if BULK["choose"]:
        st.markdown("**🔎 محتاجة تحديد منك**")
        for i, (t, cands, why) in enumerate(BULK["choose"]):
            opts = ["— تجاهل —"] + [f"{c.name} · {c.price:,}" for c in cands]
            pick = st.selectbox(f"«{t}» — {why}", opts, key=f"bulk_pick_{i}")
            if pick != opts[0]:
                chosen.append(cands[opts.index(pick) - 1])

    if BULK["missing"]:
        st.markdown("**⛔ مش لاقيلها مقابل — ضيفها يدوي من خانة البحث**")
        st.code("\n".join(BULK["missing"]), language=None)

    g1, g2 = st.columns(2)
    with g1:
        if st.button(f"➕ أضف المختار ({len(chosen)})",
                     use_container_width=True, type="primary",
                     disabled=not chosen, key="bulk_add"):
            wa = st.session_state.get("bulk_src") == "wa"
            res4 = add_many(chosen, "whatsapp" if wa else "bulk")
            flash_panel_result("استفسار الواتساب" if wa else "القائمة الملزوقة", *res4)
            st.session_state.bulk = None
            st.session_state.bulk_src = ""
            st.rerun()
    with g2:
        if st.button("🗑️ امسح القائمة", use_container_width=True, key="bulk_clear"):
            st.session_state.bulk = None
            st.session_state.bulk_src = ""
            st.rerun()


# ------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ الإعدادات")
    st.session_state.branch = st.selectbox(
        "الفرع", BRANCHES, index=BRANCHES.index(st.session_state.branch))
    st.session_state.prefer_bundle = st.toggle(
        "استخدم سعر الباقة لو أرخص", value=st.session_state.prefer_bundle,
        help="مثال: Lipid profile باقة 700 بدل 950 مفرّق")
    st.session_state.wa_lang = st.radio("لغة رسالة الواتساب", ["ar", "en"],
                                        horizontal=True,
                                        format_func=lambda x: "عربي" if x == "ar" else "English")

    st.divider()
    st.markdown("### 🩺 فحص النظام")
    st.success(f"{len(IDX.records):,} صف / {len(IDX.by_key):,} اسم فريد / "
               f"{len(LABS_DB)} قسم")
    st.info(f"📦 {len(bundles_for(st.session_state.branch))} باقة مدموجة "
            f"في قائمة الأسعار")
    if BROKEN_PANELS:
        st.error(f"⛔ {len(BROKEN_PANELS)} panel مكسور — أسماء مش موجودة في قائمة الأسعار")
        for p, bad in BROKEN_PANELS.items():
            with st.expander(p):
                for t, s, hint in bad:
                    st.write(f"`{t}` → **{s}** · {hint}")
    else:
        st.success(f"✅ كل الـ {len(QUICK_PANELS)} panel أسماؤهم مطابقة")

    st.divider()
    st.caption("👨‍💻 Developed by Dr/Hussein Ali")
    st.caption("📊 تتبّع العروض: " +
              ("✅ مفعّل" if get_event_store() else "⚪ مش متظبط (secrets)"))


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

st.markdown("## 🍊 Orange Lab — فاتورة تحاليل")
render_nav(st, "Invoice.py")
st.caption(f"🧾 Quote ID: `{st.session_state.quote_id}`  ·  للمتابعة الداخلية بس، "
           f"مش بتتحط في رسالة العميل")

for kind, msg in st.session_state.flash:
    getattr(st, kind)(msg)
st.session_state.flash = []


# ------------------------------------------------------------
# 0) 💬 استفسار واتساب — الموظف يلزق المحادثة: الاسم والرقم والتحاليل والمنطقة ونية العميل
#    بيتملوا لوحدهم، والمصدر بيبقى WhatsApp، ووقت الرسالة بيتسجّل (سرعة الرد في الداشبورد).
#    التحاليل بتروح لمراجعة سريعة (المؤكد متعلّم) — نفس قاعدة «مفيش تخمين».
# ------------------------------------------------------------

CFG = load_config()
DISCOUNT_LIMIT_PCT = config_store.discount_limit(CFG)    # 50% افتراضي — Branches ← Policy
_BRANCH_NAMES = [(CFG["branches"].get(b) or {}).get("name_ar", b) for b in BRANCHES]
_BUNDLE_COMPONENTS = {b["name"]: list(b.get("components", [])) for b in BUNDLE_DEFS}


def _local_phone(e164: str) -> str:
    return "0" + e164[2:] if e164.startswith("20") and len(e164) == 12 else "+" + e164


with st.expander("💬 استفسار واتساب — الصق المحادثة (الاسم والرقم والتحاليل بيتملوا لوحدهم)",
                 expanded=not st.session_state["items"] or st.session_state.get("bulk_src") == "wa"):
    with st.form("wa_form", clear_on_submit=True):
        wa_raw = st.text_area(
            "محادثة العميل", height=110, label_visibility="collapsed", key="wa_raw",
            placeholder="انسخ رسايل العميل من الواتساب والزقها هنا زي ما هي:\n"
                        "[10:15, 11/11/2026] Mona Ahmed: بكام صورة دم وفيتامين د؟ أنا في زايد وعايزة سحب منزلي")
        wa_go = st.form_submit_button("⚡ حلّل الاستفسار", use_container_width=True, type="primary")
    if wa_go and (wa_raw or "").strip():
        A = WI.analyze_inquiry(wa_raw, IDX, areas=CFG["areas"])
        got = []
        if A["name"] and not st.session_state.p_name.strip():
            st.session_state.p_name = A["name"]
            got.append(f"الاسم: {A['name']}")
        if A["phone"] and not st.session_state.p_phone.strip():
            st.session_state.p_phone = _local_phone(A["phone"])
            got.append("الرقم")
        if st.session_state.referral_source == REFERRAL_SOURCES[-1] and WHATSAPP_SOURCE in REFERRAL_SOURCES:
            st.session_state.referral_source = WHATSAPP_SOURCE
            got.append("المصدر: واتساب")
        if A["home_visit"] and st.session_state.visit_type != "home":
            st.session_state.visit_type = "home"
            got.append("🏠 زيارة منزلية")
        if A["area"] and not st.session_state.area:
            st.session_state.area = A["area"]
            got.append(f"المنطقة: {A['area']}")
        if A["inquiry_ts"]:
            st.session_state.inquiry_ts = A["inquiry_ts"].isoformat(timespec="seconds")
        T = A["tests"]
        n_t = len(T["confident"]) + len(T["choose"])
        if n_t or T["missing"]:
            st.session_state.bulk = T
            st.session_state.bulk_src = "wa"
        if A["offer_no"] and HAS_CATALOG and OC.get(str(A["offer_no"])):
            st.session_state["cat_pick"] = str(A["offer_no"])
            got.append(f"العميل كتب رقم العرض {A['offer_no']} (افتح «عروض المعمل بالرقم»)")
        st.session_state["_wa_last"] = {"intents": A["intents"], "text": A["customer_text"][:1500],
                                        "has_media": A["has_media"], "tests": n_t}
        if n_t:
            got.append(f"{n_t} تحليل للمراجعة تحت")
        flash("success" if got else "info",
              "💬 " + (" · ".join(got) if got else "مفيش تحاليل في الرسالة — شوف الرد المقترح"))
        st.rerun()

    if st.session_state.get("bulk_src") == "wa" and st.session_state.bulk:
        st.markdown("**🧪 التحاليل اللي في رسالة العميل**")
        bulk_review(st.session_state.bulk)

    _W = st.session_state.get("_wa_last")
    if _W:
        if _W["has_media"] and not _W["tests"]:
            st.info("📎 العميل بعت صورة (غالباً روشتة) — افتحها وضيف التحاليل بالبحث أو الصوت أو «الصق قائمة».")
        _sugs = RP.suggested(_W["intents"])
        if _sugs:
            st.markdown("**💬 الرد المقترح** — " + " · ".join(f"«{x['keyword']}»" for x in _W["intents"][:4]))
            _rid = st.radio("الرد", [t["id"] for t in _sugs], horizontal=True, key="wa_sug",
                            format_func=lambda i: RP.get(i)["title"], label_visibility="collapsed")
            _tpl = RP.get(_rid) or _sugs[0]
            _its = st.session_state["items"]
            _tn = compute_totals(_its, st.session_state.discount_value, st.session_state.discount_type)
            _bi = CFG["branches"].get(st.session_state.branch)
            _names = [i["name"] for i in _its]
            _txt0 = RP.render_reply(
                _tpl, "short", name=st.session_state.p_name, lab=LAB_NAME_AR,
                branch_text=config_store.branch_block(_bi) if (_bi and "{branch}" in _tpl["short"]) else "",
                quote_text=RP.quote_block(_names, _tn["total"], discount=_tn["discount"]) if _its else "",
                prep_text=prep_block(_names, _BUNDLE_COMPONENTS) if _its else "",
                eta_text=eta_text([i.get("result_days") for i in _its]),
                cta_text=RP.booking_cta(_BRANCH_NAMES) if _its else "")
            _rtxt = st.text_area("نص الرد (تقدر تعدّله)", value=_txt0, height=150,
                                 key=f"wa_rtxt_{_tpl['id']}_{len(_its)}_{_tn['total']}")
            _rp = validate_phone(st.session_state.p_phone) if st.session_state.p_phone.strip() else None
            _ra, _rb = st.columns(2)
            _ra.link_button("📲 ابعت الرد ده", share_url(_rtxt, _rp.value if (_rp and _rp.ok) else ""),
                            use_container_width=True)
            if _rb.button("💬 افتح في Replies", key="wa_to_replies", use_container_width=True):
                st.session_state["_rp_prefill"] = {"rp_name": st.session_state.p_name,
                                                   "rp_phone": st.session_state.p_phone,
                                                   "rp_reply": _tpl["id"], "rp_msg": _W["text"]}
                if hasattr(st, "switch_page"):
                    st.switch_page("pages/8_Replies.py")

        # العميل سأل ومابعتش تحاليل لسه: سجّله «مستفسر» عشان مايضيعش (بيظهر في Follow-up)
        _lp = validate_phone(st.session_state.p_phone) if st.session_state.p_phone.strip() else None
        if not st.session_state["items"] and _lp and _lp.ok and get_event_store():
            _lk = f"_lead_{_lp.value}"
            _fh = config_store.followup_hours(CFG) or 24
            if st.session_state.get(_lk):
                st.caption("🟡 اتسجّل كمستفسر — هيظهر في Follow-up لو مارجعش بالروشتة، وبيتقفل لوحده لما تعمله عرض.")
            elif st.button(f"🟡 سجّل كمستفسر + متابعة بعد {_fh} ساعة (لو مابعتش الروشتة)", key="wa_lead",
                           use_container_width=True):
                try:
                    _nm = validate_patient_name(st.session_state.p_name)
                    get_event_store().append(events_path(month_key()), make_event(
                        "lead", new_lead_id(), branch=st.session_state.branch,
                        referral_source=WHATSAPP_SOURCE, phone_key=phone_key(_lp.value, QUOTE_SECRET),
                        contact=({"name": _nm.value if _nm.ok else "", "phone": _lp.value} if STORE_CONTACTS else None),
                        staff=st.session_state.staff_name, visit_type=st.session_state.visit_type,
                        area=st.session_state.area,
                        note=", ".join(x["intent"] for x in _W["intents"])[:80],
                        meta={"next_due": (datetime.now() + timedelta(hours=_fh)).isoformat(timespec="seconds"),
                              **({"inquiry_ts": st.session_state.inquiry_ts} if st.session_state.inquiry_ts else {})}))
                    st.session_state[_lk] = True
                    flash("success", "🟡 اتسجّل كمستفسر — المتابعة هتظهر في Follow-up في ميعادها")
                except GithubStoreError as e:
                    flash("error", f"مقدرتش أسجّل: {e}")
                st.rerun()
        if st.button("✖️ اقفل الاستفسار", key="wa_close"):
            st.session_state["_wa_last"] = None
            if st.session_state.get("bulk_src") == "wa":
                st.session_state.bulk, st.session_state.bulk_src = None, ""
            st.rerun()



# ------------------------------------------------------------
# 1) Patient info + validation
# ------------------------------------------------------------

st.markdown("#### 👤 بيانات العميل")
c1, c2 = st.columns(2)
with c1:
    st.session_state.p_name = st.text_input(
        "اسم العميل *", value=st.session_state.p_name, placeholder="Ahmed Ali Hassan")
    st.session_state.p_phone = st.text_input(
        "رقم الموبايل *", value=st.session_state.p_phone, placeholder="01012345678")
with c2:
    st.session_state.p_doctor = st.text_input(
        "الطبيب المحوِّل", value=st.session_state.p_doctor, placeholder="Dr. Sameh")
    st.session_state.p_date = st.date_input("التاريخ", value=st.session_state.p_date)

st.session_state.referral_source = st.selectbox(
    "من فين عرف عن المعمل؟", REFERRAL_SOURCES,
    index=REFERRAL_SOURCES.index(st.session_state.referral_source),
    help="بيساعدنا نعرف أي قناة تسويقية بتجيب عملاء أكتر")

st.session_state.campaign_id = st.text_input(
    "كود الحملة (اختياري)", value=st.session_state.campaign_id, placeholder="OL-261105-AB12",
    help="لو العميل جه من إعلان عملته من Marketing Studio — اكتب الكود اللي على التصميم/النص"
).strip().upper()
CAMPAIGN = st.session_state.campaign_id if CAMPAIGN_RE.match(st.session_state.campaign_id) else ""
if st.session_state.campaign_id and not CAMPAIGN:
    st.caption("⚠️ الشكل المتوقع للكود: OL-YYMMDD-XXXX — مش هيتسجّل بالشكل ده")

LINKS = config_store.resolve_links(CFG, st.secrets)       # لينكات قابلة للتعديل من صفحة Branches ← Links
APP_URL = LINKS["app_url"] or APP_URL
REVIEW_URL = LINKS["review_url"] or REVIEW_URL
_staff_opts = ["—"] + list(CFG["staff"])
if CFG["staff"]:
    _cur = st.session_state.staff_name if st.session_state.staff_name in _staff_opts else "—"
    _pick_staff = st.selectbox("الموظف", _staff_opts, index=_staff_opts.index(_cur))
    st.session_state.staff_name = "" if _pick_staff == "—" else _pick_staff
else:
    st.session_state.staff_name = st.text_input("اسم الموظف (اختياري)", value=st.session_state.staff_name,
                                                help="بيظهر في مقارنة الأداء بالداشبورد").strip()
_ar1, _ar2 = st.columns(2)
_areas = ["—"] + list(CFG["areas"])
_cura = st.session_state.area if st.session_state.area in _areas else "—"
_pick_area = _ar1.selectbox("منطقة العميل", _areas, index=_areas.index(_cura),
                            help="لحملات زي الزيارة المنزلية المجانية (6 أكتوبر والشيخ زايد)")
st.session_state.area = "" if _pick_area == "—" else _pick_area
st.session_state.visit_type = _ar2.radio("نوع الزيارة", ["lab", "home"], horizontal=True,
                                         index=0 if st.session_state.visit_type != "home" else 1,
                                         format_func=lambda k: {"lab": "🏥 في المعمل", "home": "🏠 زيارة منزلية"}[k])

name_chk = validate_patient_name(st.session_state.p_name)
phone_chk = validate_phone(st.session_state.p_phone)
PK = phone_key(phone_chk.value, QUOTE_SECRET) if phone_chk.ok else ""
CUSTOMER = customer_profile(recent_events(), PK) if PK else None

# 🎯 العميل وصله إعلان من الاستوديو خلال 14 يوم ← كود الحملة بيتربط تلقائي (مرة واحدة لكل عرض)
_ak = f"_camp_auto_{st.session_state.quote_id}"
if PK and not CAMPAIGN and not st.session_state.get(_ak):
    st.session_state[_ak] = True
    _cid = last_campaign_for(recent_events(), PK)
    if _cid and CAMPAIGN_RE.match(_cid):
        st.session_state.campaign_id = CAMPAIGN = _cid
        flash("info", f"🎯 العميل ده وصله إعلان {_cid} من الاستوديو — اتربط بالعرض تلقائي "
                      "(تقدر تمسحه من خانة «كود الحملة»)")

v1, v2 = st.columns(2)
with v1:
    if not st.session_state.p_name:
        st.caption("اكتب اسم العميل")
    elif name_chk.ok:
        st.markdown(f"<span class='ok-badge'>✅ {name_chk.value}</span>",
                    unsafe_allow_html=True)
        for w in name_chk.warnings:
            st.markdown(f"<span class='warn-badge'>⚠️ {w}</span>", unsafe_allow_html=True)
    else:
        for e in name_chk.errors:
            st.markdown(f"<span class='bad-badge'>❌ {e}</span>", unsafe_allow_html=True)
with v2:
    if not st.session_state.p_phone:
        st.caption("الرقم مطلوب لإرسال الواتساب")
    elif phone_chk.ok:
        st.markdown(f"<span class='ok-badge'>✅ {format_phone_display(phone_chk.value)}"
                    f"</span>", unsafe_allow_html=True)
        for w in phone_chk.warnings:
            st.markdown(f"<span class='warn-badge'>⚠️ {w}</span>", unsafe_allow_html=True)
    else:
        for e in phone_chk.errors:
            st.markdown(f"<span class='bad-badge'>❌ {e}</span>", unsafe_allow_html=True)

if CUSTOMER and CUSTOMER["optout"]:
    st.warning("🚫 العميل ده طلب إيقاف الرسائل التسويقية والمتابعة — ماتبعتلوش رسائل غير عرض السعر اللي طلبه.")
elif CUSTOMER and CUSTOMER["label"] != "New":
    st.caption(f"👤 عميل {CUSTOMER['label']} — {CUSTOMER['quotes']} عرض قبل كده، "
               f"اتباع له {CUSTOMER['converted']} مرة"
               + (f" بإجمالي {CUSTOMER['revenue']:,} {CURRENCY}" if CUSTOMER["revenue"] else ""))

st.divider()


# ------------------------------------------------------------
# 2) Quick panels
# ------------------------------------------------------------

_promos_now = active_promotions(load_promos(), st.session_state.branch, date.today())
if _promos_now:
    with st.expander(f"🎁 عروض شغّالة دلوقتي ({len(_promos_now)})"):
        for _p in _promos_now:
            pa, pb = st.columns([3, 1])
            pa.markdown(f"**{_p['name']}** — {_p['target']}: ~~{_p['original_price']:,}~~ → "
                        f"**{_p['promo_price']:,}** {CURRENCY}")
            if pb.button("➕ أضف", key=f"promo_{_p['id']}", use_container_width=True):
                _prec = resolve_test(_p["target"], IDX).best
                if _prec:
                    _pres = try_add(dc_replace(_prec, price=_p["promo_price"]), source=f"promo:{_p['id']}")
                    if _pres == "added":
                        flash("success", f"🎁 اتضاف {_prec.name} بسعر العرض {_p['promo_price']:,}")
                    elif _pres == "duplicate":
                        flash("info", f"{_prec.name} موجود في الفاتورة بالفعل")
                st.rerun()

st.markdown("#### ⚡ الإدخال السريع")

PANEL_COLS = 2                      # اتنين في السطر - أوفر في المساحة على الموبايل
panel_names = [p for p in QUICK_PANELS if p not in BROKEN_PANELS]
for row in range(0, len(panel_names), PANEL_COLS):
    cols = st.columns(PANEL_COLS)
    for j, p in enumerate(panel_names[row:row + PANEL_COLS]):
        i = row + j
        with cols[j]:
            if st.button(p, use_container_width=True, key=f"pnl_{i}"):
                bname = panel_bundle_name(p, st.session_state.branch)
                brec = resolve_test(bname, IDX).best if bname else None
                itemized = sum(resolve_test(t, IDX).best.price
                               for t in QUICK_PANELS[p]["tests"])
                if brec and st.session_state.prefer_bundle and brec.price <= itemized:
                    st.session_state.pending_panel = p
                else:
                    res4 = add_panel_tests(QUICK_PANELS[p]["tests"], p)
                    flash_panel_result(p, *res4)
                st.rerun()

# اختيار باقة أو مفرّق
if st.session_state.pending_panel:
    p = st.session_state.pending_panel
    brec = resolve_test(panel_bundle_name(p, st.session_state.branch), IDX).best
    itemized, saving = bundle_saving(brec, IDX)
    st.info(f"**{p}** — الباقة أوفر")
    b1, b2, b3 = st.columns([2, 2, 1])
    with b1:
        lbl = (f"📦 باقة: {brec.price:,} {CURRENCY}"
               + (f"  (توفير {saving:,})" if saving > 0 else ""))
        if st.button(lbl, use_container_width=True, type="primary"):
            res = try_add(brec, source=p)
            st.session_state.pending_panel = None
            if res == "added":
                flash("success", f"تمت إضافة باقة {brec.name}")
            elif res == "duplicate":
                flash("warning", f"باقة {brec.name} موجودة بالفعل")
            st.rerun()
    with b2:
        if st.button(f"🔬 مفرّق: {itemized:,} {CURRENCY}", use_container_width=True):
            res4 = add_panel_tests(QUICK_PANELS[p]["tests"], p)
            st.session_state.pending_panel = None
            flash_panel_result(p, *res4)
            st.rerun()
    with b3:
        if st.button("إلغاء", use_container_width=True):
            st.session_state.pending_panel = None
            st.rerun()

st.divider()


# ------------------------------------------------------------
# 3) Add test — with name verification gate
# ------------------------------------------------------------

st.markdown("#### ➕ إضافة تحليل")

with st.form("add_form", clear_on_submit=True):
    fc1, fc2 = st.columns([4, 1])
    with fc1:
        q = st.text_input("اسم التحليل", placeholder="cbc / sugar / vit d / ferritin",
                          label_visibility="collapsed")
    with fc2:
        submitted = st.form_submit_button("تحقّق", use_container_width=True)

if submitted and q.strip():
    r = resolve_test(q, IDX)
    if r.status in (MATCH_EXACT, MATCH_ALIAS):
        res = try_add(r.best)
        if res == "added":
            tag = " 📦 باقة" if r.best.is_bundle else ""
            flash("success", f"✅ {r.best.name}{tag} — {r.best.price:,} {CURRENCY}"
                             + (f"  ({r.reason})" if r.status == MATCH_ALIAS else ""))
        elif res == "duplicate":
            flash("warning", f"⚠️ {r.best.name} موجود بالفعل في الفاتورة")
        st.session_state.pending = None
    else:
        st.session_state.pending = r
    st.rerun()

# بوابة التأكيد — مفيش إضافة تلقائية لأي اسم غير مؤكد
pend = st.session_state.pending
if pend:
    if pend.status == MATCH_AMBIGUOUS:
        st.warning(f"🔎 «{pend.query}» — {pend.reason}. اختار التحليل الصح:")
    elif pend.status == MATCH_SUGGEST:
        st.warning(f"🔎 مفيش تحليل بالاسم «{pend.query}» بالظبط. {pend.reason}:")
    else:
        st.error(f"⛔ «{pend.query}» — {pend.reason}")

    if pend.candidates:
        opts = [f"{c.name}  ·  {c.price:,} {CURRENCY}  ·  {c.category}"
                for c in pend.candidates]
        pick = st.radio("الاختيارات المتاحة", opts,
                        key=f"pick_{abs(hash(pend.query))%99999}",
                        label_visibility="collapsed")
        rec = pend.candidates[opts.index(pick)]
        meta = []
        if rec.result_days:
            meta.append(f"⏱️ النتيجة خلال {rec.result_days} يوم")
        if rec.collection_notes:
            meta.append(f"🧪 {rec.collection_notes}")
        if meta:
            st.caption("  ·  ".join(meta))
        if rec.price == 0:
            st.error("⚠️ التحليل ده سعره 0 في قائمة الأسعار — حدّد السعر يدوي قبل الفاتورة")

        a1, a2 = st.columns(2)
        with a1:
            if st.button("✅ أكّد وأضف", use_container_width=True, type="primary"):
                res = try_add(rec)
                if res == "added":
                    flash("success", f"تمت إضافة {rec.name}")
                elif res == "duplicate":
                    flash("warning", f"{rec.name} موجود بالفعل")
                st.session_state.pending = None
                st.rerun()
        with a2:
            if st.button("❌ إلغاء", use_container_width=True):
                st.session_state.pending = None
                st.rerun()
    else:
        if st.button("حسناً"):
            st.session_state.pending = None
            st.rerun()

# ---- بوابة التعارض: منع الدفع مرتين ----
if st.session_state.conflict:
    conf, crec, csrc = st.session_state.conflict

    if conf.kind == "covered":
        st.error(f"⛔ **{conf.message}** — لو ضفته العميل هيدفع "
                 f"{conf.saving:,} {CURRENCY} زيادة على الفاضي.")
        k1, k2 = st.columns(2)
        with k1:
            if st.button("👍 تمام، مش هضيفه", use_container_width=True,
                         type="primary"):
                st.session_state.conflict = None
                st.rerun()
        with k2:
            if st.button("أضفه برضه (مقصود)", use_container_width=True):
                add_record(crec, csrc)
                st.session_state.conflict = None
                flash("warning", f"{crec.name} اتضاف مع إنه داخل في {conf.bundle}")
                st.rerun()
    else:
        itemized, _ = bundle_saving(crec, IDX)
        st.warning(f"📦 **{conf.message}**")
        st.caption("المفرّق الموجود: " + " · ".join(conf.names))
        k1, k2, k3 = st.columns([2, 2, 1])
        with k1:
            lbl = ("🔁 استبدلهم بالباقة"
                   + (f" (توفير {conf.saving:,})" if conf.saving > 0
                      else f" (فرق {conf.saving:,})"))
            if st.button(lbl, use_container_width=True, type="primary"):
                replace_with_bundle(crec, conf.names, csrc)
                st.session_state.conflict = None
                flash("success", f"اتحطت باقة {crec.name} بدل {len(conf.names)} مفرّق")
                st.rerun()
        with k2:
            if st.button("سيبهم مفرّق", use_container_width=True):
                st.session_state.conflict = None
                st.rerun()
        with k3:
            if st.button("إلغاء", key="conf_cancel", use_container_width=True):
                st.session_state.conflict = None
                st.rerun()

# ---- 🎤 إضافة بالأمر الصوتي ----
with st.expander("🎤 إضافة بالصوت (قول اسم التحليل)"):
    _vl = st.radio("لغة الكلام", ["English", "عربي"], horizontal=True, key="voice_lang")
    components.html(mic_html("en-US" if _vl == "English" else "ar-EG"), height=100)
    vtxt = st.text_input(VOICE_ARIA, key=f"voice_text_{st.session_state.voice_gen}",
                         label_visibility="collapsed",
                         placeholder="الكلام هيتكتب هنا — أو اكتب واضغط Enter")
    st.caption("قول مثلاً: CBC — أو أكتر من تحليل: CBC and ESR and glucose")

if vtxt.strip():
    _whole = resolve_test(vtxt, IDX)
    _parts = [vtxt.strip()] if _whole.is_confident else split_voice_command(vtxt)
    _recs, _choose, _missing = [], [], []
    for _t in _parts:
        _r = resolve_test(_t, IDX)
        if _r.is_confident:
            _recs.append(_r.best)
        elif _r.candidates:
            _choose.append((_t, _r.candidates[:6], _r.reason))
        else:
            _missing.append(_t)
    if _recs:   # المؤكد بس بيتضاف تلقائي — نفس قاعدة البحث المكتوب
        _a, _d, _c, _df = add_many(_recs, "voice")
        if _a:
            flash("success", "🎤 سمعت وأضفت: " + "، ".join(_a))
        flash_panel_result("الأمر الصوتي", [], _d, _c, _df)
    if _choose or _missing:
        st.session_state.bulk = {"confident": [], "choose": _choose, "missing": _missing}
        st.session_state.bulk_src = ""
        flash("warning", "🎤 في اسم محتاج تأكيدك — راجعه تحت في «الصق قائمة»")
    if not _parts:
        flash("warning", "🎤 مسمعتش اسم تحليل واضح — جرّب تاني")
    st.session_state.voice_gen += 1
    st.rerun()

# ---- لصق قائمة تحاليل من رسالة العميل ----
BULK = st.session_state.bulk

with st.expander("📋 الصق قائمة تحاليل (من رسالة عميل)",
                 expanded=bool(BULK) and st.session_state.get("bulk_src") != "wa"):
    with st.form("bulk_form"):
        raw = st.text_area(
            "الزق النص هنا", height=130, label_visibility="collapsed",
            placeholder="الزق رسالة العميل زي ما هي — عربي أو إنجليزي:\n"
                        "1- صورة دم كاملة\n2- سكر صائم\n"
                        "فيتامين د، كرياتينين\nTSH + Ferritin")
        go = st.form_submit_button("🔍 اقرأ القائمة", use_container_width=True)

    if go:
        toks = parse_bulk_tests(raw)
        conf, choose, missing = [], [], []
        for t in toks:
            r = resolve_test(t, IDX)
            if r.is_confident:
                conf.append((t, r.best))
            elif r.candidates:
                choose.append((t, r.candidates[:6], r.reason))
            else:
                missing.append(t)
        st.session_state.bulk = {"confident": conf, "choose": choose,
                                 "missing": missing}
        st.session_state.bulk_src = ""
        if not toks:
            flash("warning", "مفيش أي سطر صالح في النص ده")
        st.rerun()

    if BULK and st.session_state.get("bulk_src") != "wa":
        bulk_review(BULK)

# تصفح بالقسم
with st.expander("📂 تصفّح حسب القسم"):
    cat = st.selectbox("القسم", sorted(LABS_DB.keys()))
    recs = [r for r in IDX.records if r.category == cat]
    opts = [f"{r.name}  ·  {r.price:,} {CURRENCY}" for r in recs]
    sel = st.multiselect("اختار تحاليل", opts, key=f"cat_pick_{cat}")
    if sel and st.button("➕ أضف المختار", key=f"cat_add_{cat}"):
        n = sum(1 for s in sel if try_add(recs[opts.index(s)]) == "added")
        flash("success", f"تمت إضافة {n} تحليل")
        st.rerun()

st.divider()


# ------------------------------------------------------------
# 4) Invoice
# ------------------------------------------------------------

st.markdown("#### 📋 الفاتورة")
items = st.session_state["items"]

if not items:
    st.info("لسه مفيش تحاليل مضافة.")
    totals = compute_totals([], 0, "Percentage")
else:
    h = st.columns([5, 2, 3, 1])
    h[0].markdown("**التحليل**")
    h[1].markdown("**السعر**")
    h[2].markdown("**ملاحظات**")
    h[3].markdown("**حذف**")

    remove_uid = None
    for it in items:
        c = st.columns([5, 2, 3, 1])
        badge = " 📦" if it.get("category", "").startswith("Profiles") else ""
        c[0].write(f"{it['name']}{badge}")
        c[1].write(f"**{it['price']:,}**" if it["price"] else "**—**")
        bits = []
        if it["result_days"]:
            bits.append(f"⏱️{it['result_days']}d")
        if it["collection_notes"]:
            bits.append(it["collection_notes"][:34])
        c[2].caption("  ·  ".join(bits) or "—")
        if c[3].button("🗑️", key=f"del_{it['uid']}"):   # مفتاح ثابت مش index
            remove_uid = it["uid"]

    if remove_uid:
        st.session_state["items"] = [i for i in items if i["uid"] != remove_uid]
        st.rerun()

    # ---- 💡 Smart Offer Engine: اقتراح استباقي لاستبدال مفرّق بباقة أرخص ----
    # بيدوّر على الفاتورة كلها في كل مرة — مش بس وقت إضافة تحليل جديد،
    # عشان ما نضيّعش فرصة upsell لو الموظف ضاف التحاليل واحد واحد.
    offers = [o for o in suggest_bundle_offers(items, IDX)
             if o["bundle"].key not in st.session_state.dismissed_offers]
    for off in offers:
        b = off["bundle"]
        st.info(
            f"💡 **اقتراح توفير للعميل**\n\n"
            f"بإمكانك استبدال {len(off['matched_names'])} تحاليل منفردة "
            f"بـ «{b.name}»\n\n"
            f"السعر يقل من {off['spent']:,} إلى {b.price:,} {CURRENCY} — "
            f"العميل يوفر **{off['saving']:,} {CURRENCY}**"
        )
        oc1, oc2 = st.columns([2, 1])
        with oc1:
            if st.button(f"🔁 استبدلهم بـ «{b.name}»", key=f"offer_add_{b.key}",
                         use_container_width=True, type="primary"):
                replace_with_bundle(b, off["matched_names"], source="smart_offer")
                flash("success", f"اتحطت باقة {b.name} بدل "
                                 f"{len(off['matched_names'])} مفرّق — "
                                 f"وفّرت على العميل {off['saving']:,} {CURRENCY}")
                st.rerun()
        with oc2:
            if st.button("تجاهل", key=f"offer_dismiss_{b.key}",
                         use_container_width=True):
                st.session_state.dismissed_offers.append(b.key)
                st.rerun()

    st.markdown("")
    d1, d2 = st.columns([1, 2])
    with d1:
        dtype = st.radio("نوع الخصم", ["Percentage", "Fixed Amount"],
                         index=["Percentage", "Fixed Amount"].index(
                             st.session_state.discount_type),
                         horizontal=True, label_visibility="collapsed")
        if dtype != st.session_state.discount_type:
            st.session_state.discount_type = dtype
            st.session_state.discount_value = 0.0
            st.session_state.disc_gen += 1
            st.rerun()
    with d2:
        # الخانة ليها key ثابت وبتتزرع مرة واحدة بس: قبل كده كان `value=` بيتغيّر
        # مع كل تعديل فـ Streamlit يعتبرها خانة جديدة ويرجّع القيمة القديمة.
        # الحد الأقصى ثابت (compute_totals بيقصّ الخصم على الإجمالي أصلاً).
        _dk = f"disc_{dtype}_{st.session_state.disc_gen}"
        if _dk not in st.session_state:
            st.session_state[_dk] = float(st.session_state.discount_value)
        st.session_state.discount_value = st.number_input(
            "خصم (%)" if dtype == "Percentage" else f"خصم ({CURRENCY})",
            min_value=0.0,
            max_value=100.0 if dtype == "Percentage" else 1_000_000.0,
            step=1.0 if dtype == "Percentage" else 10.0, format="%.0f", key=_dk)

    totals = compute_totals(items, st.session_state.discount_value,
                            st.session_state.discount_type)

    if totals["unpriced"]:
        st.error(f"⚠️ تحاليل من غير سعر: {', '.join(totals['unpriced'])} — "
                 f"حدّد سعرها قبل ما تبعت الفاتورة")

    m1, m2, m3 = st.columns(3)
    m1.metric("عدد التحاليل", totals["count"])
    m2.metric("قبل الخصم", f"{totals['subtotal']:,}")
    m3.metric("الإجمالي", f"{totals['total']:,} {CURRENCY}",
              delta=f"-{totals['discount']:,}" if totals["discount"] else None)
    if totals["max_days"]:
        st.caption(f"⏱️ أطول وقت نتيجة في الفاتورة: {totals['max_days']} يوم")

st.divider()


# ------------------------------------------------------------
# 5) Send / Export
# ------------------------------------------------------------

def apply_catalog_offer(o):
    """بيضيف تحاليل العرض للفاتورة (بنفس حماية التكرار/التعارض) ويظبط خصم ثابت
    يخلّي إجمالي التحاليل دي = سعر العرض بالظبط. لو فيه خصم متسجّل قبل كده مابيلمسوش."""
    added = dup = 0
    for name in o["db"]:
        hits = IDX.get(name)
        if not hits:
            continue
        res = try_add(hits[0], source=f"offer:{o['id']}")
        added += res == "added"
        dup += res == "duplicate"
    wanted = set(o["db"])
    base = sum(int(i["price"]) for i in st.session_state["items"] if i["name"] in wanted)
    need = base - int(o["after"])
    if st.session_state.get("conflict"):
        flash("warning", "فيه تعارض في إضافة بعض التحاليل — اتحلّه الأول وبعدها اضغط تاني")
    elif need <= 0:
        flash("info", f"اتضافت التحاليل ({added} جديد). سعر العرض مش أقل من مجموعها فمفيش خصم يتطبّق")
    elif float(st.session_state.discount_value or 0) > 0:
        flash("warning", f"اتضافت التحاليل، بس فيه خصم متسجّل — اضبطه يدوي ({need} ج) "
                         f"عشان الإجمالي يبقى {int(o['after']):,}")
    else:
        st.session_state.discount_type = "Fixed Amount"
        st.session_state.discount_value = float(need)
        st.session_state.disc_gen += 1
        st.session_state["_offer_disc"] = (st.session_state.quote_id, need)
        st.session_state["_offer_id"] = o["id"]
        flash("success", f"✅ اتطبّق «{o['title']}»: {added} تحليل جديد + خصم {need:,} "
                         f"= {int(o['after']):,} {CURRENCY}" + (f" ({dup} كانوا موجودين)" if dup else ""))



# ---- تسعير الروشتة: عروض مناسبة للفاتورة دي (خصم فوري أو «ضيف تحليل ووفّر»)
if items and HAS_CATALOG:
    _sug = [m for m in OM.match_offers(items, IDX, OC.OFFERS) if m["offer"]["id"] != st.session_state.get("_offer_id")][:3]
    _psug = OM.match_promotions(items, load_promos(), st.session_state.branch, date.today())[:2]
    if _sug or _psug:
        st.markdown("#### 🎁 عروض مناسبة لهذه الفاتورة")
    for _m in _sug:
        _o = _m["offer"]
        _c1, _c2 = st.columns([3, 1])
        if _m["kind"] == "full":
            _c1.markdown(f"✅ **{_o['title']}** — الفاتورة مؤهلة: {_m['have_sum']:,} ← **{_m['after']:,}** "
                         f"(**وفّر {_m['saving']:,} {CURRENCY}**)")
            _lbl = "⚡ طبّق"
        else:
            _c1.markdown(f"➕ ضيف **{'، '.join(_m['missing'])}** "
                         + (f"(+{_m['extra_cost']:,}) " if _m["extra_cost"] > 0 else "(والإجمالي بيقل) ")
                         + f"واحصل على **{_o['title']}** بـ {_m['after']:,} — قيمة مضافة {_m['saving']:,} {CURRENCY}")
            _lbl = "➕ أضف وطبّق"
        if _c2.button(_lbl, key=f"sug_{_o['id']}", use_container_width=True):
            apply_catalog_offer(_o)
            st.rerun()
    for _pm in _psug:
        _c1, _c2 = st.columns([3, 1])
        _c1.markdown(f"🎁 عرض شغّال على **{_pm['item']}**: {_pm['promo']['original_price']:,} ← "
                     f"**{_pm['promo']['promo_price']:,}** (وفّر {_pm['saving']:,} {CURRENCY})")
        if _c2.button("⚡ طبّق", key=f"psug_{_pm['promo']['id']}", use_container_width=True):
            for _it in st.session_state["items"]:
                if _it["name"] == _pm["item"]:
                    _it["price"] = _pm["promo"]["promo_price"]
                    _it["source"] = f"promo:{_pm['promo']['id']}"
            flash("success", f"🎁 اتطبّق سعر العرض على {_pm['item']}")
            st.rerun()

st.markdown("#### 📤 إرسال")

# ---- حملة الزيارة المنزلية المجانية: صافي التحاليل بعد الخصم >= الحد + منطقة الحملة
FHV_RES = (CP.evaluate_all(CFG["campaigns"], net_total=totals["total"], area=st.session_state.area,
                           today=date.today()) if items else [])
for _r in FHV_RES:
    _c = _r["campaign"]
    if _r["eligible"]:
        st.success(f"🎁 FREE HOME VISIT ELIGIBLE — {_c['name']}"
                   + (" · أكّد إن العميل في 6 أكتوبر/الشيخ زايد" if _r["needs_area"] else ""))
    elif _r["reason"] == "amount" and 0 < _r["missing"] <= 0.25 * int(_c["min_net"]):
        st.info(f"🎁 ناقص {_r['missing']:,} {CURRENCY} ويتأهل العميل لـ «{_c['name']}» "
                f"(الحد {int(_c['min_net']):,} صافي بعد الخصم)")
_fhv_on = any(r["eligible"] for r in FHV_RES) and st.toggle(
    "🎁 إضافة الزيارة المجانية لرسالة العميل", value=True, key="wa_fhv")
FHV_IDS = CP.benefit_ids(FHV_RES) if _fhv_on else []
_BINFO = CFG["branches"].get(st.session_state.branch)
_branch_on = bool(_BINFO) and st.toggle("📍 إرفاق عنوان ومواعيد الفرع مع العرض", value=True, key="wa_branch_info")
_t1, _t2, _t3 = st.columns(3)
_cta_on = _t1.toggle("✅ طريقة الحجز", value=True, key="wa_cta",
                     help="«للحجز ردّ برقم: 1 لاسيتيه · 2 دياموند · 3 سحب منزلي» — العميل يرد برقم بدل ما يفكّر")
_code_on = _t2.toggle("🔖 كود العرض", value=True, key="wa_code",
                      help="العميل يذكره عند الحضور ← الاستقبال يلاقي العرض في Check-in ويسجّل الحضور")
_prep_on = _t3.toggle("🧪 تعليمات التحضير", value=True, key="wa_prep",
                      help="صيام/ميعاد السحب للتحاليل اللي محتاجة (من patient_prep.py)")
_PREP_TXT = prep_block([i["name"] for i in items], _BUNDLE_COMPONENTS) if (items and _prep_on) else ""


# الرسالة بتتبني بمستويات: لو لينك واتساب طويل، بنختصر الأقل أهمية الأول (عنوان الفرع الكامل ←
# تعليمات العينة ← التحضير ← طريقة الحجز) — الإجمالي والكود وخريطة الفرع بيفضلوا لآخر لحظة.
#   level: (رسالة كاملة؟, التحضير, طريقة الحجز: full/short/none, الفرع كامل؟, الكود كامل؟)
_LEVELS = [(True, True, "full", True, True), (True, True, "full", False, True),
           (False, True, "full", False, True), (False, False, "short", False, False),
           (False, False, "none", False, False), (False, False, "none", False, False)]


def _msg(level) -> str:
    full, with_prep, cta, branch_full, code_full = _LEVELS[min(int(level), len(_LEVELS) - 1)]
    base = build_whatsapp_message(
        items, totals, name_chk.value if name_chk.ok else st.session_state.p_name,
        lab_name=LAB_NAME_AR, doctor=st.session_state.p_doctor,
        invoice_date=st.session_state.p_date.strftime("%d-%m-%Y"),
        currency=CURRENCY, lang=st.session_state.wa_lang, compact=not full)
    extra = []
    ar = st.session_state.wa_lang != "en"
    last = int(level) >= len(_LEVELS) - 1
    if _PREP_TXT and ar and with_prep:
        extra.append(_PREP_TXT)
    if FHV_IDS:
        extra.append(CP.benefit_text(FHV_RES, "en" if st.session_state.wa_lang == "en" else "ar"))
    if _cta_on and ar and cta == "full":
        extra.append(RP.booking_cta(_BRANCH_NAMES))
    elif _cta_on and ar and cta == "short":
        extra.append("✅ للحجز ردّ: " + " · ".join(f"{i + 1} {n}" for i, n in enumerate(_BRANCH_NAMES[:2] + ["سحب منزلي"])))
    if _branch_on and not last:
        extra.append(config_store.branch_block(_BINFO, compact=not branch_full))
    if _code_on:
        extra.append(RP.code_line(st.session_state.quote_id) if (code_full and ar) else f"🔖 {st.session_state.quote_id}")
    return base + ("\n\n" + "\n\n".join(extra) if extra else "")


_wa_phone = phone_chk.value if phone_chk.ok else ""
wa_note, WA_LEVEL = "", 0
for WA_LEVEL in range(len(_LEVELS)):
    wa_msg = _msg(WA_LEVEL)
    wa_url = build_whatsapp_url(_wa_phone, wa_msg)
    if len(wa_url) <= MAX_WA_URL:
        break
else:
    wa_note = "⚠️ الفاتورة كبيرة جداً على لينك واتساب — استخدم PDF أو انسخ الرسالة يدوي"
if not wa_note and WA_LEVEL >= 3:
    wa_note = "الرسالة طويلة — اتختصرت (التحضير/طريقة الحجز) عشان لينك واتساب يشتغل"
if wa_note and items:
    if "كبيرة" in wa_note:
        st.warning(wa_note)
    else:
        st.caption("ℹ️ " + wa_note)

# ---- سياسة الخصم: أكبر من الحد = موافقة المسؤول بكود (secrets: discount_limit_pct + discount_approval_pin)
_limit_hit = bool(items) and needs_approval(totals, DISCOUNT_LIMIT_PCT)
_appr_key = f"_appr_{st.session_state.quote_id}_{totals['discount']}"   # الموافقة مربوطة بقيمة الخصم دي
_offer_ok = st.session_state.get("_offer_disc") == (st.session_state.quote_id, totals["discount"])
_approved = bool(st.session_state.get(_appr_key)) or _offer_ok       # سعر عرض رسمي = معتمد
if _limit_hit and not _approved:
    if DISCOUNT_PIN:
        st.warning(f"🔐 الخصم {discount_pct_of(totals):.0f}% أكبر من الحد المسموح "
                   f"({DISCOUNT_LIMIT_PCT:.0f}%) — محتاج موافقة المسؤول")
        _pin = st.text_input("كود الموافقة", type="password", key="disc_pin")
        if _pin and pin_ok(_pin, DISCOUNT_PIN):
            st.session_state[_appr_key] = True
            st.rerun()
        elif _pin:
            st.error("كود الموافقة غلط")
    else:
        st.warning(f"⚠️ الخصم {discount_pct_of(totals):.0f}% أكبر من الحد ({DISCOUNT_LIMIT_PCT:.0f}%) "
                   "— ضيف discount_approval_pin في Secrets عشان يتطلب موافقة")

blockers = []
if _limit_hit and DISCOUNT_PIN and not _approved:
    blockers.append("الخصم محتاج موافقة المسؤول")
if not items:
    blockers.append("مفيش تحاليل في الفاتورة")
if not name_chk.ok:
    blockers.append("اسم العميل غير صالح")
if not phone_chk.ok:
    blockers.append("رقم الموبايل غير صالح")
if totals.get("unpriced"):
    blockers.append("فيه تحاليل من غير سعر")

# ---- تسجيل حدث "quote" مرة واحدة بس لكل quote_id، أول ما الفاتورة تبقى
#      جاهزة للإرسال (اسم+رقم صح+فيها تحاليل) — أساس حساب نسبة التحويل
if not blockers:
    _log_key = f"_logged_{st.session_state.quote_id}"
    if not st.session_state.get(_log_key):
        store = get_event_store()
        if store:
            try:
                store.append(events_path(month_key()), make_event(
                    "quote", st.session_state.quote_id,
                    branch=st.session_state.branch,
                    referral_source=st.session_state.referral_source,
                    total=totals["total"], count=totals["count"],
                    items=[i["name"] for i in items],
                    campaign_id=CAMPAIGN, phone_key=PK, discount=totals["discount"],
                    staff=st.session_state.staff_name, visit_type=st.session_state.visit_type,
                    area=st.session_state.area, benefits=FHV_IDS,
                    parent=st.session_state.parent_quote,
                    meta=({"approved": True} if _approved and _limit_hit and not _offer_ok else {})
                    | ({"offer": st.session_state["_offer_id"]} if _offer_ok else {})
                    | ({"inquiry_ts": st.session_state.inquiry_ts} if st.session_state.inquiry_ts else {})
                    or None))
            except GithubStoreError:
                pass  # التتبّع مش أولوية أعلى من إتمام الفاتورة نفسها
        st.session_state[_log_key] = True

FU_OPTIONS = [3, 6, 24, 48, 72, 0]
FU_LABELS = {0: "من غير متابعة", 3: "بعد 3 ساعات", 6: "بعد 6 ساعات", 24: "بكرة (24 ساعة)",
             48: "بعد يومين", 72: "بعد 3 أيام"}
_sent_key = f"_sent_{st.session_state.quote_id}"


def log_sent(via: str) -> bool:
    """«اتبعت» + ميعاد المتابعة في حدث واحد — أساس قايمة المتابعة وتأكيد الحضور."""
    _store = get_event_store()
    if not _store:
        flash("warning", "تتبّع العروض مش متظبط في الإعدادات (secrets)")
        return False
    fh = int(st.session_state.get("fu_hours", 24) or 0)
    due = (datetime.now() + timedelta(hours=fh)).isoformat(timespec="seconds") if fh else ""
    try:
        _contact = ({"name": name_chk.value, "phone": phone_chk.value}
                    if STORE_CONTACTS and name_chk.ok else None)
        _store.append(events_path(month_key()), make_event(
            "sent", st.session_state.quote_id, branch=st.session_state.branch,
            referral_source=st.session_state.referral_source,
            total=totals["total"], count=totals["count"],
            items=[i["name"] for i in items], discount=totals["discount"],
            campaign_id=CAMPAIGN, phone_key=PK, contact=_contact,
            staff=st.session_state.staff_name, visit_type=st.session_state.visit_type,
            area=st.session_state.area, benefits=FHV_IDS,
            parent=st.session_state.parent_quote,
            meta={"followup_hours": fh, "via": via, **({"next_due": due} if due else {}),
                  **({"inquiry_ts": st.session_state.inquiry_ts} if st.session_state.inquiry_ts else {})}))
        st.session_state[_sent_key] = due or "none"
        flash("success", "✅ اتسجّل إن العرض اتبعت" + (
            f" — المتابعة {FU_LABELS[fh]} في «Follow-up» لو العميل ماردّش، والحضور بيتأكد من «Check-in»"
            if fh else " (من غير متابعة)"))
        return True
    except GithubStoreError as e:
        flash("error", f"مقدرتش أسجّل الإرسال: {e}")
        return False


s1, s2, s3 = st.columns(3)

with s1:
    if blockers:
        st.button("📲 إرسال واتساب", disabled=True, use_container_width=True)
        st.caption("مقفول: " + " · ".join(blockers))
    elif get_event_store():
        # ضغطة واحدة: بتفتح واتساب العميل وبتسجّل «اتبعت» + ميعاد المتابعة (جسر wa_bridge)
        st.session_state.setdefault("fu_hours", config_store.followup_hours(CFG))
        if st.session_state.fu_hours not in FU_OPTIONS:
            st.session_state.fu_hours = 24
        st.selectbox("⏰ المتابعة لو ماردّش", FU_OPTIONS, key="fu_hours", format_func=lambda h: FU_LABELS[h])
        st.markdown(BRIDGE_CSS, unsafe_allow_html=True)
        _bv = st.text_input(BRIDGE_ARIA, key=f"wa_bridge_{st.session_state.bridge_gen}",
                            label_visibility="collapsed")
        _tok = parse_token(_bv)
        if _tok:
            st.session_state.bridge_gen += 1
            if _tok == ("sent", st.session_state.quote_id) and not st.session_state.get(_sent_key):
                log_sent("one_tap")
            st.rerun()
        _done = st.session_state.get(_sent_key)
        components.html(send_button_html(
            wa_url, f"📲 إرسال لـ \u2066{format_phone_display(phone_chk.value)}\u2069" + ("" if _done else " + متابعة"),
            make_token("sent", st.session_state.quote_id),
            hint="" if _done else "بيفتح واتساب ويسجّل الإرسال والمتابعة مع بعض"), height=82)
        if _done:
            st.caption("✔ اتسجّل إن العرض اتبعت" + (
                f" — المتابعة: {datetime.fromisoformat(_done):%d-%m %H:%M}" if _done != "none" else " (من غير متابعة)"))
        elif st.button("✅ تم الإرسال (لو ماتسجّلش لوحده)", use_container_width=True, key="btn_sent"):
            log_sent("button")
            st.rerun()
    else:
        st.markdown(
            f'<a href="{wa_url}" target="_blank" style="text-decoration:none;">'
            f'<div style="background:#25D366;color:#fff;text-align:center;'
            f'padding:9px;border-radius:6px;font-weight:700;">'
            f'📲 إرسال لـ {format_phone_display(phone_chk.value)}</div></a>',
            unsafe_allow_html=True)
        st.caption("التتبّع مش متظبط (secrets) — الإرسال شغّال، بس من غير متابعة ولا تسجيل")
        if st.button("✅ تم الإرسال للعميل", use_container_width=True, key="btn_sent"):
            log_sent("button")
            st.rerun()

with s2:
    pdf_ready = bool(items) and name_chk.ok
    try:
        from pdf_invoice import unicode_ready
        pdf_uni = unicode_ready()
    except Exception:
        pdf_uni = False
    # مع خط يونيكود الأسماء العربية بقت شغالة؛ من غيره نرجع للقيد القديم
    pdf_safe = pdf_uni or name_is_pdf_safe(name_chk.value)
    if pdf_ready and not pdf_safe:
        st.button("📄 PDF", disabled=True, use_container_width=True)
        st.caption("مفيش خط يونيكود على السيرفر — اكتب الاسم إنجليزي "
                   "أو ارفع خط في مجلد fonts/")
    elif pdf_ready:
        try:
            from pdf_invoice import build_pdf
            st.download_button(
                "📄 تحميل PDF", data=build_pdf(items, totals,
                                               name_chk.value,
                                               phone_chk.value if phone_chk.ok else "",
                                               st.session_state.p_doctor,
                                               st.session_state.p_date.strftime("%d-%m-%Y"),
                                               MAPS_URL),
                file_name=f"orange_invoice_{st.session_state.p_date}.pdf",
                mime="application/pdf", use_container_width=True)
        except Exception as e:
            st.button("📄 PDF", disabled=True, use_container_width=True)
            st.caption(f"PDF غير متاح: {e}")
    else:
        st.button("📄 PDF", disabled=True, use_container_width=True)

with s3:
    if st.button("🗑️ فاتورة جديدة", use_container_width=True):
        for k in ("items", "pending", "pending_panel", "conflict", "p_name", "p_phone",
                  "p_doctor", "discount_value", "quote_id", "dismissed_offers",
                  "saved_link", "saved_at", "referral_source", "campaign_id", "area",
                  "visit_type", "parent_quote", "inquiry_ts", "bulk", "bulk_src"):
            st.session_state[k] = DEFAULTS[k] if not isinstance(DEFAULTS[k], list) else []
        st.session_state.p_date = date.today()
        st.session_state.disc_gen += 1
        st.session_state["_show_lost_reason"] = False
        st.session_state["_wa_last"] = None
        st.query_params.clear()
        st.rerun()

if items:
    with st.expander("👀 معاينة رسالة الواتساب"):
        st.code(wa_msg, language=None)

st.divider()


# ------------------------------------------------------------
# 6) Save Quote — لينك يرجّع نفس الفاتورة خلال 24-48 ساعة
#    "هفكر وأرد عليكم" -> نحفظله العرض بدل ما نضيّع العميل
# ------------------------------------------------------------

st.markdown("#### 💾 حفظ العرض للمتابعة لاحقاً")
st.caption(f"🔐 اللينك مشفّر وبيقفل لوحده بعد {QUOTE_TTL_HOURS:.0f} ساعة" if QUOTE_SECRET else
           "🔓 من غير quote_secret اللينك مش مشفّر ومش بيتأكد منه")

sv1, sv2 = st.columns([1, 2])
with sv1:
    if st.button("💾 احفظ العرض", use_container_width=True, disabled=not items):
        payload = {
            "id": st.session_state.quote_id,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "items": [{"n": i["name"], "p": i["price"], "d": i.get("result_days"),
                       "c": i.get("collection_notes", ""), "cat": i.get("category", "")}
                      for i in items],
            "name": st.session_state.p_name,
            "phone": st.session_state.p_phone,
            "doctor": st.session_state.p_doctor,
            "date_iso": st.session_state.p_date.isoformat(),
            "dtype": st.session_state.discount_type,
            "dval": st.session_state.discount_value,
            "cid": CAMPAIGN, "area": st.session_state.area,
            "vt": st.session_state.visit_type, "par": st.session_state.parent_quote,
        }
        st.session_state.saved_link = f"{APP_URL}/?q={encode_quote(payload, QUOTE_SECRET)}"
        st.session_state.saved_at = payload["ts"]
        st.rerun()

if st.session_state.saved_link and not QUOTE_SECRET:
    st.warning("🔓 اللينك ده من غير توقيع — أضف quote_secret في Streamlit Secrets "
               "عشان محدّش يقدر يعدّل السعر أو الخصم فيه")
if st.session_state.saved_link:
    with sv2:
        st.text_input(f"لينك العرض — صالح {QUOTE_TTL_HOURS:.0f} ساعة (شير له، افتحه تاني يرجّع نفس الفاتورة)",
                      value=st.session_state.saved_link, key="saved_link_box")
    if APP_URL.startswith("https://REPLACE"):
        st.warning("⚠️ لسه محطوطش لينك التطبيق الحقيقي — حطه من صفحة Branches ← Links (أو secret اسمه app_url) — "
                   "غيّره عشان اللينك ده يفتح صح")

    if phone_chk.ok and CUSTOMER and CUSTOMER["optout"]:
        st.caption("🚫 العميل طلب إيقاف الرسائل — زرار التذكير متقفل")
    elif phone_chk.ok:
        rem_name = name_chk.value if name_chk.ok else st.session_state.p_name
        age_now = quote_age_hours(st.session_state.saved_at)
        remaining = max(0, round(QUOTE_TTL_HOURS - age_now)) if age_now is not None else round(QUOTE_TTL_HOURS)
        reminder_msg = (
            f"🍊 *{LAB_NAME_AR}*\n"
            f"مرحباً {rem_name}،\n"
            f"بنفكّرك بعرض التحاليل اللي طلبته:\n"
            f"{st.session_state.saved_link}\n"
            f"*المطلوب: {totals['total']:,} {CURRENCY}*\n"
            f"⏱️ العرض متاح لغاية {remaining} ساعة كمان"
        )
        rem_url = build_whatsapp_url(phone_chk.value, reminder_msg)
        st.markdown(
            f'<a href="{rem_url}" target="_blank" style="text-decoration:none;">'
            f'<div style="background:#25D366;color:#fff;text-align:center;'
            f'padding:9px;border-radius:6px;font-weight:700;margin-top:.4rem;">'
            f'📲 ابعت تذكير واتساب للعميل</div></a>',
            unsafe_allow_html=True)

st.divider()


# ------------------------------------------------------------
# 7) قرار العميل — Lost Sale / Converted
#    الأساس اللي عليه نسبة التحويل ("38% من العملاء قالوا السعر")
# ------------------------------------------------------------

st.markdown("#### 📞 قرار العميل")

_dkey = f"_decided_{st.session_state.quote_id}"      # آخر قرار اتسجّل للعرض ده
_decided = st.session_state.get(_dkey)

oc1, oc2, oc3 = st.columns(3)
with oc3:
    if st.button("📅 تم الحجز" + (" ✔" if _decided == "booked" else ""), use_container_width=True,
                 disabled=not items or _decided in ("booked", "converted")):
        st.session_state["_show_booking"] = True
        st.rerun()
with oc1:
    if st.button("✅ حضر / اتباع" + (" ✔" if _decided == "converted" else ""),
                 use_container_width=True,
                 disabled=not items or _decided == "converted"):
        store = get_event_store()
        if store:
            try:
                store.append(events_path(month_key()), make_event(
                    "converted", st.session_state.quote_id,
                    branch=st.session_state.branch, total=totals["total"]))
                st.session_state[_dkey] = "converted"
                flash("success", "✅ اتسجّل كعملية بيع — تمام")
            except GithubStoreError as e:
                flash("error", f"مقدرتش أسجّل ده: {e}")
        else:
            flash("warning", "تتبّع العروض مش متظبط في الإعدادات (secrets)")
        st.rerun()
with oc2:
    if st.button("❌ هيفوّت" + (" ✔" if _decided == "lost_sale" else ""),
                 use_container_width=True,
                 disabled=not items or _decided == "lost_sale"):
        st.session_state["_show_lost_reason"] = True
        st.rerun()

if st.session_state.get("_show_booking"):
    _bd = st.date_input("ميعاد الزيارة", value=date.today() + timedelta(days=1), key="book_date")
    _bt = st.time_input("الساعة", value=dtime(10, 0), key="book_time")
    _b1, _b2 = st.columns(2)
    if _b1.button("سجّل الحجز", use_container_width=True, type="primary", key="book_ok"):
        _bs = get_event_store()
        if _bs:
            try:
                _bs.append(events_path(month_key()), make_event(
                    "booked", st.session_state.quote_id, branch=st.session_state.branch,
                    visit_type=st.session_state.visit_type, area=st.session_state.area,
                    meta={"appointment": datetime.combine(_bd, _bt).isoformat(timespec="seconds")}))
                st.session_state[_dkey] = "booked"
                flash("success", "📅 اتسجّل الحجز — هيظهر في «Visits» لو العميل ماحضرش")
            except GithubStoreError as e:
                flash("error", f"مقدرتش أسجّل الحجز: {e}")
        else:
            flash("warning", "تتبّع العروض مش متظبط في الإعدادات (secrets)")
        st.session_state["_show_booking"] = False
        st.rerun()
    if _b2.button("إلغاء", use_container_width=True, key="book_cancel"):
        st.session_state["_show_booking"] = False
        st.rerun()

if st.session_state.get("_show_lost_reason"):
    reason = st.radio("السبب؟", LOST_SALE_REASONS, key="lost_reason_pick")
    note = st.text_input("ملاحظة (اختياري)", key="lost_reason_note")
    lc1, lc2 = st.columns(2)
    with lc1:
        if st.button("سجّل السبب", use_container_width=True, type="primary"):
            store = get_event_store()
            if store:
                try:
                    store.append(events_path(month_key()), make_event(
                        "lost_sale", st.session_state.quote_id,
                        branch=st.session_state.branch, reason=reason,
                        note=note, total=totals["total"]))
                    st.session_state[_dkey] = "lost_sale"
                    flash("success", f"اتسجّل: {reason}")
                except GithubStoreError as e:
                    flash("error", f"مقدرتش أسجّل ده: {e}")
            else:
                flash("warning", "تتبّع العروض مش متظبط في الإعدادات (secrets)")
            st.session_state["_show_lost_reason"] = False
            st.rerun()
    with lc2:
        if st.button("إلغاء", key="lost_cancel", use_container_width=True):
            st.session_state["_show_lost_reason"] = False
            st.rerun()

st.divider()


# ------------------------------------------------------------
# 8) إحصائيات سريعة (تجريبي — نواة الـ Marketing Dashboard الجاي)
# ------------------------------------------------------------

with st.expander("📊 إحصائيات الشهر ده"):
    _store = get_event_store()
    if not _store:
        st.caption("مش متظبط لسه — ضيف gh_events_token / gh_events_repo / "
                  "gh_events_branch في Streamlit Secrets عشان الإحصائيات تشتغل")
    else:
        try:
            _events, _ = _store.read(events_path(month_key()))
            _s = summarize_events(_events)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("عروض الشهر", _s["quotes"])
            k2.metric("اتباعت", _s["converted"])
            k3.metric("فاتت", _s["lost"])
            k4.metric("نسبة التحويل", f"{_s['conversion_pct']}%")
            if _s["top_lost_reasons"]:
                st.caption("🔻 أكتر أسباب الفوات: " +
                          " · ".join(f"{r} ({c})" for r, c in _s["top_lost_reasons"][:3]))
            if _s["top_sources"]:
                st.caption("📣 أكتر مصادر: " +
                          " · ".join(f"{r} ({c})" for r, c in _s["top_sources"][:3]))
        except GithubStoreError as e:
            st.caption(f"مقدرتش أجيب الإحصائيات دلوقتي: {e}")


# ------------------------------------------------------------
# 9) 📣 رسائل تسويقية (واتساب)
#    قوالب جاهزة بتتبني من بيانات الفاتورة الحالية — عدّل النص قبل الإرسال
# ------------------------------------------------------------

if HAS_CATALOG:
    with st.expander("📋 عروض المعمل (بالرقم)"):
        _opted = bool(CUSTOMER and CUSTOMER["optout"])
        if _opted:
            st.warning("🚫 العميل طلب إيقاف الرسائل — متاح بس ردود الخدمة.")
        _opts = [o for o in OC.selectable() if (not _opted or o["status"] == "service")]
        _pick = st.selectbox("رقم العرض", ([] if _opted else ["menu"]) + [o["id"] for o in _opts], key="cat_pick",
                             format_func=lambda i: ("📋 القائمة الترحيبية (كل الأرقام)" if i == "menu"
                                                    else OC.option_label(OC.get(i))))
        _co = None if _pick == "menu" else OC.get(_pick)
        _w1, _w2 = st.columns(2)
        _wh = _w1.toggle("مواعيد العمل", key="cat_hours")
        _wl = _w2.toggle("عنوان الفرع", key="cat_loc")
        if _co and not OC.is_sendable(_co):
            st.warning("⚠️ الرقم ده في القائمة بس لسه من غير تفاصيل/سعر — ضيفها في offers_data.py")
        else:
            _t0 = (OC.menu_message() if _co is None else
                   OC.offer_message(_co, IDX, branch=st.session_state.branch, with_hours=_wh, with_location=_wl))
            _ctxt = st.text_area("نص الرسالة (تقدر تعدّله)", value=_t0, height=230,
                                 key=f"cat_txt_{_pick}_{_wh}_{_wl}_{st.session_state.branch}")
            _cphone = phone_chk.value if phone_chk.ok else ""
            _curl = share_url(_ctxt, _cphone)
            if len(_curl) > MAX_WA_URL:
                st.warning("الرسالة طويلة على لينك واتساب — انسخها (زرار النسخ فوق يمين المربع) والصقها في المحادثة")
                st.code(_ctxt, language=None)
                st.link_button("📲 افتح محادثة واتساب (والصق الرسالة)",
                               f"https://wa.me/{_cphone}" if _cphone else "https://wa.me/",
                               use_container_width=True)
            else:
                st.link_button("📲 افتح واتساب بالرسالة دي", _curl, use_container_width=True)
                if not _cphone:
                    st.caption("مفيش رقم عميل صالح — واتساب هيسيبك تختار جهة الاتصال")

        if _co and _co["id"] == "27":                       # العميل كتب 27: إيقاف الرسائل
            if PK and get_event_store():
                if st.button("🚫 سجّل طلب إيقاف الرسائل لرقم العميل", key="cat_optout", use_container_width=True):
                    try:
                        get_event_store().append(events_path(month_key()), make_event(
                            "optout", st.session_state.quote_id, branch=st.session_state.branch, phone_key=PK))
                        recent_events.clear()
                        flash("success", "✅ اتسجّل — الرقم ده مش هيظهر في المتابعة ولا الرسائل التسويقية")
                    except GithubStoreError as e:
                        flash("error", f"مقدرتش أسجّل الإيقاف: {e}")
                    st.rerun()
            else:
                st.caption("لتسجيل الإيقاف لازم رقم عميل صالح + quote_secret + تتبّع العروض متظبط")

        if _co and _co["status"] == "current" and _co.get("after"):
            st.caption(f"💰 {_co['after']:,} {CURRENCY}"
                       + (f" بدل {_co['before']:,} (توفير {OC.saving(_co):,})" if _co.get("before") else ""))
            if _co["db"]:
                if st.button("⚡ طبّق العرض على الفاتورة (التحاليل + الخصم)", key=f"cat_apply_{_co['id']}",
                             use_container_width=True):
                    apply_catalog_offer(_co)
                    st.rerun()
            else:
                st.caption("التحاليل مش مسمّاة بالاسم — ضيفها للفاتورة يدوي")
            if HAS_IMAGES:
                st.markdown("**🖼️ كصورة**")
                _csz = st.radio("مقاس الصورة", list(SIZES), index=1, horizontal=True, key="cat_img_size",
                                format_func=lambda k: SIZE_LABELS[k])
                try:
                    from brand import DEFAULT_PHONE as _P
                    _cpng, _cjpg = catalog_card(_co["id"], _csz, _P)
                except Exception as _e:  # noqa: BLE001
                    st.warning(f"مقدرتش أرسم الصورة: {_e}")
                else:
                    st.image(_cpng, use_container_width=True)
                    _cf = f"orange-offer-{_co['id']}-{_csz}"
                    _c1, _c2 = st.columns(2)
                    _c1.download_button("⬇️ حمّل الصورة (PNG)", _cpng, file_name=f"{_cf}.png",
                                        mime="image/png", use_container_width=True, key="cat_dl_png")
                    _c2.download_button("⬇️ JPG (أخف)", _cjpg, file_name=f"{_cf}.jpg",
                                        mime="image/jpeg", use_container_width=True, key="cat_dl_jpg")
                    components.html(share_button_html(_cjpg, _ctxt, f"{_cf}.jpg"), height=90)


with st.expander("📣 رسائل تسويقية (واتساب)"):
    if CUSTOMER and CUSTOMER["optout"]:
        st.warning("🚫 العميل ده طلب إيقاف الرسائل التسويقية — الرسائل هنا متقفلة.")
        st.stop()
    _rows = []
    for _b in bundles_for(st.session_state.branch):
        _rec = resolve_test(_b["name"], IDX).best
        if _rec:
            _rows.append({"name": _b["name"], "price": _rec.price,
                          "saving": bundle_saving(_rec, IDX)[1]})
    mk = st.selectbox("نوع الرسالة", list(MARKETING_KINDS),
                      format_func=lambda k: MARKETING_KINDS[k])
    ml = st.radio("لغة الرسالة", ["ar", "en"], horizontal=True, key="mk_lang")
    _name = name_chk.value if name_chk.ok else st.session_state.p_name
    _msg0 = build_marketing_message(
        mk, ml, lab=LAB_NAME_AR, name=_name, total=totals["total"],
        currency=CURRENCY, bundles=_rows, review_url=REVIEW_URL)
    mk_msg = st.text_area("نص الرسالة (تقدر تعدّله)", value=_msg0, height=190,
                          key=f"mk_txt_{mk}_{ml}")
    _mphone = phone_chk.value if phone_chk.ok else ""
    _murl = share_url(mk_msg, _mphone)
    if len(_murl) > MAX_WA_URL:
        st.warning("الرسالة طويلة على لينك واتساب — انسخها من تحت وابعتها يدوي")
        st.code(mk_msg, language=None)
    else:
        st.link_button("📲 افتح واتساب بالرسالة دي", _murl, use_container_width=True)
        if not _mphone:
            st.caption("مفيش رقم عميل صالح — واتساب هيسيبك تختار جهة الاتصال")

    # ---- نفس العرض كصورة (قالب Orange) — واتساب بيرفق النص بس، فالصورة بتتبعت بزرار المشاركة
    if mk == "offer" and HAS_IMAGES and _rows:
        st.markdown("**🖼️ ابعتها كصورة**")
        _isz = st.radio("مقاس الصورة", list(SIZES), index=1, horizontal=True, key="mk_img_size",
                        format_func=lambda k: SIZE_LABELS[k])
        try:
            from brand import DEFAULT_PHONE as _LAB_PHONE
            _png, _jpg = packages_card(json.dumps(_rows, ensure_ascii=False, sort_keys=True),
                                       _isz, _LAB_PHONE)
        except Exception as _e:  # noqa: BLE001
            st.warning(f"مقدرتش أرسم الصورة: {_e}")
        else:
            st.image(_png, use_container_width=True)
            _fname = f"orange-packages-{st.session_state.branch.split()[0].lower()}-{_isz}"
            _i1, _i2 = st.columns(2)
            _i1.download_button("⬇️ حمّل الصورة (PNG)", _png, file_name=f"{_fname}.png",
                                mime="image/png", use_container_width=True, key="mk_dl_png")
            _i2.download_button("⬇️ JPG (أخف)", _jpg, file_name=f"{_fname}.jpg",
                                mime="image/jpeg", use_container_width=True, key="mk_dl_jpg")
            components.html(share_button_html(_jpg, mk_msg, f"{_fname}.jpg"), height=90)
            st.caption("📲 «شارك الصورة نفسها» بيفتح قايمة المشاركة في الموبايل بالصورة والنص. "
                       "لو مش شغّال عندك: اضغط مطوّلاً على الصورة ← مشاركة/حفظ. "
                       "لتصميمات أكتر (خصم، توعية، قصص) افتح 🎨 الاستوديو.")
