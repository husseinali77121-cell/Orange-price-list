#!/usr/bin/env python3
"""
اختبار كتالوج العروض: القائمة الترحيبية (39 رقم)، العروض المنقولة من رسائل المعمل،
مطابقتها بقائمة الأسعار، الرسائل، التصميم، والربط بالفاتورة/الاستوديو/صفحة العروض.
    python3 test_offers_catalog.py
"""
import json
import sys
from urllib.parse import unquote

import fake_streamlit as fs
import github_store as gs
import offers_catalog as OC
from brand import BRANCH_INFO, OFFERS_PHONE, WORKING_HOURS_AR, branch_maps_url
from bundles import BUNDLE_CATEGORY, BUNDLES
from labs_price_list import LABS_DB
from marketing_templates import SIZES, render_template
from offers_data import MENU, OFFERS, PENDING_NOS
from price_utils import MAX_WA_URL, build_index, validate_phone
from tracking import month_key, phone_key

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:68} got={got}")
    if not ok:
        fails.append((label, got, want))


IDX = build_index(LABS_DB, BUNDLES, BUNDLE_CATEGORY)
byid = {o["id"]: o for o in OFFERS}

# ------------------------------------------------------------
# 1) القائمة الترحيبية
# ------------------------------------------------------------
check("menu has 39 numbers 1..39", [n for n, _ in MENU], list(range(1, 40)))
menu = OC.menu_message()
lines = menu.splitlines()
check("menu greeting", lines[0], "مرحبًا بكم في معمل أورانج لاب للتحاليل الطبية 🌟")
check("menu instruction", lines[1], "للاستفسار عن أي عرض، يُرجى كتابة رقم العرض، وسنرد عليك بكافة التفاصيل:")
check("menu item 1 keycap", lines[2], "1️⃣ تساقط الشعر وعلاجه")
check("menu item 10 keycap", "🔟 تحاليل الضعف الجنسي وتأخر الإنجاب (يُرجى تحديد الجنس)" in lines, True)
check("menu item 11+ style", "🔵 11 - عرض أهم فيتامينات الجسم" in lines, True)
check("menu item 39 text", "🔵 39 - تحاليل حديثي الولادة والفحص المبكر للأمراض الوراثية" in lines, True)
i27 = lines.index("🔵 27 - إلغاء خدمة إرسال العروض للواتساب")
check("phone line right after item 27 (as in the original)", lines[i27 + 1], f"📞 ت: {OFFERS_PHONE}")
check("item 28 follows the phone line", lines[i27 + 2], "🔵 28 - تحاليل ما قبل الزواج")
check("menu has working hours", WORKING_HOURS_AR in menu, True)
check("menu has both branch map links", all(i["maps"] in menu for i in BRANCH_INFO.values()), True)
check("menu has both addresses", all(i["address"] in menu for i in BRANCH_INFO.values()), True)
check("menu without branches/hours",
      (OC.menu_message(with_branches=False, with_hours=False).endswith("الفحص المبكر للأمراض الوراثية")), True)
check("branch map links as provided", (BRANCH_INFO["Orange (La Cité)"]["maps"], BRANCH_INFO["Diamond"]["maps"]),
      ("https://maps.app.goo.gl/XR1kcfeN1XJ36i3J7?g_st=ac", "https://maps.app.goo.gl/zvE73ScU1ykTE7vNA"))
check("branch_maps_url falls back for unknown branch", branch_maps_url("Nowhere").startswith("https://maps.app.goo.gl/"), True)

# ------------------------------------------------------------
# 2) سلامة البيانات
# ------------------------------------------------------------
ids = [o["id"] for o in OFFERS]
check("offer ids unique", len(ids), len(set(ids)))
check("valid statuses", {o["status"] for o in OFFERS} <= set(OC.STATUS_LABELS), True)
cov = OC.coverage()
check("every menu number has an entry", [n for n, v in cov.items() if not v], [])
check("no number is legacy-only", [n for n, v in cov.items() if v and set(v) == {"legacy"}], [])
check("pending = exactly the numbers without details",
      sorted(n for n, v in cov.items() if v == ["pending"]), sorted(PENDING_NOS))
bad = [o["id"] for o in OFFERS if o["before"] and o["after"] and o["after"] >= o["before"]]
check("after < before everywhere", bad, [])
check("prices are positive ints", [o["id"] for o in OFFERS
                                   if any(o[k] is not None and (not isinstance(o[k], int) or o[k] <= 0)
                                          for k in ("before", "after"))], [])
check("every db name exists in the price list", [(o["id"], n) for o in OFFERS for n in o["db"] if not IDX.get(n)], [])
check("bundle refs are real bundles", [(o["id"], n) for o in OFFERS for n in o["bundle_refs"]
                                       if n not in {b.name for b in IDX.bundles}], [])
check("sendable offers have a message source", [o["id"] for o in OFFERS if o["status"] == "current"
                                                and not (o["override"] or o["tests"])], [])
check("2-digit menu number for each current offer exists in MENU", [o["id"] for o in OFFERS
                                                                    if o["no"] is not None and o["no"] not in dict(MENU)], [])

# النسخة الحالية أقرب لقائمة الأسعار من القديمة (ده اللي حدّد مين current)
for o in OFFERS:
    if o["status"] == "legacy":
        cur = byid[o["id"].replace("-v1", "")]
        a, b = OC.price_check(cur, IDX), OC.price_check(o, IDX)
        if a["status"] != "unknown":
            check(f"{cur['id']}: current closer to list than legacy", abs(a["delta"]) < abs(b["delta"]), True)
        check(f"{cur['id']}: legacy cheaper (older prices)", o["before"] < cur["before"] and o["after"] < cur["after"], True)

# ------------------------------------------------------------
# 3) مطابقة الأسعار بالقائمة
# ------------------------------------------------------------
for oid in ("1", "7", "20", "23", "24"):
    pc = OC.price_check(byid[oid], IDX)
    check(f"offer {oid} matches the price list exactly", (pc["status"], pc["delta"]), ("ok", 0))
check("Orange 1 current within 3% of list", OC.price_check(byid["4"], IDX)["status"], "ok")
check("Orange 1 legacy flagged as stale", OC.price_check(byid["4-v1"], IDX)["status"], "list_higher")
pc13 = OC.price_check(byid["13"], IDX)
check("thyroid: list 870 vs offer 650 -> implied saving 220", (pc13["status"], pc13["list_sum"], pc13["implied_saving"]),
      ("no_before", 870, 220))
check("chronic fatigue can't be compared (tests unnamed)", OC.price_check(byid["8"], IDX)["status"], "unknown")
check("thyroid offer conflicts with the app's Thyroid Profile bundle",
      OC.bundle_conflicts(IDX), [{"offer_id": "13", "offer_price": 650, "bundle": "Thyroid Profile", "bundle_price": 870}])
check("discount pct computed from real numbers", (OC.discount_pct(byid["4"]), OC.saving(byid["4"])), (20.4, 960))
check("check-up stated 25% vs real", (byid["2"]["pct"], OC.discount_pct(byid["2"])), ("25%", 25.2))

# ------------------------------------------------------------
# 4) رسائل العروض
# ------------------------------------------------------------
m4 = OC.offer_message(byid["4"], IDX)
check("Orange 1 message: prices", all(x in m4 for x in ("قبل الخصم: 4,710 ج", "بعد الخصم: 3,750 ج", "وفّر 960 ج")), True)
check("Orange 1 message: note + phone", "مقاومة الأنسولين" in m4 and OFFERS_PHONE in m4, True)
check("Orange 1 message lists tests inline (14 > 10)", "• CBC، HbA1c" in m4, True)
check("overweight message: fasting 10h", "يتطلب صيام 10 ساعات" in OC.offer_message(byid["7"], IDX), True)
check("insulin resistance: fasting 8h + water/meds", all(x in OC.offer_message(byid["15"], IDX)
                                                         for x in ("يتطلب صيام 8 ساعات", "مسموح بالمياه والعلاج فقط", "450")), True)
m13 = OC.offer_message(byid["13"], IDX)
check("thyroid keeps both prices (650 and 1000)", "650" in m13 and "1000" in m13, True)
m17 = OC.offer_message(byid["17"], IDX)
check("cervical swab keeps both types and prices", all(x in m17 for x in ("450", "3000", "Vaginal panel by PCR")), True)
m2 = OC.offer_message(byid["2"], IDX)
check("check-up points to Orange 1 & 2 by number", "رقم 4" in m2 and "رقم 5" in m2, True)
check("pending offer has no message", OC.offer_message(byid["12"], IDX), "")
check("pending offer is not sendable", OC.is_sendable(byid["12"]), False)
m27 = OC.offer_message(byid["27"], IDX)
check("opt-out reply is a service message (no sales CTA)", ("تم إيقاف" in m27, "للحجز" in m27), (True, False))
m30 = OC.offer_message(byid["30"], IDX)
check("liver/kidney from app bundles with saving", "Liver Profile: 850 ج (وفّر 320 ج)" in m30 and "Kidney Profile: 850 ج (وفّر 300 ج)" in m30, True)
check("lipid from app bundle", "Lipid Profile: 700 ج" in OC.offer_message(byid["32"], IDX), True)
check("location block: one branch", (BRANCH_INFO["Diamond"]["maps"] in OC.offer_message(byid["4"], IDX, branch="Diamond", with_location=True),
                                     BRANCH_INFO["Orange (La Cité)"]["maps"] in OC.offer_message(byid["4"], IDX, branch="Diamond", with_location=True)),
      (True, False))
check("location block: both branches when unknown", all(i["maps"] in OC.offer_message(byid["4"], IDX, with_location=True)
                                                        for i in BRANCH_INFO.values()), True)
check("hours appended on request", WORKING_HOURS_AR in OC.offer_message(byid["4"], IDX, with_hours=True), True)
allmsgs = {o["id"]: OC.offer_message(o, IDX) for o in OFFERS if OC.is_sendable(o)}
check("no message contains None / markup", [i for i, t in allmsgs.items() if "None" in t or "[[" in t], [])
check("every sendable message is non-empty", [i for i, t in allmsgs.items() if not t.strip()], [])
too_long = sorted(i for i, t in allmsgs.items() if len("https://wa.me/20" + "1" * 10 + "?text=" + __import__("urllib.parse").parse.quote(t, safe="")) > MAX_WA_URL)
print("INFO  messages too long for a wa.me link (UI falls back to copy):", too_long)

# ------------------------------------------------------------
# 5) تصميم العروض
# ------------------------------------------------------------
priced = [o for o in OFFERS if o["status"] == "current" and o["after"]]
f4 = OC.studio_fields(byid["4"])
check("studio fields: prices", (f4["badge_value"], f4["old_price"], f4["badge_mode"]), ("3750", "4710", "price"))
check("studio fields: at most 7 rows, last one summarises", (len(f4["items"].splitlines()), f4["items"].splitlines()[-1]),
      (7, "و 8 تحاليل أخرى"))
check("studio: stated percent used as subtitle", OC.studio_fields(byid["2"])["subtitle"], "خصم 25%")
check("studio: fasting used as subtitle", OC.studio_fields(byid["7"])["subtitle"], "يتطلب صيام 10 ساعات")
check("studio: 'starting from' badge for cervical swab", OC.studio_fields(byid["17"])["badge_top"], "ابتداءً من")
check("studio: price without 'before' leaves old price empty", OC.studio_fields(byid["13"])["old_price"], "")
try:
    OC.studio_fields(byid["12"])
    check("studio refuses pending offer", "no error", "ValueError")
except ValueError:
    check("studio refuses pending offer", True, True)
bad_render = []
for o in priced:
    f = OC.studio_fields(o)
    f.pop("template")
    f["photo"] = "sugar"
    try:
        for size in ("post", "story"):
            assert render_template("offer", size, f).size == SIZES[size]
    except Exception as e:  # noqa: BLE001
        bad_render.append((o["id"], str(e)))
check(f"all {len(priced)} priced offers render (post + story)", bad_render, [])

# ------------------------------------------------------------
# 6) الربط بالصفحات
# ------------------------------------------------------------
SECRET, PHONE = "abc", "01012345678"
PK = phone_key(validate_phone(PHONE).value, SECRET)
SEC = {"gh_events_token": "t", "gh_events_repo": "u/r", "quote_secret": SECRET}
ITEM = {"uid": "a1", "name": "CBC", "price": 400, "result_days": 1, "collection_notes": "EDTA",
        "category": "HEMATOLOGY", "source": "manual"}


def invoice(state=None, secrets=None, clicks=(), typed=None, events=None):
    gh = fs.FakeGitHub()
    gs.requests = gh
    if events:
        gh.put_json(f"events/{month_key()}.json", events)
    st_ = {"items": [dict(ITEM)], "p_name": "Ahmed Ali Hassan", "p_phone": PHONE}
    st_.update(state or {})
    fake, g = fs.run_script("Invoice.py", state=st_, secrets={**SEC, **(secrets or {})}, clicks=clicks, typed=typed)
    return fake, g, gh


def links(fake):
    return [unquote(c[2]) for c in fake.calls if c[0] == "link"]


fake, g, gh = invoice()
check("invoice: welcome menu is too long for a link -> shown for copy + open-chat link",
      (any("للاستفسار عن أي عرض" in m for m in fake.messages("code")),
       "https://wa.me/201012345678" in links(fake)), (True, True))

fake, g, gh = invoice(typed={"cat_pick": "4"})
check("invoice: offer 4 message with prices", any("قبل الخصم: 4,710 ج" in l and "بعد الخصم: 3,750 ج" in l for l in links(fake)), True)
check("invoice: offer image + PNG/JPG buttons + share", (
    any(c[0] == "image" for c in fake.calls),
    {"⬇️ حمّل الصورة (PNG)", "⬇️ JPG (أخف)"} <= {c[1] for c in fake.calls if c[0] == "download"},
    any("navigator.share" in c[1] for c in fake.calls if c[0] == "components.html")), (True, True, True))

fake, g, gh = invoice(typed={"cat_pick": "12"})
check("invoice: pending number warns and sends nothing", (
    any("من غير تفاصيل" in m for m in fake.messages("warning")),
    any("12" in l and "wa.me" in l and "عرض فيتامين د" in l for l in links(fake))), (True, False))

fake, g, gh = invoice(typed={"cat_pick": "12"}, secrets={"x": 1}, state={"p_phone": ""})
check("invoice: no customer phone -> link without number", any(l.startswith("https://wa.me/?text=") for l in links(fake)), True)

# تطبيق العرض: تحاليل حقيقية + خصم ثابت يوصّل لسعر العرض بالظبط
fake, g, gh = invoice(state={"items": []}, typed={"cat_pick": "7"}, clicks={"cat_apply_7"})
names = sorted(i["name"] for i in fake.session_state["items"])
check("apply offer 7: the 8 tests are on the invoice",
      names, sorted(["HOMA1-IR", "Lipid Profile", "FT3", "FT4", "TSH", "HbA1C", "ALT (SGPT)", "Creatinine (Serum)"]))
check("apply offer 7: fixed discount 720 -> total = offer price 2100",
      (fake.session_state["discount_type"], fake.session_state["discount_value"], g["totals"]["total"]),
      ("Fixed Amount", 720.0, 2100))
check("apply offer 7: success flash", any("اتطبّق" in m for m in fake.messages("success")), True)
q = [e for e in gh.events() if e["type"] == "quote"]
check("applied offer is logged on the quote event", (len(q), q[0].get("meta") if q else None, q[0]["total"] if q else None),
      (1, {"offer": "7"}, 2100))

pol = {"discount_limit_pct": 20, "discount_approval_pin": "1234"}
fake, g, gh = invoice(state={"items": []}, typed={"cat_pick": "7"}, clicks={"cat_apply_7"}, secrets=pol)
check("offer discount (25%) is pre-approved even with a 20% policy",
      ([e["type"] for e in gh.events()], "الخصم محتاج موافقة المسؤول" in g["blockers"]), (["quote"], False))
fake, g, gh = invoice(state={"discount_type": "Percentage", "discount_value": 30.0, "disc_Percentage_0": 30.0},
                      secrets=pol, typed={"cat_pick": "7"})
check("a manual 30% discount still needs approval", ([e["type"] for e in gh.events()], "الخصم محتاج موافقة المسؤول" in g["blockers"]),
      ([], True))

fake, g, gh = invoice(state={"items": [], "discount_type": "Fixed Amount", "discount_value": 50.0,
                             "disc_Fixed Amount_0": 50.0}, typed={"cat_pick": "7"}, clicks={"cat_apply_7"})
check("existing discount is never overwritten (warns instead)",
      (fake.session_state["discount_value"], any("خصم متسجّل" in m for m in fake.messages("warning"))), (50.0, True))

fake, g, gh = invoice(state={"items": []}, typed={"cat_pick": "8"})
check("offer with unnamed tests: no apply button, explains why",
      (not any(c[0] == "button" for c in fake.calls), any("مش مسمّاة" in str(c) for c in fake.calls if c[0] == "caption")), (True, True))

# 27 = إلغاء الرسائل
fake, g, gh = invoice(typed={"cat_pick": "27"}, clicks={"cat_optout"})
oo = [e for e in gh.events() if e["type"] == "optout"]
check("27: opt-out button logs the phone key", (len(oo), oo[0].get("pk") if oo else None), (1, PK))
fake, g, gh = invoice(typed={"cat_pick": "27"}, clicks={"cat_optout"}, secrets={"quote_secret": ""})
check("27: no quote_secret -> no opt-out written, explained", ([e["type"] for e in gh.events() if e["type"] == "optout"],
                                                              any("quote_secret" in str(c) for c in fake.calls if c[0] == "caption")), ([], True))
hist = [{"type": "optout", "quote_id": "X", "pk": PK, "ts": "2026-11-01T10:00:00"}]
fake, g, gh = invoice(events=hist)
opts = fake.options["cat_pick"]
check("opted-out customer: only service replies are offered (no menu, no sales offers)",
      (opts, "menu" in opts, any("طلب إيقاف" in m for m in fake.messages("warning"))),
      (["26", "27"], False, True))
check("opted-out customer: no promotional text is sent", not any(
    "بعد الخصم" in l or "للاستفسار عن أي عرض" in l for l in links(fake) + fake.messages("code")), True)
fake, g, gh = invoice()
check("normal customer: menu first, then all non-legacy entries",
      (fake.options["cat_pick"][0], "4" in fake.options["cat_pick"], "4-v1" in fake.options["cat_pick"]),
      ("menu", True, False))

# الاستوديو
SS = "pages/2_Marketing_Studio.py"
gh = fs.FakeGitHub()
gs.requests = gh
fake, g = fs.run_script(SS, secrets=SEC, state={"ms_bundle_pick": "o:4", "ms_branch": "Diamond"})
opts = fake.options["ms_bundle_pick"]
check("studio: ONE box lists bundles (Lipid/Liver/Kidney) and numbered offers",
      (all(f"b:{n}" in opts for n in ("Lipid Profile", "Liver Profile", "Kidney Profile")),
       "o:4" in opts, "o:12" in opts, "o:4-v1" in opts), (True, True, False, False))
check("studio: no separate catalog selector left in the sidebar", "ms_cat" in fake.options, False)
g["fill_from_pick"]("Diamond")
st_ = fake.session_state
check("studio fill from catalog: fields", (st_["ms_title_big"], st_["ms_badge_value"], st_["ms_old_price"], st_["ms_template"]),
      ("أورانج 1", "3750", "4710", "offer"))
fake2, g2 = fs.run_script(SS, secrets=SEC, state=dict(st_))
check("studio renders the catalog design", any(c[0] == "image" for c in fake2.calls), True)
check("studio caption uses the selected branch's map link",
      BRANCH_INFO["Diamond"]["maps"] in fake2.session_state.get("ms_cap_txt", ""), True)
fake3, g3 = fs.run_script(SS, secrets=SEC, state={**st_, "ms_badge_value": "3000"})
check("studio warns if the price is edited away from the catalog price",
      any("غير سعر" in m for m in fake3.messages("warning")), True)

# صفحة العروض: Catalog tab
fake, g = fs.run_script("pages/4_Promotions.py", secrets=SEC)
check("offers page: catalog table + CSV + conflict warning for thyroid",
      (sum(1 for c in fake.calls if c[0] == "dataframe") >= 2,
       any("⬇️ الكتالوج (CSV)" == c[1] for c in fake.calls if c[0] == "download"),
       any("Thyroid Profile" in m for m in fake.messages("warning"))), (True, True, True))

print("\n" + "=" * 78)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
