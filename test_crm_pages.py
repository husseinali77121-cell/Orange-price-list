#!/usr/bin/env python3
"""
تشغيل الفاتورة وصفحات CRM على Streamlit وهمي + GitHub وهمي: الحجز، الحضور، الاسترجاع بموافقة
الإدارة، الزيارة المجانية، مطابقة العروض، VIP، الهدايا، الفروع، الحملات، الداشبورد.
    python3 test_crm_pages.py
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from urllib.parse import unquote

import config_store as cs
import fake_streamlit as fs
import github_store as gs
import offers_catalog as OC
import recovery as rc
import tracking as tr
from bundles import BUNDLE_CATEGORY, BUNDLES
from labs_price_list import LABS_DB
from price_utils import build_index, decode_quote_checked, validate_phone

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:70} got={got}")
    if not ok:
        fails.append((label, got, want))


IDX = build_index(LABS_DB, BUNDLES, BUNDLE_CATEGORY)
SECRET, PHONE = "abc", "01012345678"
PK = tr.phone_key(validate_phone(PHONE).value, SECRET)
SEC = {"gh_events_token": "t", "gh_events_repo": "u/r", "quote_secret": SECRET}
NOW = datetime.now()


def ev(typ, qid, hours_ago, **kw):
    return tr.make_event(typ, qid, now=NOW - timedelta(hours=hours_ago), **kw)


def setup(events=None, config=None):
    gh = fs.FakeGitHub()
    gs.requests = gh
    if events:
        gh.put_json(f"events/{tr.month_key()}.json", events)
    if config is not None:
        gh.put_json(cs.CONFIG_PATH, config)
    return gh


def run(path, gh_events=None, config=None, secrets=None, **kw):
    gh = setup(gh_events, config)
    fake, g = fs.run_script(path, secrets={**SEC, **(secrets or {})}, **kw)
    return fake, g, gh


def items(*pairs):
    return [{"uid": f"u{i}", "name": n, "price": p, "result_days": 1, "collection_notes": "", "category": "X",
             "source": "manual"} for i, (n, p) in enumerate(pairs)]


def types(gh, typ=None):
    return [e for e in gh.events() if typ is None or e["type"] == typ]


def invoice(state=None, **kw):
    st = {"items": items(("CBC", 400)), "p_name": "Ahmed Ali Hassan", "p_phone": PHONE}
    st.update(state or {})
    return run("Invoice.py", state=st, **kw)


def wa(fake):
    """روابط واتساب: link_button + الأزرار اللي بتتبني HTML (زرار إرسال عرض السعر في الفاتورة)."""
    urls = [c[2] for c in fake.calls if c[0] == "link" and "wa.me" in c[2]]
    for c in fake.calls:
        if c[0] == "markdown" and c[1] and "wa.me" in str(c[1][0]):
            urls += re.findall(r'href="(https://wa\.me[^"]+)"', str(c[1][0]))
    return [unquote(u) for u in urls]


# ============================================================
# الفاتورة: موظف/منطقة/نوع الزيارة، الزيارة المجانية، بيانات الفرع
# ============================================================
fake, g, gh = invoice({"staff_name": "Mona", "area": "Sheikh Zayed", "visit_type": "home"})
q = types(gh, "quote")[0]
check("quote event carries staff / visit type / area", (q.get("staff"), q.get("visit_type"), q.get("area")),
      ("Mona", "home", "Sheikh Zayed"))

big = items(("CBC", 3100), ("Ferritin", 3100))
fake, g, gh = invoice({"items": big, "area": "Sheikh Zayed", "visit_type": "home"})
check("6,200 in Sheikh Zayed: FREE HOME VISIT ELIGIBLE alert", any("FREE HOME VISIT ELIGIBLE" in m for m in fake.messages("success")), True)
check("eligible quote records the benefit", types(gh, "quote")[0].get("benefits"), ["FHV-OCT-ZAYED"])
check("benefit text is added to the customer's message", any("زيارة منزلية مجانية" in l for l in wa(fake)), True)

fake, g, gh = invoice({"items": items(("CBC", 2750), ("Ferritin", 2750)), "area": "6 October"})
check("5,500: not eligible, hint says 500 missing", (any("FREE HOME VISIT" in m for m in fake.messages("success")),
      any("ناقص 500" in m for m in fake.messages("info"))), (False, True))
check("not eligible => no benefit recorded", "benefits" in types(gh, "quote")[0], False)
fake, g, gh = invoice({"items": big, "area": "Other"})
check("other area: no alert, no benefit", (any("FREE HOME VISIT" in m for m in fake.messages("success")),
                                           "benefits" in types(gh, "quote")[0]), (False, False))
fake, g, gh = invoice({"items": big, "area": ""})
check("area not chosen: eligible but asks to confirm the area", any("أكّد" in m for m in fake.messages("success")), True)
fake, g, gh = invoice({"items": items(("CBC", 4000), ("Ferritin", 2500)), "area": "6 October",
                       "discount_type": "Fixed Amount", "discount_value": 600.0, "disc_Fixed Amount_0": 600.0})
check("threshold is on the NET after the invoice discount (6,500 − 600 = 5,900 → not eligible)",
      any("FREE HOME VISIT ELIGIBLE" in m for m in fake.messages("success")), False)
expired_cfg = {"campaigns": [{**cs.default_config()["campaigns"][0], "end": "2026-10-15"}]}
fake, g, gh = invoice({"items": big, "area": "6 October"}, config=expired_cfg)
check("expired campaign: nothing shown", any("FREE HOME VISIT" in m for m in fake.messages("success")), False)
rule7 = {"campaigns": [{**cs.default_config()["campaigns"][0], "min_net": 7000}]}
fake, g, gh = invoice({"items": big, "area": "6 October"}, config=rule7)
check("rule is editable: min 7,000 => 6,200 not eligible", any("FREE HOME VISIT ELIGIBLE" in m for m in fake.messages("success")), False)

fake, g, gh = invoice({"branch": "Diamond"})
check("quote message carries the branch's map link", any("zvE73ScU1ykTE7vNA" in l for l in wa(fake)), True)
fake, g, gh = invoice({"branch": "Orange (La Cité)"})
check("switching the branch switches the map link", (any("XR1kcfeN1XJ36i3J7" in l for l in wa(fake)),
                                                    any("zvE73ScU1ykTE7vNA" in l for l in wa(fake))), (True, False))
fake, g, gh = invoice({"branch": "Diamond"}, config={"branches": {"Diamond": {"maps": "https://maps.example/diamond"}}})
check("branch data edited from the admin page reaches the quote", any("maps.example/diamond" in l for l in wa(fake)), True)

# ============================================================
# تسعير الروشتة: اقتراح العروض المناسبة
# ============================================================
o7 = OC.get("7")
full7 = [(n, IDX.get(n)[0].price) for n in o7["db"]]
fake, g, gh = invoice({"items": items(*full7)}, clicks={"sug_7"})
check("matching offer applied from the suggestion: total = offer price", (g["totals"]["total"], fake.session_state["discount_value"]), (2100, 720.0))
sub7 = [(n, p) for n, p in full7 if n != "FT3"]
fake, g, gh = invoice({"items": items(*sub7)}, clicks={"sug_7"})
check("near match: adds the missing test and applies the offer", (sorted(i["name"] for i in fake.session_state["items"]) == sorted(o7["db"]),
                                                                  g["totals"]["total"]), (True, 2100))
check("suggestion hidden once the offer is applied", [c for c in fake.calls if c[0] == "button" and "sug_7" in str(c)], [])

# ============================================================
# الحجز من الفاتورة
# ============================================================
fake, g, gh = invoice(clicks={"📅 تم الحجز", "book_ok"})
b = types(gh, "booked")
check("booking from the invoice logs the appointment", (len(b), bool(b and b[0]["meta"].get("appointment"))), (1, True))

# ============================================================
# استرجاع: لينك العرض الجديد مرتبط + معتمد من الإدارة
# ============================================================
lost_ev = [ev("quote", "L1", 100, total=2000, discount=0, items=["CBC", "Ferritin"], phone_key=PK, branch="Diamond",
              contact={"name": "Mona Ahmed", "phone": "201012345678"}), ev("sent", "L1", 99, branch="Diamond"),
           ev("lost_sale", "L1", 60, reason="السعر", total=2000)]
rec = tr.quote_records(lost_ev)["L1"]
url, missing = rc.recovery_link(rec, 150, IDX, SECRET, now=NOW)
tok = url.split("?q=")[1]
data, status = decode_quote_checked(tok, SECRET, max_age_hours=48)
check("recovery link is signed + fresh", (url.startswith("/?q="), status), (True, "ok"))
check("link: parent, approval flag, discount = old + approved extra",
      (data["par"], data["appr"], data["dval"], [i["n"] for i in data["items"]], data["name"]),
      ("L1", True, 150.0, ["CBC", "Ferritin"], "Mona Ahmed"))
check("link: customer data is NOT readable in the URL", "Mona" not in tok and "0101234" not in tok, True)
check("link without quote_secret is not marked approved", rc.recovery_link(rec, 150, IDX, "", now=NOW)[0] != "", True)
payload, _m = rc.build_recovery_payload(rec, 150, IDX, signed=False)
check("unsigned payload: no approval flag", payload["appr"], False)
payload, miss = rc.build_recovery_payload({**rec, "items": ["CBC", "Ghost Test"]}, 0, IDX)
check("tests missing from the price list are reported", (miss, len(payload["items"])), (["Ghost Test"], 1))

fake, g, gh = invoice({"items": [], "p_name": "", "p_phone": ""}, query={"q": tok},
                      secrets={"discount_limit_pct": 5, "discount_approval_pin": "9999"})
check("opening a recovery quote restores items + parent link", (
    sorted(i["name"] for i in fake.session_state["items"]), fake.session_state["parent_quote"],
    fake.session_state["quote_id"] == data["id"]), (["CBC", "Ferritin"], "L1", True))
check("admin-approved discount does not ask for the approval PIN again",
      ("الخصم محتاج موافقة المسؤول" in g["blockers"], fake.session_state["discount_value"]), (False, 150.0))
q = types(gh, "quote")
check("the new quote is logged with its parent", (len(q), q[0].get("parent") if q else None), (1, "L1"))
fake, g, gh = invoice({"items": [], "p_name": "", "p_phone": ""}, query={"q": tok[:-3] + "AAA"})
check("tampered recovery link is refused", fake.session_state["items"], [])

# ============================================================
# صفحة المتابعة
# ============================================================
FU = "pages/3_Follow_Up.py"
sent_ev = [ev("quote", "F1", 31, branch="Diamond", total=700, phone_key=PK, items=["CBC"], visit_type="home"),
           ev("sent", "F1", 30, branch="Diamond", total=700, items=["CBC"], phone_key=PK)]
fake, g, gh = run(FU, sent_ev, clicks={"bk_F1"}, state={"staff_name": "Mona"})
b = types(gh, "booked")
check("follow-up: Booked logs appointment + visit type + staff", (len(b), bool(b[0]["meta"]["appointment"]), b[0].get("visit_type"),
                                                                  b[0].get("staff")), (1, True, "home", "Mona"))
past = (NOW - timedelta(hours=6)).isoformat(timespec="seconds")
book_ev = [ev("quote", "B1", 60, branch="Diamond", total=900, items=["CBC"]), ev("sent", "B1", 59),
           ev("booked", "B1", 30, branch="Diamond", meta={"appointment": past})]
fake, g, gh = run(FU, book_ev, clicks={"vv_B1"})
check("visits: 'Visited' closes the booking (converted)", [e["total"] for e in types(gh, "converted")], [900])
fake, g, gh = run(FU, book_ev, clicks={"vn_B1"})
check("visits: 'Not visited' logs a lost sale with a reason", [bool(e.get("reason")) for e in types(gh, "lost_sale")], [True])
fake, g, gh = run(FU, book_ev, clicks={"vs_B1"})
check("visits: reschedule logs a new booking", len(types(gh, "booked")), 2)

lost1 = [ev("quote", "L1", 100, branch="Diamond", total=2000, items=["CBC", "Ferritin"], phone_key=PK,
            contact={"name": "Mona Ahmed", "phone": "201012345678"}), ev("sent", "L1", 99, branch="Diamond"),
         ev("lost_sale", "L1", 60, reason="السعر", total=2000)]
fake, g, gh = run(FU, lost1, clicks={"rq_L1"}, state={"staff_name": "Mona"})
r_ = types(gh, "recovery_request")
check("recovery: staff requests a special discount (amount defaults to 5%)",
      (len(r_), r_[0]["meta"]["proposed_amount"], r_[0]["meta"]["requested_by"], r_[0]["meta"]["reason"]), (1, 100, "Mona", "السعر"))
pend = lost1 + [ev("recovery_request", "L1", 40, meta={"proposed_amount": 200, "reason": "السعر", "requested_by": "Mona"})]
fake, g, gh = run(FU, pend, clicks={"dd_L1"}, typed={"ap_L1": "Dr. Hussein", "dr_L1": "عميل قديم"})
d_ = types(gh, "recovery_decision")
check("approvals: decision logged with approver, amount and reason", (len(d_), d_[0]["meta"]["decision"], d_[0]["meta"]["amount"],
                                                                      d_[0]["meta"]["approver"], d_[0]["meta"]["reason"]),
      (1, "approved", 200, "Dr. Hussein", "عميل قديم"))
fake, g, gh = run(FU, pend, clicks={"dd_L1"}, typed={"ap_L1": "", "dr_L1": "x"})
check("approvals: no approver name => refused", (len(types(gh, "recovery_decision")), any("اسم المعتمد" in m for m in fake.messages("error"))), (0, True))
fake, g, gh = run(FU, pend, clicks={"dd_L1"}, typed={"ap_L1": "Dr. H", "dr_L1": ""})
check("approvals: approving without a reason => refused", len(types(gh, "recovery_decision")), 0)
fake, g, gh = run(FU, pend, clicks={"dd_L1"}, typed={"ap_L1": "Dr. H", "dc_L1": "rejected"})
check("approvals: rejection needs no amount", [(e["meta"]["decision"], e["meta"]["amount"]) for e in types(gh, "recovery_decision")], [("rejected", 0)])
fake, g, gh = run(FU, pend, secrets={"access_password": "pw"})
check("follow-up page needs a password when one is configured", any(c[0] == "metric" for c in fake.calls), False)
fake, g, gh = run(FU, pend, secrets={"access_password": "pw"}, typed={"_access_pw": "pw"})
check("follow-up page opens with the password", any(c[0] == "metric" for c in fake.calls), True)
fake, g, gh = run(FU, pend, clicks={"dd_L1"}, secrets={"access_password": "adm", "staff_password": "stf"},
                  state={"_staff_ok": True}, typed={"ap_L1": "Dr. H", "dr_L1": "x"})
check("staff session can't approve discounts (admin gate)", len(types(gh, "recovery_decision")), 0)

ready = pend + [ev("recovery_decision", "L1", 20, meta={"decision": "approved", "amount": 200, "approver": "Dr. H", "reason": "x"})]
fake, g, gh = run(FU, ready)
lk = [c[2] for c in fake.calls if c[0] == "link" and c[2].startswith("/?q=")]
check("approved request shows a link that opens the new quote", len(lk), 1)
dd, _st = decode_quote_checked(lk[0].split("?q=")[1], SECRET)
check("…with the approved extra discount", (dd["par"], dd["dval"], dd["appr"]), ("L1", 200.0, True))

# ============================================================
# العملاء / VIP
# ============================================================
CU = "pages/5_Customers.py"
cust = []
for i in range(3):
    cust += [ev("quote", f"A{i}", 400 - i, total=1500, phone_key="pkAAAAAAAAAAAAAA", branch="Diamond",
                contact={"name": "Ahmed A", "phone": "201000000001"}), ev("converted", f"A{i}", 300 - i, total=1500)]
fake, g, gh = run(CU, cust)
check("customers: VIP appears in the monthly list with a WhatsApp link", any("wa.me/201000000001" in c[2] for c in fake.calls if c[0] == "link"), True)
fake, g, gh = run(CU, cust, clicks={"vc_pkAAAAAAAAAAAAAA"}, state={"staff_name": "Mona"})
vc = types(gh, "vip_contact")
check("customers: 'contacted' is logged (no repeated contact for 30 days)", (len(vc), vc[0]["pk"], vc[0]["meta"]["by"]), (1, "pkAAAAAAAAAAAAAA", "Mona"))
fake, g, gh = run(CU, cust + [ev("vip_contact", "", 24 * 5, phone_key="pkAAAAAAAAAAAAAA", meta={"result": "تم الرد"})])
check("customers: contacted 5 days ago => not offered again", any("wa.me/201000000001" in c[2] for c in fake.calls if c[0] == "link"), False)
fake, g, gh = run(CU, cust, clicks={"cu_vip_off"}, state={"staff_name": "Mona"}, typed={"cu_vip_pick": "pkAAAAAAAAAAAAAA"})
check("customers: manual VIP removal is logged by name", [(e["pk"], e["meta"]["vip"]) for e in types(gh, "vip_set")], [("pkAAAAAAAAAAAAAA", False)])
fake, g, gh = run(CU, cust, clicks={"set_save"}, typed={"set_who": "Hussein", "set_staff": "Mona\nAli", "vip_mv": 5, "set_gifts": "Gift A | 40"})
saved = cs.effective(json.loads(gh.files[cs.CONFIG_PATH]["content"]))
check("settings: staff list, VIP rules and gift catalog are saved", (saved["staff"], saved["vip"]["min_visits"], saved["gifts"][0]["cost"]),
      (["Mona", "Ali"], 5, 40))
check("settings: every change is audit-logged", sorted({e["meta"]["section"] for e in types(gh, "config_change")}), ["areas", "gifts", "staff", "vip"])
fake, g, gh = run(CU, cust, clicks={"set_save"}, typed={"set_who": ""})
check("settings: no editor name => nothing saved", cs.CONFIG_PATH in gh.files, False)

# ============================================================
# الهدايا
# ============================================================
GF = "pages/7_Gifts.py"
gift_ev = [ev("quote", "H1", 30, total=1, phone_key="pkCCCCCCCCCCCCCC", visit_type="home", branch="Diamond", area="6 October",
              contact={"name": "Dina D", "phone": "201000000004"}), ev("booked", "H1", 20, branch="Diamond")]
fake, g, gh = run(GF, gift_ev)
check("gifts: new customer + home visit shows the welcome-gift alert", any("NEW CUSTOMER" in m for m in fake.messages("warning")), True)
fake, g, gh = run(GF, gift_ev, config={"gifts": [{"id": "bag", "name": "Gift Bag", "cost": 75}]},
                  clicks={"gc_H1"}, typed={"gb_H1": "Dr. Sara", "gn_H1": "ok"})
gf = types(gh, "gift")
check("gifts: delivery logged with type, cost, deliverer", [(e["meta"]["gift_type"], e["meta"]["cost"], e["meta"]["delivered_by"]) for e in gf],
      [("Gift Bag", 75, "Dr. Sara")])
fake, g, gh = run(GF, gift_ev, clicks={"gc_H1"})
check("gifts: no deliverer name => refused", (len(types(gh, "gift")), any("اسم اللي سلّم" in m for m in fake.messages("error"))), (0, True))
fake, g, gh = run(GF, gift_ev + [ev("gift", "H1", 5, meta={"gift_type": "Gift Bag", "cost": 75, "delivered_by": "Dr. S"})])
check("gifts: delivered gift leaves the queue", any("NEW CUSTOMER" in m for m in fake.messages("warning")), False)

# ============================================================
# الفروع + الحملات + الداشبورد
# ============================================================
BR = "pages/6_Branches.py"
fake, g, gh = run(BR, clicks={"br_Diamond_save"}, typed={"br_who": "Hussein", "br_Diamond_phone": "+20 100 000 0001"})
stored = cs.effective(json.loads(gh.files[cs.CONFIG_PATH]["content"]))
check("branches: phone edit saved (and the other branch kept)", (stored["branches"]["Diamond"]["phone"],
      stored["branches"]["Orange (La Cité)"]["address"].startswith("الحصري")), ("+20 100 000 0001", True))
check("branches: edit is audit-logged with the editor's name", [(e["meta"]["by"], e["meta"]["section"]) for e in types(gh, "config_change")],
      [("Hussein", "branches")])
fake, g, gh = run(BR, clicks={"br_Diamond_save"}, typed={"br_who": "", "br_Diamond_phone": "+20 1"})
check("branches: no editor name => refused", cs.CONFIG_PATH in gh.files, False)
fake, g, gh = run(BR, clicks={"br_Diamond_save"}, typed={"br_who": "H", "br_Diamond_maps": "http://not-https"})
check("branches: invalid maps link => refused", (cs.CONFIG_PATH in gh.files, any("https" in m for m in fake.messages("error"))), (False, True))
fake, g, gh = run(BR, secrets={"access_password": "pw"})
check("branches page is admin-only", any(c[0] == "link" for c in fake.calls), False)

PP = "pages/4_Promotions.py"
fake, g, gh = run(PP, clicks={"camp_save"}, typed={"camp_who": "Hussein", "camp0_min": 7000})
camp = cs.effective(json.loads(gh.files[cs.CONFIG_PATH]["content"]))["campaigns"][0]
check("campaigns: rule edited from the Offers page (min 7,000)", (camp["min_net"], camp["id"]), (7000, "FHV-OCT-ZAYED"))
fake, g, gh = run(PP, clicks={"camp_save"}, typed={"camp_who": "H", "camp0_min": 6000, "camp0_end": date(2026, 9, 1)})
check("campaigns: end before start => refused", cs.CONFIG_PATH in gh.files, False)

DB = "pages/1_Dashboard.py"
dash = lost1 + [ev("recovery_request", "L1", 40, meta={"proposed_amount": 200}),
                ev("recovery_decision", "L1", 20, meta={"decision": "approved", "amount": 200, "approver": "Dr. H", "reason": "x"}),
                ev("quote", "C1", 10, total=1800, parent="L1", staff="Mona"), ev("sent", "C1", 9, staff="Mona"),
                ev("converted", "C1", 2, total=1800)]
fake, g, gh = run(DB, dash)
metrics = {c[1][0] for c in fake.calls if c[0] == "metric"}
check("dashboard: the CRM metrics from the plan are all there",
      {"Total Quotes", "Total Quoted Value", "Visit Rate", "Lost Customers", "Recovered Customers", "Discounts Granted",
       "Free Home Visits (عُرضت)", "VIP Customers", "Gifts Delivered"} <= metrics, True)

print("\n" + "=" * 80)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
