# Invoice.py
# ============================================================
#  Orange Lab - Medical Test Invoice
#  Developed by Dr/Hussein Ali
#
#  التشغيل:  streamlit run Invoice.py
#  الاختبار: python3 test_price_utils.py   (قبل أي رفع)
# ============================================================

import uuid
from datetime import date, datetime
from io import BytesIO

import streamlit as st

st.set_page_config(page_title="Orange Lab - Invoice", page_icon="🍊", layout="wide")

st.markdown("""
<style>
.stActionButton {display:none !important;}
#MainMenu, footer {visibility:hidden !important;}
header[data-testid="stHeader"] {display:none !important;}
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
                         build_whatsapp_link_safe, build_whatsapp_message,
                         build_whatsapp_url, bundle_saving, check_add,
                         compute_totals, decode_quote, encode_quote,
                         generate_quote_id, parse_bulk_tests, quote_age_hours,
                         format_phone_display, name_is_pdf_safe, norm,
                         resolve_test, search_tests, suggest_bundle_offers,
                         validate_patient_name, validate_phone)
from tracking import (LOST_SALE_REASONS, REFERRAL_SOURCES, make_event,
                      month_key, summarize_events)
from github_store import (GithubEventStore, GithubStoreError, events_path,
                          store_from_secrets)

CURRENCY = "ج.م"
LAB_NAME_AR = "معمل أورانج للتحاليل الطبية"
MAPS_URL = "https://maps.app.goo.gl/vLdtTk9KctLXtpE4A?g_st=ac"

# TODO: حط هنا لينك التطبيق المنشور فعلياً على Streamlit Cloud
# (من غير كده زرار "حفظ العرض" هيولّد لينك مايفتحش صح)
APP_URL = "https://REPLACE-WITH-YOUR-STREAMLIT-APP-URL"


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
        data = decode_quote(q)
        if data:
            st.session_state["items"] = [
                {"uid": uuid.uuid4().hex[:8], "name": it["n"], "price": int(it["p"]),
                 "result_days": it.get("d"), "collection_notes": it.get("c", ""),
                 "category": it.get("cat", ""), "source": "saved_quote"}
                for it in data.get("items", [])
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
            age_h = quote_age_hours(data.get("ts", ""))
            if age_h is not None and age_h > 48:
                flash("warning",
                      f"⚠️ العرض المحفوظ {data.get('id','')} عمره {age_h:.0f} ساعة "
                      f"(أكتر من 48 ساعة) — راجع الأسعار قبل ما تأكّده للعميل")
            else:
                flash("info", f"📂 اتفتح عرض محفوظ: {data.get('id','')}")
        else:
            flash("error", "⚠️ لينك العرض ده تالف أو معدَّل — مش هينفتح")

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
st.caption(f"🧾 Quote ID: `{st.session_state.quote_id}`  ·  للمتابعة الداخلية بس، "
           f"مش بتتحط في رسالة العميل")

for kind, msg in st.session_state.flash:
    getattr(st, kind)(msg)
st.session_state.flash = []


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

name_chk = validate_patient_name(st.session_state.p_name)
phone_chk = validate_phone(st.session_state.p_phone)

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

st.divider()


# ------------------------------------------------------------
# 2) Quick panels
# ------------------------------------------------------------

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

# ---- لصق قائمة تحاليل من رسالة العميل ----
BULK = st.session_state.bulk

with st.expander("📋 الصق قائمة تحاليل (من رسالة عميل)", expanded=bool(BULK)):
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
        if not toks:
            flash("warning", "مفيش أي سطر صالح في النص ده")
        st.rerun()

    if BULK:
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
                         disabled=not chosen):
                res4 = add_many(chosen, "bulk")
                flash_panel_result("القائمة الملزوقة", *res4)
                st.session_state.bulk = None
                st.rerun()
        with g2:
            if st.button("🗑️ امسح القائمة", use_container_width=True):
                st.session_state.bulk = None
                st.rerun()

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
            st.rerun()
    with d2:
        sub = sum(i["price"] for i in items)
        st.session_state.discount_value = st.number_input(
            "خصم (%)" if dtype == "Percentage" else f"خصم ({CURRENCY})",
            min_value=0.0,
            max_value=100.0 if dtype == "Percentage" else float(max(sub, 1)),
            value=float(st.session_state.discount_value),
            step=1.0 if dtype == "Percentage" else 10.0, format="%.0f")

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

st.markdown("#### 📤 إرسال")

def _msg(compact: bool) -> str:
    return build_whatsapp_message(
        items, totals, name_chk.value if name_chk.ok else st.session_state.p_name,
        lab_name=LAB_NAME_AR, doctor=st.session_state.p_doctor,
        invoice_date=st.session_state.p_date.strftime("%d-%m-%Y"),
        currency=CURRENCY, lang=st.session_state.wa_lang, compact=compact)


wa_url, wa_msg, wa_note = build_whatsapp_link_safe(
    phone_chk.value if phone_chk.ok else "", _msg)
if wa_note and items:
    st.warning(wa_note)

blockers = []
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
                    items=[i["name"] for i in items]))
            except GithubStoreError:
                pass  # التتبّع مش أولوية أعلى من إتمام الفاتورة نفسها
        st.session_state[_log_key] = True

s1, s2, s3 = st.columns(3)

with s1:
    if blockers:
        st.button("📲 إرسال واتساب", disabled=True, use_container_width=True)
        st.caption("مقفول: " + " · ".join(blockers))
    else:
        st.markdown(
            f'<a href="{wa_url}" target="_blank" style="text-decoration:none;">'
            f'<div style="background:#25D366;color:#fff;text-align:center;'
            f'padding:9px;border-radius:6px;font-weight:700;">'
            f'📲 إرسال لـ {format_phone_display(phone_chk.value)}</div></a>',
            unsafe_allow_html=True)

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
                  "saved_link", "saved_at", "referral_source"):
            st.session_state[k] = DEFAULTS[k] if not isinstance(DEFAULTS[k], list) else []
        st.session_state.p_date = date.today()
        st.session_state["_show_lost_reason"] = False
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
        }
        st.session_state.saved_link = f"{APP_URL}/?q={encode_quote(payload)}"
        st.session_state.saved_at = payload["ts"]
        st.rerun()

if st.session_state.saved_link:
    with sv2:
        st.text_input("لينك العرض — صالح 48 ساعة (شير له، افتحه تاني يرجّع نفس الفاتورة)",
                      value=st.session_state.saved_link, key="saved_link_box")
    if APP_URL.startswith("https://REPLACE"):
        st.warning("⚠️ لسه محطوطش لينك التطبيق الحقيقي في `APP_URL` أعلى الملف — "
                   "غيّره عشان اللينك ده يفتح صح")

    if phone_chk.ok:
        rem_name = name_chk.value if name_chk.ok else st.session_state.p_name
        age_now = quote_age_hours(st.session_state.saved_at)
        remaining = max(0, round(48 - age_now)) if age_now is not None else 48
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

oc1, oc2 = st.columns(2)
with oc1:
    if st.button("✅ اتباع / حجز", use_container_width=True, disabled=not items):
        store = get_event_store()
        if store:
            try:
                store.append(events_path(month_key()), make_event(
                    "converted", st.session_state.quote_id,
                    branch=st.session_state.branch, total=totals["total"]))
                flash("success", "✅ اتسجّل كعملية بيع — تمام")
            except GithubStoreError as e:
                flash("error", f"مقدرتش أسجّل ده: {e}")
        else:
            flash("warning", "تتبّع العروض مش متظبط في الإعدادات (secrets)")
        st.rerun()
with oc2:
    if st.button("❌ هيفوّت", use_container_width=True, disabled=not items):
        st.session_state["_show_lost_reason"] = True
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
