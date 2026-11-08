#!/usr/bin/env python3
"""
اختبار دورة العميل (CRM): مراحل العرض، استرجاع العملاء بموافقة الإدارة، VIP، هدايا العملاء
الجدد، حملة الزيارة المجانية، مطابقة العروض على الفاتورة، إعدادات الإدارة، ومستويات الدخول.
    python3 test_crm.py
"""
import sys
import types
from datetime import date, datetime, timedelta

import access
import campaigns as cp
import config_store as cs
import fake_streamlit as fs
import github_store as gs
import offer_matcher as om
import tracking as tr
from bundles import BUNDLE_CATEGORY, BUNDLES
from labs_price_list import LABS_DB
from offers_data import OFFERS
from price_utils import build_index
from promotions import new_promotion

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:68} got={got}")
    if not ok:
        fails.append((label, got, want))


IDX = build_index(LABS_DB, BUNDLES, BUNDLE_CATEGORY)
NOW = datetime(2026, 11, 7, 12, 0, 0)


def ev(typ, qid, hours_ago, **kw):
    return tr.make_event(typ, qid, now=NOW - timedelta(hours=hours_ago), **kw)


# ------------------------------------------------------------
# 1) مراحل العرض
# ------------------------------------------------------------
appt_past = (NOW - timedelta(hours=5)).isoformat(timespec="seconds")
appt_future = (NOW + timedelta(days=1)).isoformat(timespec="seconds")
E = [
    ev("quote", "N1", 50, total=500), ev("sent", "N1", 49),                                  # sent
    ev("quote", "B1", 60, total=700), ev("sent", "B1", 59), ev("booked", "B1", 30, meta={"appointment": appt_past}),
    ev("quote", "B2", 60, total=700), ev("sent", "B2", 59), ev("booked", "B2", 30, meta={"appointment": appt_future}),
    ev("quote", "V1", 90, total=900), ev("sent", "V1", 89), ev("booked", "V1", 70), ev("visited", "V1", 20),
    ev("quote", "L1", 90, total=1000), ev("sent", "L1", 89), ev("lost_sale", "L1", 60, reason="السعر"),
    ev("quote", "R1", 90, total=400), ev("lost_sale", "R1", 60), ev("booked", "R1", 10),    # رجع بعد ما فات
]
recs = tr.quote_records(E)
check("stages", {k: tr.stage_of(v) for k, v in recs.items()},
      {"N1": "sent", "B1": "booked", "B2": "booked", "V1": "visited", "L1": "lost", "R1": "booked"})
check("'visited' behaves as the final decision (converted)", recs["V1"]["decision"], "converted")
q = tr.followup_queue(E, NOW)
check("visit_check: booking whose appointment passed", [x["quote_id"] for x in q["visit_check"]], ["B1"])
check("upcoming bookings", sorted(x["quote_id"] for x in q["booked"]), ["B2", "R1"])
check("sent-no-booking quote stays in the normal follow-up queue",
      [x["quote_id"] for x in q["due"] + q["upcoming"] + q["stale"] + q["exhausted"]], ["N1"])
check("visited/lost never queued", {"V1", "L1"} & {x["quote_id"] for k in q.values() for x in k}, set())
no_appt = [ev("quote", "B3", 60, total=1), ev("booked", "B3", 30)]
check("booking w/o appointment is checked 24h later", [x["quote_id"] for x in tr.followup_queue(no_appt, NOW)["visit_check"]], ["B3"])
check("booking <24h w/o appointment is just upcoming",
      [x["quote_id"] for x in tr.followup_queue([ev("quote", "B4", 9, total=1), ev("booked", "B4", 5)], NOW)["booked"]], ["B4"])

# ------------------------------------------------------------
# 2) استرجاع العملاء: طلب خصم ← قرار الإدارة ← عرض جديد مرتبط
# ------------------------------------------------------------
REC = [ev("quote", "L2", 100, total=2000, discount=0, items=["CBC"]), ev("lost_sale", "L2", 80, reason="السعر"),
       ev("recovery_request", "L2", 40, meta={"proposed_amount": 200, "reason": "السعر", "requested_by": "Mona"})]
rq = tr.recovery_queue(REC)
check("request is pending", ([x["quote_id"] for x in rq["pending"]], rq["ready"], rq["done"]), (["L2"], [], []))
check("pending carries request details", rq["pending"][0]["recovery"]["request"]["proposed_amount"], 200)
REC2 = REC + [ev("recovery_decision", "L2", 20, meta={"decision": "counter", "amount": 150, "approver": "Dr. Hussein",
                                                       "reason": "عميل قديم"})]
rq = tr.recovery_queue(REC2)
check("counter-offer is ready for a new quote", ([x["quote_id"] for x in rq["ready"]], rq["pending"]), (["L2"], []))
check("decision recorded with approver", rq["ready"][0]["recovery"]["decision"]["approver"], "Dr. Hussein")
REC3 = REC2 + [ev("quote", "C2", 10, total=1850, parent="L2"), ev("sent", "C2", 9), ev("booked", "C2", 8),
               ev("visited", "C2", 2)]
rq = tr.recovery_queue(REC3)
check("new linked quote moves it to done", ([x["quote_id"] for x in rq["done"]], rq["ready"]), (["L2"], []))
REC4 = REC + [ev("recovery_decision", "L2", 20, meta={"decision": "rejected", "approver": "Dr. Hussein", "reason": "x"})]
check("rejected goes to done (no new quote)", [x["quote_id"] for x in tr.recovery_queue(REC4)["done"]], ["L2"])
REC5 = REC2 + [ev("recovery_request", "L2", 5, meta={"proposed_amount": 300, "reason": "تاني"})]
check("a newer request re-opens the decision", [x["quote_id"] for x in tr.recovery_queue(REC5)["pending"]], ["L2"])

# ------------------------------------------------------------
# 3) مؤشرات الإدارة
# ------------------------------------------------------------
K = REC3 + [ev("quote", "S1", 30, total=6200, staff="Mona", visit_type="home", benefits=["FHV-OCT-ZAYED"], area="Sheikh Zayed"),
            ev("sent", "S1", 29, staff="Mona"), ev("booked", "S1", 28), ev("visited", "S1", 5),
            ev("quote", "S2", 30, total=300, staff="Ali"), ev("sent", "S2", 29, staff="Ali"),
            ev("quote", "S3", 30, total=6500, staff="Ali", visit_type="home", benefits=["FHV-OCT-ZAYED"]),
            ev("sent", "S3", 29, staff="Ali"),
            ev("gift", "S1", 4, meta={"gift_type": "Welcome Gift", "cost": 50, "delivered_by": "Dr. A"})]
k = tr.crm_kpis(K, fhv_ids={"FHV-OCT-ZAYED"}, now=NOW)
check("kpi: quotes + quoted value", (k["total_quotes"], k["quoted_value"]), (5, 2000 + 1850 + 6200 + 300 + 6500))
check("kpi: visited (S1 + recovered C2)", k["visited"], 2)
check("kpi: recovered customers", k["recovered"], 1)
check("kpi: additional discounts granted", k["discounts_granted"], 150)
check("kpi: free home visits offered / used", (k["free_visits_offered"], k["free_visits_used"]), (2, 1))
check("kpi: gifts", (k["gifts_delivered"], k["gifts_cost"]), (1, 50))
check("kpi: visit rate = visited / sent (the real metric)", k["visit_rate_pct"], round(100 * 2 / 4, 1))
check("kpi: by staff", (k["by_staff"]["Mona"]["visited"], k["by_staff"]["Ali"]["sent"], k["by_staff"]["Ali"]["visit_rate_pct"]),
      (1, 2, 0.0))
check("kpi: lost", k["lost"], 1)

# ------------------------------------------------------------
# 4) العملاء + VIP
# ------------------------------------------------------------
PA, PB, PC, PD = "pkAAAAAAAAAAAAAA", "pkBBBBBBBBBBBBBB", "pkCCCCCCCCCCCCCC", "pkDDDDDDDDDDDDDD"
CE = []
for i in range(3):
    CE += [ev("quote", f"A{i}", 200 - i * 10, total=1000, phone_key=PA, contact={"name": "Ahmed A", "phone": "201000000001"}),
           ev("visited", f"A{i}", 100 - i * 10, total=1000)]
CE += [ev("quote", "B0", 300, total=500, phone_key=PB, contact={"name": "Bassem B", "phone": "201000000002"}),
       ev("visited", "B0", 200, total=500),
       ev("quote", "C0", 20, total=500, phone_key=PC),
       ev("quote", "D0", 150, total=12000, phone_key=PD, contact={"name": "Dina D", "phone": "201000000004"}),
       ev("visited", "D0", 100, total=12000)]
cu = {c["pk"]: c for c in tr.customers(CE, now=NOW)}
check("3 visits in window => VIP", cu[PA]["label"], "VIP")
check("1 visit => Returning", cu[PB]["label"], "Returning")
check("no visit => New", cu[PC]["label"], "New")
check("spend >= 10,000 => VIP", cu[PD]["label"], "VIP")
check("aggregates (visits, spend, contact)", (cu[PA]["visits"], cu[PA]["spend"], cu[PA]["name"], cu[PA]["has_contact"]),
      (3, 3000, "Ahmed A", True))
check("customer without stored contact", cu[PC]["has_contact"], False)
two = [e for e in CE if e.get("pk") != PA] + [
    ev("quote", "A9", 200, total=1, phone_key=PA), ev("visited", "A9", 100, total=1),
    ev("quote", "A8", 200, total=1, phone_key=PA), ev("visited", "A8", 100, total=1)]
check("2 visits (no VIP rule hit) => Regular", {c["pk"]: c for c in tr.customers(two, now=NOW)}[PA]["label"], "Regular")
check("manual VIP overrides the rules", {c["pk"]: c["label"] for c in tr.customers(
    CE + [ev("vip_set", "", 1, phone_key=PB, meta={"vip": True})], now=NOW)}[PB], "VIP")
check("manual un-VIP overrides the rules", {c["pk"]: c["label"] for c in tr.customers(
    CE + [ev("vip_set", "", 1, phone_key=PA, meta={"vip": False})], now=NOW)}[PA], "Regular")
check("VIP rules are configurable", {c["pk"]: c["label"] for c in tr.customers(
    CE, vip={"min_visits": 1, "min_spend": 10**9, "window_days": 365}, now=NOW)}[PB], "VIP")
check("old visits fall out of the VIP window", {c["pk"]: c["label"] for c in tr.customers(
    CE, vip={"window_days": 1}, now=NOW)}[PA], "Regular")

vf = tr.vip_followups(tr.customers(CE, now=NOW), NOW)
check("monthly VIP list: due", sorted(c["name"] for c in vf["due"]), ["Ahmed A", "Dina D"])
CE2 = CE + [ev("vip_contact", "", 24 * 5, phone_key=PA, meta={"result": "تم الرد"})]
vf = tr.vip_followups(tr.customers(CE2, now=NOW), NOW)
check("contacted 5 days ago => not contacted again (cooldown 30d)",
      (sorted(c["name"] for c in vf["due"]), [c["name"] for c in vf["recent"]]), (["Dina D"], ["Ahmed A"]))
CE3 = CE + [ev("optout", "A0", 3, phone_key=PA)]
check("opted-out VIP is excluded", [c["name"] for c in tr.vip_followups(tr.customers(CE3, now=NOW), NOW)["due"]], ["Dina D"])
vip_nc = [ev("quote", "X0", 200, total=20000, phone_key="pkEEEEEEEEEEEEEE"), ev("visited", "X0", 100, total=20000)]
check("VIP without stored phone is flagged, not messaged",
      [c["pk"] for c in tr.vip_followups(tr.customers(vip_nc, now=NOW), NOW)["no_contact"]], ["pkEEEEEEEEEEEEEE"])

# ------------------------------------------------------------
# 5) هدايا العملاء الجدد
# ------------------------------------------------------------
G = [ev("quote", "H1", 30, total=1, phone_key=PC, visit_type="home"), ev("booked", "H1", 20),
     ev("quote", "H2", 30, total=1, phone_key=PA, visit_type="home"), ev("booked", "H2", 20),       # عميل قديم
     ev("quote", "H3", 30, total=1, phone_key="pkFFFFFFFFFFFFFF", visit_type="lab"), ev("booked", "H3", 20),
     ev("quote", "H4", 30, total=1, visit_type="home"), ev("booked", "H4", 20)]
G += [e for e in CE if str(e.get("quote_id", "")).startswith("A")]   # PA عنده 3 زيارات سابقة
gq = {x["quote_id"]: x for x in tr.gift_queue(G)}
check("gift alert: new customer + home visit", "H1" in gq, True)
check("no gift alert for a returning customer", "H2" in gq, False)
check("no gift alert for a lab visit", "H3" in gq, False)
check("no pk => assumed new but flagged unverified", (gq["H4"]["unverified_new"], gq["H1"]["unverified_new"]), (True, False))
G2 = G + [ev("gift", "H1", 5, meta={"gift_type": "Welcome Gift", "cost": 40, "delivered_by": "Dr. Sara", "note": ""})]
check("delivered gift leaves the queue", "H1" in {x["quote_id"] for x in tr.gift_queue(G2)}, False)
check("gift stats", tr.gift_stats(G2), {"count": 1, "cost": 40, "by_type": {"Welcome Gift": 1}})

# ------------------------------------------------------------
# 6) حملة الزيارة المجانية
# ------------------------------------------------------------
FH = cs.default_config()["campaigns"][0]
D = date(2026, 11, 7)
check("seed rule values", (FH["min_net"], FH["areas"], FH["end"]), (6000, ["6 October", "Sheikh Zayed"], "2026-11-30"))
r = cp.evaluate(FH, net_total=6000, area="Sheikh Zayed", today=D)
check("6,000 exactly in Sheikh Zayed => eligible", (r["eligible"], r["needs_area"]), (True, False))
check("5,999 => not eligible, missing 1", (cp.evaluate(FH, net_total=5999, area="6 October", today=D)["eligible"],
                                           cp.evaluate(FH, net_total=5999, area="6 October", today=D)["missing"]), (False, 1))
check("other area => not eligible", cp.evaluate(FH, net_total=9000, area="Other", today=D)["reason"], "area")
r = cp.evaluate(FH, net_total=9000, area="", today=D)
check("area not chosen yet => eligible but needs area", (r["eligible"], r["needs_area"]), (True, True))
check("valid through the last day (Nov 30)", cp.evaluate(FH, net_total=6000, area="6 October", today=date(2026, 11, 30))["eligible"], True)
check("expired Dec 1", cp.evaluate(FH, net_total=6000, area="6 October", today=date(2026, 12, 1))["state"], "expired")
check("not started before Oct 1", cp.evaluate(FH, net_total=6000, area="6 October", today=date(2026, 9, 30))["state"], "scheduled")
check("inactive campaign", cp.evaluate({**FH, "active": False}, net_total=6000, area="6 October", today=D)["state"], "inactive")
res = cp.evaluate_all([FH], net_total=6500, area="6 October", today=D)
check("benefit ids + texts", (cp.benefit_ids(res), "6,000" in cp.benefit_text(res), "FREE HOME VISIT" in cp.benefit_text(res, "en")),
      (["FHV-OCT-ZAYED"], True, True))
check("benefit text empty when not eligible", cp.benefit_text(cp.evaluate_all([FH], net_total=100, area="6 October", today=D)), "")
check("campaign validation", (cp.validate_campaign(FH), len(cp.validate_campaign({**FH, "min_net": 0, "end": "2026-01-01"}))), ([], 2))

# ------------------------------------------------------------
# 7) مطابقة العروض على الفاتورة (تسعير الروشتة)
# ------------------------------------------------------------
def items_for(names):
    return [{"name": n, "price": IDX.get(n)[0].price, "source": "manual"} for n in names]


o7 = next(o for o in OFFERS if o["id"] == "7")
m = om.match_offers(items_for(o7["db"]), IDX, OFFERS)
top = next(x for x in m if x["offer"]["id"] == "7")
check("full match: saving = invoice tests − offer price (2820 − 2100)", (top["kind"], top["saving"], top["after"]), ("full", 720, 2100))
check("full matches come first", m[0]["kind"], "full")
sub = om.match_offers(items_for([n for n in o7["db"] if n != "FT3"]), IDX, OFFERS)
n7 = next(x for x in sub if x["offer"]["id"] == "7")
check("near match: customer already pays more than the offer -> adding FT3 saves 720",
      (n7["kind"], n7["missing"], n7["extra_cost"], n7["saving"]), ("near", ["FT3"], -450, 720))
o11 = next(o for o in OFFERS if o["id"] == "11")
n11 = next(x for x in om.match_offers(items_for(["Vitamin D3(25 Hydroxy Cholecal.)"]), IDX, OFFERS) if x["offer"]["id"] == "11")
check("near match: add B12 (1500) for +800 -> net saving 700", (n11["kind"], n11["extra_cost"], n11["saving"]), ("near", 800, 700))
check("unrelated invoice => no suggestions", om.match_offers(items_for(["Urea"]), IDX, OFFERS), [])
applied = items_for(o7["db"])
for i in applied:
    i["source"] = "offer:7"
check("already-applied offer is not suggested again", [x for x in om.match_offers(applied, IDX, OFFERS) if x["offer"]["id"] == "7"], [])
check("legacy/pending offers never suggested", {x["offer"]["status"] for x in m}, {"current"})
promo = new_promotion(name="CBC week", target="CBC", original_price=400, promo_price=300,
                      start=date(2026, 11, 1), end=date(2026, 11, 30), now=NOW)
pm = om.match_promotions(items_for(["CBC", "Urea"]), [promo], "Diamond", D)
check("promo match on an invoice item", [(x["item"], x["saving"]) for x in pm], [("CBC", 100)])
check("expired promo ignored", om.match_promotions(items_for(["CBC"]), [promo], "Diamond", date(2026, 12, 5)), [])

# ------------------------------------------------------------
# 8) إعدادات الإدارة
# ------------------------------------------------------------
cfg = cs.default_config()
check("default branches from brand (editable later)", sorted(cfg["branches"]), ["Diamond", "Orange (La Cité)"])
check("branch has address/maps/phone/hours/services", all(cfg["branches"]["Diamond"].get(k) for k in
                                                           ("address", "maps", "phone", "hours", "services")), True)
eff = cs.effective({"branches": {"Diamond": {"phone": "0100", "hours": "24h"}, "New": {"name_ar": "فرع جديد"}},
                    "vip": {"min_visits": 5}, "areas": ["A"]})
check("stored values override defaults field by field", (eff["branches"]["Diamond"]["phone"], eff["branches"]["Diamond"]["address"].startswith("امام")),
      ("0100", True))
check("new branch added from config", eff["branches"]["New"]["name_ar"], "فرع جديد")
check("vip rules merge", (eff["vip"]["min_visits"], eff["vip"]["window_days"]), (5, 365))
check("garbage config falls back to defaults", cs.effective("nope"), cs.default_config())
check("branch validation", (cs.validate_branch(cfg["branches"]["Diamond"]),
                            len(cs.validate_branch({"name_ar": "", "address": "", "maps": "http://x", "hours": ""}))), ([], 4))
blk = cs.branch_block(cfg["branches"]["Diamond"])
check("branch block: address + hours + phone + map", all(x in blk for x in ("📍", "🕘", "📞", "🗺️", "https://maps.app.goo.gl/")), True)
check("compact block: name + map only", cs.branch_block(cfg["branches"]["Diamond"], compact=True).count("\n"), 1)

gh = fs.FakeGitHub()
gs.requests = gh
store = gs.GithubEventStore("t", "u/r")
saved = cs.save_section(store, "branches", {"Diamond": {"phone": "01011112222"}}, who="Hussein", note="phone")
check("save_section persists and reloads", saved["branches"]["Diamond"]["phone"], "01011112222")
check("config change is logged (audit)", [(e["type"], e["meta"]["by"], e["meta"]["section"]) for e in gh.events()],
      [("config_change", "Hussein", "branches")])
try:
    cs.save_section(store, "vip", {}, who=" ")
    check("edit needs the editor's name", "no error", "ValueError")
except ValueError:
    check("edit needs the editor's name", True, True)
check("load without a store = defaults", cs.load(None), cs.default_config())

# ------------------------------------------------------------
# 9) مستويات الدخول
# ------------------------------------------------------------
class FakeST:
    def __init__(self, secrets, state=None, typed=""):
        self.secrets, self.session_state, self.typed, self.out = secrets, dict(state or {}), typed, []

    def warning(self, m): self.out.append("warning")
    def markdown(self, m): pass
    def caption(self, m): pass
    def error(self, m): self.out.append("error")
    def text_input(self, *a, **k): return self.typed
    def rerun(self): self.out.append("rerun")
    def stop(self): raise SystemExit


def gate(level, secrets, typed="", state=None):
    st = FakeST(secrets, state, typed)
    try:
        access.require_access(st, "x", level=level)
        return "passed", st
    except SystemExit:
        return "stopped", st


S = {"access_password": "admin", "staff_password": "staff"}
check("no passwords: open (warning)", (gate("admin", {})[0], gate("admin", {})[1].out), ("passed", ["warning"]))
check("staff page: staff password unlocks it", gate("staff", S, "staff")[1].session_state.get("_staff_ok"), True)
check("staff page: admin password unlocks it too", gate("staff", S, "admin")[1].session_state.get("_access_ok"), True)
r, st_ = gate("admin", S, "staff")
check("admin page: staff password refused with a clear message", (r, st_.out[-1], st_.session_state.get("_staff_ok")), ("stopped", "error", None))
check("admin page: admin password unlocks it", gate("admin", S, "admin")[1].session_state.get("_access_ok"), True)
check("staff session can't open admin pages", gate("admin", S, state={"_staff_ok": True})[0], "stopped")
check("staff session opens staff pages", gate("staff", S, state={"_staff_ok": True})[0], "passed")
check("only access_password set: one password for everything (old behaviour)",
      gate("staff", {"access_password": "pw"}, "pw")[1].session_state.get("_access_ok"), True)
check("wrong password", (gate("staff", S, "nope")[0], gate("staff", S, "nope")[1].out[-1]), ("stopped", "error"))

ag = FakeST({"access_password": "admin"}, typed="admin")
res = access.admin_gate(ag)
check("admin_gate: right password unlocks (session flag set)", (ag.session_state.get("_access_ok"), "rerun" in ag.out), (True, True))
check("admin_gate: wrong password stays locked", (access.admin_gate(FakeST({"access_password": "admin"}, typed="x")), ), (False,))
check("admin_gate: already unlocked", access.admin_gate(FakeST({"access_password": "a"}, {"_access_ok": True})), True)
check("admin_gate: no password configured => open", access.admin_gate(FakeST({})), True)

# ------------------------------------------------------------
# 10) Marketing Studio: اسم/رقم العميل + تبديل الفرع (دياموند / لاسيتيه)
# ------------------------------------------------------------
from urllib.parse import unquote
from price_utils import validate_phone

SS = "pages/2_Marketing_Studio.py"
SEC = {"gh_events_token": "t", "gh_events_repo": "u/r", "quote_secret": "abc"}
CFG_BRANCHES = {"branches": {"Diamond": {"phone": "+20 100 000 0001"}, "Orange (La Cité)": {"phone": "+20 100 000 0002"}}}


def studio(state=None, secrets=None, events=None, cfg=True, typed=None):
    gh2 = fs.FakeGitHub()
    gs.requests = gh2
    if cfg:
        gh2.put_json(cs.CONFIG_PATH, CFG_BRANCHES)
    if events:
        gh2.put_json(f"events/{tr.month_key()}.json", events)
    fake, g = fs.run_script(SS, secrets={**SEC, **(secrets or {})}, state=state or {}, typed=typed)
    return fake, g


def wa_links(fake):
    return [unquote(x[2]) for x in fake.calls if x[0] == "link" and "wa.me" in x[2]]


SHORT = {"ms_branch_info": False, "ms_disc": False, "ms_template": "tip", "ms_headline": "نصيحة", "ms_body": "جملة قصيرة",
         "ms_photo_src": "none"}
fake, g = studio({**SHORT, "ms_cust_name": "Mona Ahmed", "ms_cust_phone": "01012345678"})
cap = fake.session_state["ms_cap_txt"]
check("studio: caption starts with the customer's first name", cap.startswith("أهلاً Mona 🍊"), True)
check("studio: WhatsApp opens straight on the customer's number",
      [l.split("?")[0] for l in wa_links(fake)], ["https://wa.me/201012345678"])
check("studio: the link carries the greeting", any("أهلاً Mona" in l for l in wa_links(fake)), True)
check("studio: button says 'to the customer'", any("واتساب للعميل" in x[1] for x in fake.calls if x[0] == "link"), True)

fake, g = studio({**SHORT, "ms_cust_name": "", "ms_cust_phone": "123"})
check("studio: invalid customer phone -> warned, chat picker (no number)",
      (any("مش صالح" in str(x) for x in fake.calls if x[0] == "caption"),
       [l.split("?")[0] for l in wa_links(fake)]), (True, ["https://wa.me/"]))
fake, g = studio(SHORT)
check("studio: no customer data -> generic greeting-free caption", fake.session_state["ms_cap_txt"].startswith("🍊"), True)

# تبديل الفرع
fake, g = studio({"ms_branch": "Diamond"})
g["on_branch_change"]()
check("studio: switching to Diamond puts Diamond's number on the image", fake.session_state["ms_phone"], "+20 100 000 0001")
fake2, g2 = studio({"ms_branch": "Diamond", "ms_phone": "+20 100 000 0001"})
cap = fake2.session_state["ms_cap_txt"]
check("studio: Diamond caption has its address + map + number (not La Cité's)",
      ("امام دياموند" in cap, "zvE73ScU1ykTE7vNA" in cap, "+20 100 000 0001" in cap, "الحصري" in cap), (True, True, True, False))
fake3, g3 = studio({"ms_branch": "Orange (La Cité)", "ms_phone": "+20 100 000 0002"})
cap = fake3.session_state["ms_cap_txt"]
check("studio: La Cité caption has its address + map + number (not Diamond's)",
      ("الحصري" in cap, "XR1kcfeN1XJ36i3J7" in cap, "+20 100 000 0002" in cap, "امام دياموند" in cap), (True, True, True, False))
fake4, g4 = studio({"ms_branch": "Orange (La Cité)"})
g4["on_branch_change"]()
check("studio: switching back to La Cité", fake4.session_state["ms_phone"], "+20 100 000 0002")
fake5, g5 = studio({"ms_branch": "Diamond", "ms_phone": "+20 111 222 3333"})
check("studio: number on the image can be edited by hand (used in the message too)",
      "+20 111 222 3333" in fake5.session_state["ms_cap_txt"], True)
fake6, g6 = studio({"ms_branch": "Diamond"}, cfg=False)
g6["on_branch_change"]()
check("studio: no stored config -> default branch number", bool(fake6.session_state["ms_phone"]), True)
fake7, g7 = studio({"ms_branch": "Diamond", "ms_branch_info": False})
check("studio: branch info can be switched off", "امام دياموند" in fake7.session_state["ms_cap_txt"], False)

# العميل الموقوف
PKX = tr.phone_key(validate_phone("01012345678").value, "abc")
opt = [tr.make_event("optout", "Q1", now=NOW, phone_key=PKX)]
fake, g = studio({**SHORT, "ms_cust_name": "Mona", "ms_cust_phone": "01012345678"}, events=opt)
check("studio: opted-out customer -> warning and no WhatsApp/Facebook buttons",
      (any("طلب إيقاف" in m for m in fake.messages("warning")) or any("إيقاف" in m for m in fake.messages("warning")),
       [x for x in fake.calls if x[0] == "link"]), (True, []))

# باقة حقيقية من نفس الخانة
fake, g = studio({"ms_bundle_pick": "b:Lipid Profile", "ms_branch": "Diamond"})
g["fill_from_pick"]("Diamond")
check("studio: picking a real bundle in the same box fills the template", (
    fake.session_state["ms_badge_value"], fake.session_state["ms_title_big"], fake.session_state["ms_template"]),
    ("700", "الدهون", "offer"))

print("\n" + "=" * 78)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
