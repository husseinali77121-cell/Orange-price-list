# pages/8_Replies.py
# ============================================================
#  💬 Smart Replies — اختار اعتراض العميل ← رد جاهز (مختصر/مطوّل) باسمه وفرعه وعروضه ←
#  واتساب ← سجّل نتيجة المحادثة (متابعة بعد 24 ساعة / فات بسبب) من نفس الصفحة.
#  • الإرسال بإيد الموظف (البرنامج ما بيبعتش تلقائي) وتأكيد الإرسال يدوي.
#  • المتابعة بتتمنع لو فيه متابعة مجدولة أو اتعملت من أقل من 12 ساعة (ما نزعجش العميل).
#  • كل رد بيتسجّل (reply) → تحليل الاعتراضات في الداشبورد.
#  • جديد: الصق رسالة العميل ← البرنامج يفهم هو بيسأل عن إيه ويقترح الرد (غالي؟ صيام؟ عنوان؟…)،
#    والرد بيتملا من العرض المسجّل (التحاليل + الإجمالي + الكود + التحضير + ميعاد النتيجة/الحجز).
#  • عميل سأل ومفيش عرض لسه ← «متابعة» بتسجّله مستفسر (Lead) عشان مايضيعش.
# ============================================================

from datetime import datetime, timedelta

import streamlit as st

import campaigns as CP
import config_store
import offers_catalog as OC
import replies as RP
from access import require_access, secret_str
from brand import LAB_NAME_AR
from bundles import BUNDLES as BUNDLE_DEFS
from bundles import BUNDLE_CATEGORY
from github_store import (GithubStoreError, events_path, read_events_range,
                          store_from_secrets)
from labs_price_list import LABS_DB
from navigation import render_nav
from panels import BRANCHES, DEFAULT_BRANCH
from price_utils import (MAX_WA_URL, build_index, format_phone_display, validate_phone)
from promotions import PROMO_PATH, active_promotions
from marketing import share_url
from tracking import (WHATSAPP_SOURCE, customer_profile, can_schedule_followup, make_event, month_key,
                      new_lead_id, optout_keys, phone_key, quote_records, stage_of)
import wa_inquiry as WI
from patient_prep import eta_text, prep_block
from price_utils import resolve_test
from access import secret_bool

st.set_page_config(page_title="Orange Lab - Replies", page_icon="💬", layout="wide")
st.markdown("## 💬 Smart Replies")
render_nav(st, "pages/8_Replies.py")
require_access(st, "صفحة الردود", level="staff")

store = store_from_secrets(st.secrets)
now = datetime.now()
QUOTE_SECRET = secret_str(st.secrets, "quote_secret")


@st.cache_data(ttl=120, show_spinner=False)
def load_cfg():
    return config_store.load(store_from_secrets(st.secrets))


@st.cache_data(ttl=120, show_spinner=False)
def load_promos():
    s = store_from_secrets(st.secrets)
    try:
        data, _ = s.read(PROMO_PATH) if s else ([], None)
        return data if isinstance(data, list) else []
    except GithubStoreError:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def load_events():
    s = store_from_secrets(st.secrets)
    if not s:
        return []
    y, m = now.year, now.month - 1
    if m < 1:
        y, m = y - 1, 12
    try:
        return read_events_range(s, f"{y:04d}-{m:02d}", month_key(now))
    except GithubStoreError:
        return []


@st.cache_resource(show_spinner=False)
def load_index():
    return build_index(LABS_DB, BUNDLE_DEFS, BUNDLE_CATEGORY)


IDX = load_index()
BUNDLE_COMPONENTS = {b["name"]: list(b.get("components", [])) for b in BUNDLE_DEFS}
STORE_CONTACTS = secret_bool(st.secrets, "store_contacts")
CFG = load_cfg()
events = load_events()
recs = quote_records(events)
opted = optout_keys(events)
st.session_state.setdefault("staff_name", "")
st.session_state.setdefault("rp_branch", DEFAULT_BRANCH)

# جاي من الفاتورة («افتح في Replies»): الاسم/الرقم/الرد/رسالة العميل
_pf = st.session_state.pop("_rp_prefill", None)
if isinstance(_pf, dict):
    for _k, _v in _pf.items():
        if _k in ("rp_name", "rp_phone", "rp_reply", "rp_msg") and _v is not None:
            st.session_state[_k] = _v
    st.session_state["_rp_auto_for"] = st.session_state["_rp_msg_seen"] = _pf.get("rp_msg", "")

# ---------------- 📥 رسالة العميل ← الرد المقترح ----------------
msg_in = st.text_area("📥 رسالة العميل (اختياري) — الصقها والبرنامج يقترح الرد", key="rp_msg", height=90,
                      placeholder="مثال: الأسعار عندكم غالية… / محتاج صيام قبل التحليل؟ / عنوانكم فين؟")
CHAT = WI.parse_chat(msg_in) if (msg_in or "").strip() else None
MSG_TESTS = []
if CHAT:
    if st.session_state.get("_rp_msg_seen") != msg_in:      # نملا الاسم/الرقم مرة واحدة لكل رسالة
        st.session_state["_rp_msg_seen"] = msg_in
        if CHAT["name"] and not (st.session_state.get("rp_name") or "").strip():
            st.session_state["rp_name"] = CHAT["name"]
        if CHAT["phone"] and not (st.session_state.get("rp_phone") or "").strip():
            st.session_state["rp_phone"] = CHAT["phone"]
    _an = WI.analyze_tests(CHAT["customer_text"], IDX)
    MSG_TESTS = [rec for _t, rec in _an["confident"]]
    _intents = WI.detect_intents(CHAT["customer_text"], has_media=CHAT["has_media"])
    _sug = RP.suggested(_intents)
    if _sug:
        st.caption("💡 الرد المقترح (اضغط عشان تختاره):")
        _cols = st.columns(min(3, len(_sug)))
        for _i, _t in enumerate(_sug[:3]):
            if _cols[_i].button(f"💡 {_t['title']}", key=f"rp_sug_{_t['id']}", use_container_width=True):
                st.session_state["rp_reply"] = _t["id"]
        if "rp_reply" not in st.session_state or st.session_state.get("_rp_auto_for") != msg_in:
            st.session_state["_rp_auto_for"] = msg_in
            st.session_state["rp_reply"] = _sug[0]["id"]
    elif not MSG_TESTS:
        st.caption("ماعرفتش نية واضحة في الرسالة — اختار الرد بنفسك تحت.")
    if MSG_TESTS:
        st.caption("🧪 في الرسالة: " + "، ".join(r.name for r in MSG_TESTS) + " — اعمله عرض سعر من صفحة Invoice")

# ---------------- العميل والفرع ----------------
c1, c2 = st.columns(2)
name = c1.text_input("اسم العميل", key="rp_name", placeholder="اختياري — بيتكتب في الرد")
phone_raw = c2.text_input("رقم موبايل العميل", key="rp_phone", placeholder="01012345678")
STAFF = st.text_input("اسمك (بيتسجّل مع الرد)", key="staff_name")
cp_ = validate_phone(phone_raw) if phone_raw.strip() else None
cust_phone = cp_.value if (cp_ is not None and cp_.ok) else ""
if cp_ is not None:
    st.caption(f"✅ {format_phone_display(cp_.value)}" if cp_.ok else "⚠️ الرقم مش صالح — واتساب هيسيبك تختار جهة الاتصال")
branch = st.radio("الفرع", BRANCHES, key="rp_branch", horizontal=True,
                  format_func=lambda k: (CFG["branches"].get(k) or {}).get("name_ar", k))
binfo = CFG["branches"].get(branch)

PK = phone_key(cust_phone, QUOTE_SECRET) if (cust_phone and QUOTE_SECRET) else ""
prof = customer_profile(events, PK) if PK else None
if prof and prof["optout"]:
    st.warning("🚫 العميل ده طلب إيقاف الرسائل التسويقية والمتابعة — مفيش إرسال ولا متابعة ليه.")
elif prof and prof["label"] != "New":
    st.caption(f"👤 عميل {prof['label']} — {prof['quotes']} عرض قبل كده، حضر {prof['converted']} مرة")

# العرض اللي الكلام عليه (لازم عشان تسجيل المتابعة/الفوات)
cutoff = (now - timedelta(days=14)).isoformat(timespec="seconds")
open_recs = [r for r in recs.values() if r["quote_ts"] and stage_of(r) in ("new", "sent", "booked")
             and r["quote_ts"] >= cutoff and not r["optout"]]
mine = [r for r in open_recs if PK and r["pk"] == PK]
pool = sorted(mine or open_recs, key=lambda r: r["quote_ts"], reverse=True)
qopts = ["—"] + [r["quote_id"] for r in pool]
st.selectbox("العرض اللي الكلام عليه (عشان تسجيل المتابعة)", qopts, key="rp_quote",
             index=1 if (mine and len(qopts) > 1) else 0,
             format_func=lambda i: "— من غير عرض —" if i == "—" else (
                 lambda r: f"{r['quote_id']} · {r['total']:,} ج · {r['branch'] or '—'}"
                 + (f" · {(r.get('contact') or {}).get('name')}" if (r.get('contact') or {}).get('name') else ""))(recs[i]))
qid = st.session_state.get("rp_quote", "—")
rec = recs.get(qid) if qid != "—" else None

# ---------------- الرد ----------------
st.markdown("### 💬 اختار الاعتراض / الرد")
rid = st.selectbox("الرد", [r["id"] for r in RP.REPLIES], key="rp_reply",
                   format_func=lambda i: f"{RP.GROUPS[RP.get(i)['group']].split(' ')[0]} {RP.get(i)['title']}")
tpl = RP.get(rid)
version = st.radio("النسخة", ["short", "long"], horizontal=True, key="rp_version",
                   format_func=lambda k: {"short": "مختصر", "long": "مطوّل"}[k])

cat_offers = [o for o in OC.selectable() if o["status"] == "current" and o.get("after")]
sel_offers = st.multiselect("عروض تتضاف للرد (اختياري)", [o["id"] for o in cat_offers], key="rp_offers",
                            format_func=lambda i: f"{OC.option_label(OC.get(i))} — {OC.get(i)['after']:,}")
today = now.date()
promos_now = active_promotions(load_promos(), branch, today)
sel_promos = st.multiselect("عروض من «إدارة العروض»", [p["id"] for p in promos_now], key="rp_promos",
                            format_func=lambda i: next(f"{p['name']} — {p['promo_price']:,}" for p in promos_now if p["id"] == i)) \
    if promos_now else []
running_fhv = [c for c in CFG["campaigns"] if c.get("type") == "free_home_visit"
               and CP.campaign_state(c, today) == "running"]
t1, t2 = st.columns(2)
inc_branch = t1.toggle("📍 بيانات الفرع", value=("{branch}" in tpl["short"] + tpl["long"]), key="rp_branch_on")
inc_fhv = t2.toggle("🎁 الزيارة المجانية", value=False, key="rp_fhv", disabled=not running_fhv)

offers_text = RP.offer_lines([OC.get(i) for i in sel_offers],
                             [p for p in promos_now if p["id"] in sel_promos])

# بيانات العرض المسجّل (لو اخترته) أو التحاليل اللي في رسالة العميل
_names = list(rec["items"]) if rec else [r.name for r in MSG_TESTS]
_days = []
for _n in _names:
    _h = IDX.get(_n)
    _days.append(_h[0].result_days if _h else None)
inc_quote = st.toggle("🧾 العرض + الكود + التحضير + ميعاد النتيجة", value=bool(rec or MSG_TESTS), key="rp_quote_on",
                      disabled=not (rec or MSG_TESTS),
                      help="من العرض اللي اخترته فوق (أو التحاليل اللي في رسالة العميل)")
_branch_names = [(CFG["branches"].get(b) or {}).get("name_ar", b) for b in BRANCHES]
quote_text = RP.quote_block(rec["items"], rec["total"], discount=rec["discount"]) if (inc_quote and rec) else ""
code_text = RP.code_line(rec["quote_id"]) if (inc_quote and rec and not rec["is_lead"]) else ""
prep_text = prep_block(_names, BUNDLE_COMPONENTS) if (inc_quote or tpl["id"] == "prep") else ""
eta_txt = eta_text(_days) if (inc_quote or tpl["id"] == "result_time") else ""
appt_text = RP.appt_line(rec["appointment"]) if (rec and rec["appointment"]) else ""
cta_text = RP.booking_cta(_branch_names) if (inc_quote and tpl["kind"] in ("quote", "objection")) else ""
fhv_text = (running_fhv[0].get("text_ar", "") if (inc_fhv and running_fhv) else "")
branch_text = config_store.branch_block(binfo) if (inc_branch and binfo) else ""
text0 = RP.render_reply(tpl, version, name=name, lab=LAB_NAME_AR, offers_text=offers_text, fhv_text=fhv_text,
                        branch_text=branch_text, review_url=config_store.resolve_links(CFG, st.secrets)["review_url"],
                        phone=(binfo or {}).get("phone", ""), quote_text=quote_text, code_text=code_text,
                        prep_text=prep_text, eta_text=eta_txt, appt_text=appt_text, cta_text=cta_text)
text = st.text_area("نص الرد (تقدر تعدّله)", value=text0, height=260,
                    key=f"rp_txt_{rid}_{version}_{branch}_{inc_branch}_{inc_fhv}_{','.join(sel_offers)}_{','.join(sel_promos)}"
                        f"_{name.strip()}_{qid}_{inc_quote}_{len(_names)}")

blocked = bool(prof and prof["optout"])
if not blocked:
    wa = share_url(text, cust_phone)
    if len(wa) > MAX_WA_URL:
        st.warning("الرد طويل على لينك واتساب — انسخه (زرار النسخ فوق يمين المربع) والصقه في المحادثة")
        st.code(text, language=None)
        st.link_button("📲 افتح محادثة واتساب (والصق الرد)", f"https://wa.me/{cust_phone}" if cust_phone else "https://wa.me/",
                       use_container_width=True)
    else:
        st.link_button("📲 واتساب للعميل" if cust_phone else "📲 افتح واتساب بالرد ده", wa, use_container_width=True)
        st.code(text, language=None)

# ---------------- تسجيل نتيجة المحادثة ----------------
st.markdown("### 📝 سجّل نتيجة المحادثة")
if not store:
    st.info("التسجيل محتاج تتبّع العروض (gh_events_token / gh_events_repo في Secrets). الرد نفسه شغّال.")
else:
    outcomes = ["none", "followup", "lost"]
    default_i = 1 if (tpl["followup_hours"] and rec) else 0
    outcome = st.radio("النتيجة", outcomes, index=default_i, key="rp_outcome", horizontal=True,
                       format_func=lambda k: {"none": "سجّل الرد بس",
                                              "followup": f"⏰ متابعة بعد {tpl['followup_hours'] or 24} ساعة",
                                              "lost": "❌ فات / مش مكمّل"}[k])
    if rec:
        ok_f, why_f = can_schedule_followup(rec, now, opted=opted)
    elif cust_phone and not (prof and prof["optout"]):
        ok_f, why_f = True, ""
    else:
        ok_f, why_f = False, "اكتب رقم العميل أو اختار العرض الأول"
    if outcome == "followup" and not rec and ok_f:
        st.caption("🟡 مفيش عرض — العميل هيتسجّل «مستفسر» (Lead) ويظهر في Follow-up، وبيتقفل لوحده لما تعمله عرض سعر.")
    if outcome == "followup":
        st.caption("✅ تقدر تسجّل متابعة" if ok_f else f"⚠️ مش هتتسجّل متابعة: {why_f}")
    reason = None
    if outcome == "lost":
        from tracking import LOST_SALE_REASONS
        reason = st.selectbox("سبب عدم الإتمام", LOST_SALE_REASONS, key="rp_reason",
                              index=LOST_SALE_REASONS.index(tpl["reason"]) if tpl["reason"] in LOST_SALE_REASONS else 0)

    def log(*evs):
        try:
            for e in evs:
                store.append(events_path(month_key()), e)
            load_events.clear()
            return True
        except GithubStoreError as e:
            st.error(f"مقدرتش أسجّل: {e}")
            return False

    if st.button("✅ سجّل المحادثة", key="rp_log", type="primary", use_container_width=True):
        if outcome == "lost" and not rec:
            st.error("اختار العرض اللي الكلام عليه الأول عشان تسجّل فوات")
        elif outcome == "followup" and not rec and not ok_f:
            st.error(f"مش هتتسجّل متابعة: {why_f}")
        else:
            lead_id = new_lead_id(now) if (outcome == "followup" and not rec) else ""
            evs = [make_event("reply", qid if rec else lead_id, branch=branch, staff=STAFF.strip(), phone_key=PK,
                              meta={"objection": tpl["objection"], "kind": tpl["kind"], "reply": rid, "version": version})]
            note = "اتسجّل الرد"
            if lead_id:
                evs.insert(0, make_event(
                    "lead", lead_id, branch=branch, referral_source=WHATSAPP_SOURCE, phone_key=PK, staff=STAFF.strip(),
                    contact=({"name": name.strip(), "phone": cust_phone} if STORE_CONTACTS else None),
                    note=rid, meta={"next_due": (now + timedelta(hours=tpl["followup_hours"] or 24)).isoformat(timespec="seconds"),
                                    "via": "reply"}))
                note += " + اتسجّل مستفسر (Lead) بمتابعة"
            if outcome == "followup" and rec:
                if ok_f:
                    evs.append(make_event("followup", qid, branch=branch, staff=STAFF.strip(),
                                          meta={"next_due": (now + timedelta(hours=tpl["followup_hours"] or 24)).isoformat(timespec="seconds"),
                                                "via": "reply", "reply": rid}))
                    note += " + متابعة اتجدولت"
                else:
                    note += f" (من غير متابعة: {why_f})"
            elif outcome == "lost" and rec:
                evs.append(make_event("lost_sale", qid, branch=branch, reason=reason, total=rec["total"], staff=STAFF.strip()))
                note += " + العرض اتسجّل «فات»"
            if log(*evs):
                st.success(f"✅ {note}")

    if tpl["action"] == "optout":
        if PK:
            if st.button("🚫 سجّل إيقاف الرسائل لرقم العميل", key="rp_optout", use_container_width=True):
                if log(make_event("optout", qid if rec else "", branch=branch, phone_key=PK)):
                    st.success("✅ اتسجّل — الرقم ده مش هيظهر في المتابعة ولا الرسائل التسويقية")
        else:
            st.caption("لتسجيل الإيقاف لازم رقم عميل صالح + quote_secret")
