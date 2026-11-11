#!/usr/bin/env python3
"""
تحديث 8 — عملاء الواتساب: من السؤال للحضور.
تحليل المحادثة · الردود الذكية · التحضير · «إرسال + متابعة» بضغطة · المستفسر (Lead) ·
Check-in · Recall · Funnel · ربط الحملة تلقائي · حد الخصم 50% · الاستوديو (الاسم والرقم فوق).
    python3 test_whatsapp_suite.py
"""
import ast
import re
import sys
from datetime import date, datetime, timedelta
from urllib.parse import unquote

import config_store as cs
import fake_streamlit as fs
import github_store as gs
import patient_prep as PP
import recall as RC
import replies as RP
import tracking as tr
import wa_bridge as WB
import wa_inquiry as WI
from bundles import BUNDLE_CATEGORY, BUNDLES
from labs_price_list import LABS_DB
from price_utils import build_index, validate_phone

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:74} got={got}")
    if not ok:
        fails.append((label, got, want))


IDX = build_index(LABS_DB, BUNDLES, BUNDLE_CATEGORY)
NOW = datetime(2026, 11, 11, 12, 0)
SECRET, PHONE = "abc", "01012345678"
E164 = validate_phone(PHONE).value
PK = tr.phone_key(E164, SECRET)
SEC = {"gh_events_token": "t", "gh_events_repo": "u/r", "quote_secret": SECRET}
AREAS = ["6 October", "Sheikh Zayed", "Other"]


def names(T):
    return [r.name for _t, r in T["confident"]]


# ============================================================
# 1) قراءة محادثة الواتساب
# ============================================================
web = ("[10:15 AM, 11/11/2026] Mona Ahmed: مساء الخير\n"
       "[10:16 AM, 11/11/2026] Mona Ahmed: بكام تحليل الغدة الدرقية و فيريتين؟ أنا في الشيخ زايد وعايزة سحب منزلي\n"
       "[10:20 AM, 11/11/2026] Orange Lab: أهلاً بحضرتك")
A = WI.analyze_inquiry(web, IDX, areas=AREAS, now=NOW)
check("web copy: customer name from the sender", A["name"], "Mona Ahmed")
check("web copy: lab's own lines excluded from the customer text", "أهلاً بحضرتك" in A["customer_text"], False)
check("web copy: tests inside a sentence (+ «و فيريتين؟»)", names(A["tests"]), ["Thyroid Profile", "Ferritin"])
check("web copy: area + home visit detected", (A["area"], A["home_visit"]), ("Sheikh Zayed", True))
check("web copy: inquiry time = first customer message", A["inquiry_ts"], datetime(2026, 11, 11, 10, 15))
ios = "[11/11/2026, 09:05] +20 101 234 5678: عايز اعمل cbc و esr و crp\nهل لازم اكون صايم؟"
A = WI.analyze_inquiry(ios, IDX, areas=AREAS, now=NOW)
check("iOS export: phone from an unsaved sender", A["phone"], "201012345678")
check("iOS: multi-line message kept (prep question detected)", [x["reply"] for x in A["intents"]], ["prep"])
check("iOS: CRP is ambiguous -> needs a choice (no guessing)", ([c[0] for c in A["tests"]["choose"]], names(A["tests"])),
      (["crp"], ["CBC", "ESR"]))
check("«صايم» in a question is NOT added as a fasting-sugar test", "FBG" in names(A["tests"]), False)
andr = "11/11/26, 9:40 AM - Ahmed: <Media omitted>\n11/11/26, 9:41 AM - Ahmed: دي الروشتة، الأسعار غالية عندكم؟"
A = WI.analyze_inquiry(andr, IDX, now=NOW)
check("android export: media = prescription photo", (A["has_media"], A["intents"][0]["reply"]), (True, "prescription_received"))
check("android: chat lines don't pollute «not found»", A["tests"], {"confident": [], "choose": [], "missing": []})
check("android: «غالية» -> price objection reply suggested", "price_high" in [x["reply"] for x in A["intents"]], True)
ar = "[١٠:١٥ ص، ١١‏/١١‏/٢٠٢٦] سارة: عايزة اعرف العنوان ومواعيد الشغل"
A = WI.analyze_inquiry(ar, IDX, now=NOW)
check("arabic-digit timestamp parsed", (A["name"], A["inquiry_ts"]), ("سارة", datetime(2026, 11, 11, 10, 15)))
check("address question -> branch info reply", [x["reply"] for x in A["intents"]], ["branch_info"])
A = WI.analyze_inquiry("اسمي احمد محمد علي ورقمي 01112223334 عايز احجز تحليل دهون", IDX, now=NOW)
check("name + phone written inside the message", (A["name"], A["phone"]), ("احمد محمد علي", "201112223334"))
check("«دهون» -> Lipid Profile bundle", names(A["tests"]), ["Lipid Profile"])
A = WI.analyze_inquiry("1- صورة دم\n2- سكر صائم\nفيتامين د، كرياتينين\nTSH + Ferritin", IDX, now=NOW)
check("a plain list still works line by line", len(A["tests"]["confident"]), 6)
check("bare menu number -> offer selection", WI.offer_number("27"), 27)
check("number in a sentence isn't an offer pick", WI.offer_number("عندي 3 تحاليل"), None)
check("future-dated timestamp is ignored (day/month ambiguity)", WI._to_dt("12/11/2026", "10:00", NOW), None)
check("ambiguous day/month -> the reading closest to now", WI._to_dt("11/10/2026", "10:00", NOW), datetime(2026, 11, 10, 10, 0))
check("greeting alone -> welcome reply", [x["reply"] for x in WI.detect_intents("السلام عليكم")], ["welcome"])
check("every intent maps to a real reply", [i for i, rid, _k in WI.INTENTS if not RP.get(rid)], [])

# ============================================================
# 2) تعليمات التحضير + النتيجة
# ============================================================
comp = {b["name"]: b["components"] for b in BUNDLES}
check("Lipid Profile -> fasting 9–12h (from its components)", PP.prep_lines(["Lipid Profile"], comp),
      ["الدهون: صيام 9–12 ساعة قبل السحب (المية مسموحة)"])
check("OGTT before generic fasting rule", PP.prep_for_test("Glucose 2 hr (75 gm Glucose)").startswith("منحنى السكر"), True)
check("PPBG -> 2 hours after a meal", "بعد الأكل" in PP.prep_for_test("PPBG"), True)
check("CBC -> no instruction invented", PP.prep_for_test("CBC"), None)
check("duplicates collapsed", len(PP.prep_lines(["FBG", "Insulin (Fasting)", "CBC"])), 1)
check("eta text", (PP.eta_text([1, None]), PP.eta_text([2]), PP.eta_text([5, 3]), PP.eta_text([])),
      ("⏱️ النتيجة خلال يوم", "⏱️ النتيجة خلال يومين", "⏱️ النتيجة خلال 5 أيام", ""))

# ============================================================
# 3) الردود الذكية
# ============================================================
t = RP.render_reply(RP.get("price_quote"), "short", name="Mona Ahmed",
                    quote_text=RP.quote_block(["CBC", "Ferritin"], 700, discount=100),
                    code_text=RP.code_line("OR-261111-0042"), cta_text=RP.booking_cta(["فرع لاسيتيه", "فرع دياموند"]))
check("quote reply: name + total + discount + code + CTA",
      all(x in t for x in ("أهلاً Mona", "*الإجمالي: 700 ج*", "الخصم: 100", "OR-261111-0042", "3️⃣ سحب منزلي")), True)
check("empty blocks vanish (no triple newlines / braces)", ("\n\n\n" in t, "{" in t), (False, False))
check("prep reply without tests -> asks for the test names",
      "ابعتلنا أسماء التحاليل" in RP.render_reply(RP.get("prep"), "short"), True)
check("appointment line in Egyptian Arabic", RP.appt_line("2026-11-14T18:30:00"), "📅 الميعاد: السبت 14/11 — الساعة 6:30 م")
check("templates only use known placeholders",
      {v for r in RP.REPLIES for v in re.findall(r"\{(\w+)\}", r["short"] + r["long"])} <= RP.VARS, True)
check("new replies exist", {"welcome", "prescription_received", "price_quote", "prep", "result_time", "booking_confirm",
                            "appt_reminder", "missed_appt"} <= {r["id"] for r in RP.REPLIES}, True)

# ============================================================
# 4) تتبّع: إرسال + متابعة، المستفسر، Funnel، Check-in، الحملة
# ============================================================
def ev(typ, qid, hours_ago, **kw):
    return tr.make_event(typ, qid, now=NOW - timedelta(hours=hours_ago), **kw)


E = [ev("quote", "Q1", 30, referral_source=tr.WHATSAPP_SOURCE, total=800, items=["CBC"], phone_key=PK,
        meta={"inquiry_ts": (NOW - timedelta(hours=30, minutes=10)).isoformat()}),
     ev("sent", "Q1", 30, total=800, phone_key=PK, meta={"followup_hours": 3,
                                                          "next_due": (NOW - timedelta(hours=27)).isoformat()})]
fq = tr.followup_queue(E, NOW)
check("sent with a 3h follow-up -> due 3h after sending", [r["due_at"] for r in fq["due"]], [NOW - timedelta(hours=27)])
E0 = [ev("quote", "Q2", 30, total=500), ev("sent", "Q2", 30, total=500, meta={"followup_hours": 0})]
check("«من غير متابعة» -> not in the follow-up list", sum(len(v) for v in tr.followup_queue(E0, NOW).values()), 0)
L = [ev("lead", "LD1", 30, referral_source=tr.WHATSAPP_SOURCE, phone_key=PK,
        meta={"next_due": (NOW - timedelta(hours=6)).isoformat()})]
fq = tr.followup_queue(L, NOW)
check("lead (no quote yet) shows up in follow-up", [r["quote_id"] for r in fq["due"]], ["LD1"])
fq = tr.followup_queue(L + [ev("quote", "Q9", 2, total=300, phone_key=PK), ev("sent", "Q9", 2, total=300, phone_key=PK)], NOW)
check("lead closes by itself once the same phone gets a quote",
      [r["quote_id"] for k in fq for r in fq[k]], ["Q9"])
check("a lead isn't counted as a quote for the customer label", tr.customer_profile(L, PK)["quotes"], 0)
check("leads don't change the quote KPIs", (tr.summarize_events(L)["quotes"], tr.crm_kpis(L)["total_quotes"]), (0, 0))

F = (E + L + [ev("booked", "Q1", 20, meta={"appointment": (NOW - timedelta(hours=1)).isoformat()}),
              ev("converted", "Q1", 1, total=800),
              ev("quote", "Q3", 10, referral_source=tr.WHATSAPP_SOURCE, total=400, phone_key="pk3",
                 meta={"inquiry_ts": (NOW - timedelta(hours=14)).isoformat()}),
              ev("sent", "Q3", 10, total=400, phone_key="pk3"),
              ev("quote", "Q4", 5, referral_source="📘 Facebook", total=999)])
wf = tr.whatsapp_funnel(F)
check("funnel: leads / quotes / sent / visited", (wf["leads"], wf["quotes"], wf["sent"], wf["visited"]), (1, 2, 2, 1))
check("funnel: visit rate + value", (wf["visit_rate_pct"], wf["value_visited"]), (50.0, 800))
check("funnel: response-time buckets (10 min -> visited, 4h -> open)",
      [(b["bucket"], b["sent"], b["visited"]) for b in wf["by_response"]],
      [("أقل من 15 دقيقة", 1, 1), ("أكتر من 3 ساعات", 1, 0)])
check("funnel: median response minutes", wf["median_response_min"], 125.0)
E2 = [ev("quote", "Q5", 5, total=100), ev("sent", "Q5", 5, total=100, referral_source=tr.WHATSAPP_SOURCE,
                                            meta={"inquiry_ts": (NOW - timedelta(hours=5, minutes=20)).isoformat()})]
check("source/inquiry time set at send time still count", (tr.whatsapp_funnel(E2)["quotes"],
                                                          tr.whatsapp_funnel(E2)["median_response_min"]), (1, 20.0))

C = [ev("quote", "Q6", 48, total=600, phone_key=PK), ev("sent", "Q6", 48, total=600, phone_key=PK),
     ev("quote", "Q7", 24, total=300, phone_key="other"),
     ev("quote", "Q8", 24 * 60, total=300, phone_key=PK),
     ev("quote", "Q10", 30, total=300, phone_key=PK), ev("converted", "Q10", 2, total=300)]
check("check-in by phone: open quotes only, recent first",
      [r["quote_id"] for r in tr.open_quotes_for(C, pk=PK, now=NOW)], ["Q6"])
check("check-in by code (case-insensitive)", [r["quote_id"] for r in tr.open_quotes_for(C, code="q7", now=NOW)], ["Q7"])
today = NOW.date()
A2 = [ev("quote", "B1", 30, total=1), ev("booked", "B1", 30, meta={"appointment": f"{today}T16:00:00"}),
      ev("quote", "B2", 30, total=1), ev("booked", "B2", 30, meta={"appointment": f"{today - timedelta(days=2)}T10:00:00"}),
      ev("quote", "B3", 30, total=1), ev("booked", "B3", 30, meta={"appointment": f"{today}T09:00:00"}),
      ev("converted", "B3", 1)]
ap = tr.appointments(A2, today)
check("appointments: today (not visited yet) + overdue", ([r["quote_id"] for r in ap["today"]],
                                                         [r["quote_id"] for r in ap["overdue"]]), (["B1"], ["B2"]))
CA = [ev("campaign", "OL-261101-AB12", 24 * 3, phone_key=PK), ev("campaign", "OL-261020-ZZ99", 24 * 30, phone_key=PK)]
check("campaign attribution: latest ad to this phone within 14 days",
      (tr.last_campaign_for(CA, PK, now=NOW), tr.last_campaign_for(CA, "x", now=NOW)), ("OL-261101-AB12", ""))

# ============================================================
# 5) Recall
# ============================================================
R = [ev("quote", "R1", 24 * 92, total=400, items=["HbA1C", "CBC"], phone_key="p1",
        contact={"name": "Hany", "phone": "201000000001"}),
     ev("converted", "R1", 24 * 91, total=400),
     ev("quote", "R2", 24 * 40, total=700, items=["Lipid Profile"], phone_key="p2"), ev("converted", "R2", 24 * 40)]
rd = RC.recall_due(R, now=NOW)
check("HbA1c visit 91 days ago -> recall due (lipid at 40 days isn't)", [(x["pk"], x["rule"]) for x in rd], [("p1", "hba1c")])
check("recall carries the stored contact", rd[0]["contact"].get("phone"), "201000000001")
check("contacted in the last 30 days -> not repeated",
      RC.recall_due(R + [ev("recall_contact", "R1", 24, phone_key="p1", meta={"rule": "hba1c"})], now=NOW), [])
check("opted-out customer -> no recall", RC.recall_due(R + [ev("optout", "", 1, phone_key="p1")], now=NOW), [])
check("came back and repeated the test -> no recall", RC.recall_due(
    R + [ev("quote", "R3", 24 * 5, items=["HbA1C"], phone_key="p1"), ev("converted", "R3", 24 * 5)], now=NOW), [])
msg = RC.recall_message(lab="معمل أورانج", name="Hany Samir", label="السكر التراكمي (HbA1c)", months=3)
check("recall message: soft wording + opt-out line", ("لو الدكتور طالب" in msg, "إيقاف" in msg, "أهلاً Hany" in msg),
      (True, True, True))

# ============================================================
# 6) حد الخصم + الجسر
# ============================================================
check("discount limit default is 50%", cs.discount_limit(cs.default_config()), 50.0)
check("stored policy overrides (and is clamped)", (cs.discount_limit(cs.effective({"policy": {"discount_limit_pct": 35}})),
                                                   cs.discount_limit(cs.effective({"policy": {"discount_limit_pct": 300}}))),
      (35.0, 100.0))
check("policy section is saveable", "policy" in cs.SECTIONS, True)
check("bridge token round-trip", (WB.parse_token(WB.make_token("sent", "OR-1")), WB.parse_token("hack"),
                                  WB.parse_token("x:1")), (("sent", "OR-1"), None, None))
h = WB.send_button_html('https://wa.me/20?text=a"b', "إرسال <x>", "sent:OR-1")
check("bridge html escapes the url/label and embeds the token", ('href="https://wa.me/20?text=a&quot;b"' in h,
                                                                 "&lt;x&gt;" in h, '"sent:OR-1"' in h), (True, True, True))

# ============================================================
# 7) الفاتورة: لزق المحادثة ← عرض ← «إرسال + متابعة»
# ============================================================
ITEMS = [{"uid": "a1", "name": "CBC", "price": 400, "result_days": 1, "collection_notes": "EDTA",
          "category": "HEMATOLOGY", "source": "manual"},
         {"uid": "a2", "name": "Lipid Profile", "price": 700, "result_days": 1, "collection_notes": "",
          "category": "Profiles", "source": "manual"}]


def invoice(state=None, secrets=None, clicks=(), typed=None, events=None, config=None, with_items=True):
    gh = fs.FakeGitHub()
    gs.requests = gh
    if events:
        gh.put_json(f"events/{tr.month_key()}.json", events)
    if config is not None:
        gh.put_json(cs.CONFIG_PATH, config)
    st_ = {"items": [dict(i) for i in ITEMS] if with_items else [], "p_name": "Ahmed Ali Hassan", "p_phone": PHONE}
    st_.update(state or {})
    fake, g = fs.run_script("Invoice.py", state=st_, secrets={**SEC, **(secrets or {})}, clicks=clicks, typed=typed)
    return fake, g, gh


def evs(gh, typ=None):
    return [e for e in gh.events() if typ is None or e["type"] == typ]


fake, g, gh = invoice(state={"p_name": "", "p_phone": ""}, with_items=False,
                      typed={"wa_raw": web.replace("Mona Ahmed", "+20 101 234 5678")}, clicks={"⚡ حلّل الاستفسار"})
ss = fake.session_state
check("paste: phone filled from the chat", ss["p_phone"], "01012345678")
check("paste: source=WhatsApp, area, home visit", (ss["referral_source"], ss["area"], ss["visit_type"]),
      (tr.WHATSAPP_SOURCE, "Sheikh Zayed", "home"))
check("paste: tests waiting for a one-click review (not auto-added)",
      (ss["bulk_src"], [r.name for _t, r in ss["bulk"]["confident"]], ss["items"]), ("wa", ["Thyroid Profile", "Ferritin"], []))
check("paste: inquiry time stored", ss["inquiry_ts"], "2026-11-11T10:15:00")
check("paste: suggested reply rendered", "wa_sug" in fake.session_state, True)

fake, g, gh = invoice(state={"items": [], "bulk": ss["bulk"], "bulk_src": "wa"}, with_items=False, clicks={"bulk_add"})
check("one click adds the reviewed tests", sorted(i["name"] for i in fake.session_state["items"]), ["Ferritin", "Thyroid Profile"])
check("…tagged as WhatsApp source", {i["source"] for i in fake.session_state["items"]}, {"whatsapp"})

fake, g, gh = invoice(state={"inquiry_ts": "2026-11-11T10:15:00", "referral_source": tr.WHATSAPP_SOURCE})
qid = fake.session_state["quote_id"]
html = [c[1] for c in fake.calls if c[0] == "components.html" and "wa.me" in str(c[1])]
check("send button is the one-tap bridge (wa.me + token)", (len(html), f'"sent:{qid}"' in html[0] if html else False), (1, True))
wa_msg = g["wa_msg"]
check("quote message: booking CTA + quote code + fasting prep",
      ("للحجز ردّ برقم" in wa_msg, qid in wa_msg, "صيام 9–12" in wa_msg), (True, True, True))
check("quote event carries the inquiry time", evs(gh, "quote")[0].get("meta"), {"inquiry_ts": "2026-11-11T10:15:00"})

fake, g, gh = invoice(state={"quote_id": "OR-261111-0042", "_logged_OR-261111-0042": True, "fu_hours": 3,
                             "inquiry_ts": "2026-11-11T10:15:00", "referral_source": tr.WHATSAPP_SOURCE},
                      typed={"wa_bridge_0": "sent:OR-261111-0042"}, secrets={"store_contacts": True})
sent = evs(gh, "sent")
check("one tap -> exactly one «sent» with follow-up scheduled", (len(sent), sent[0]["meta"]["followup_hours"] if sent else None,
                                                                bool(sent and sent[0]["meta"].get("next_due"))), (1, 3, True))
check("one tap: via + inquiry time + source + contact", (sent[0]["meta"]["via"], sent[0]["meta"]["inquiry_ts"],
                                                         sent[0]["referral_source"], sent[0]["contact"]["phone"]),
      ("one_tap", "2026-11-11T10:15:00", tr.WHATSAPP_SOURCE, E164))
check("bridge field cleared after use", fake.session_state["bridge_gen"], 1)
fake, g, gh = invoice(state={"quote_id": "OR-261111-0042", "_logged_OR-261111-0042": True,
                             "_sent_OR-261111-0042": "none"}, typed={"wa_bridge_0": "sent:OR-261111-0042"})
check("second tap on the same quote doesn't log again", evs(gh, "sent"), [])
fake, g, gh = invoice(state={"quote_id": "OR-261111-0042", "_logged_OR-261111-0042": True},
                      typed={"wa_bridge_0": "sent:OR-999999-0000"})
check("a token for another quote is ignored", evs(gh, "sent"), [])
fake, g, gh = invoice(state={"fu_hours": 0}, clicks={"btn_sent"})
s0 = evs(gh, "sent")
check("manual fallback button + «من غير متابعة»", (len(s0), s0[0]["meta"].get("followup_hours"), "next_due" in s0[0]["meta"]),
      (1, 0, False))
check("follow-up default comes from Policy", invoice(config={"policy": {"followup_hours": 6}})[0].session_state["fu_hours"], 6)

fake, g, gh = invoice(state={"_wa_last": {"intents": [{"intent": "price", "reply": "ask_prices", "keyword": "بكام"}],
                                          "text": "بكام؟", "has_media": False, "tests": 0}},
                      with_items=False, clicks={"wa_lead"}, secrets={"store_contacts": True})
ld = evs(gh, "lead")
check("lead button: logs a WhatsApp lead with a follow-up + contact",
      (len(ld), ld[0]["referral_source"] if ld else "", bool(ld and ld[0]["meta"].get("next_due")),
       (ld[0].get("contact") or {}).get("phone") if ld else ""), (1, tr.WHATSAPP_SOURCE, True, E164))

fake, g, gh = invoice(events=[tr.make_event("campaign", "OL-261108-QX12", phone_key=PK)])
check("campaign auto-attached when this phone got a Studio ad",
      (fake.session_state["campaign_id"], evs(gh, "quote")[0].get("campaign_id")), ("OL-261108-QX12", "OL-261108-QX12"))
fake, g, gh = invoice(state={"discount_type": "Percentage", "discount_value": 45.0, "disc_Percentage_0": 45.0},
                      secrets={"discount_approval_pin": "1234", "discount_limit_pct": 20})
check("45% discount sends without a PIN now (limit 50%)", ("الخصم محتاج موافقة المسؤول" in g["blockers"],
                                                           len(evs(gh, "quote"))), (False, 1))
fake, g, gh = invoice(state={"discount_type": "Percentage", "discount_value": 55.0, "disc_Percentage_0": 55.0},
                      secrets={"discount_approval_pin": "1234"})
check("55% still locked behind the PIN", "الخصم محتاج موافقة المسؤول" in g["blockers"], True)

# ============================================================
# 8) الصفحات
# ============================================================
def page(path, events=None, config=None, **kw):
    gh = fs.FakeGitHub()
    gs.requests = gh
    if events:
        gh.put_json(f"events/{tr.month_key()}.json", events)
    if config is not None:
        gh.put_json(cs.CONFIG_PATH, config)
    secrets = {**SEC, **kw.pop("secrets", {})}
    fake, g = fs.run_script(path, secrets=secrets, **kw)
    return fake, g, gh


# --- Marketing Studio: الاسم والرقم في الصفحة نفسها (مش الـ sidebar) + إرسال مباشر
src = open("pages/2_Marketing_Studio.py", encoding="utf-8").read()
tree = ast.parse(src)
side = [n for n in ast.walk(tree) if isinstance(n, ast.With)
        and any("sidebar" in ast.unparse(i.context_expr) for i in n.items)]
side_src = "\n".join(ast.unparse(n) for n in side)
check("studio: customer name/phone are NOT in the sidebar anymore",
      ("ms_cust_name" in side_src, "ms_cust_phone" in side_src), (False, False))
check("studio: …they're on the page itself", ("ms_cust_name" in src, "ms_cust_phone" in src), (True, True))
SS = "pages/2_Marketing_Studio.py"
SHORT = {"ms_branch_info": False, "ms_disc": False, "ms_template": "tip", "ms_headline": "نصيحة", "ms_body": "جملة قصيرة",
         "ms_photo_src": "none", "ms_cust_name": "Mona Ahmed", "ms_cust_phone": PHONE}
fake, g, gh = page(SS, state=dict(SHORT))
btn = [c[1] for c in fake.calls if c[0] == "components.html" and "wa.me" in str(c[1])]
check("studio: direct send to the customer by name", (len(btn), "إرسال لـ Mona" in btn[0] if btn else False,
                                                      f"wa.me/{E164}" in btn[0] if btn else False), (1, True, True))
check("studio: message starts with the customer's name", fake.session_state["ms_cap_txt"].startswith("أهلاً Mona"), True)
cid = fake.session_state["ms_cid"]
fake, g, gh = page(SS, state={**SHORT, "ms_cid": cid}, typed={"ms_bridge_0": f"camp:{cid}"})
ce = evs(gh, "campaign")
check("studio one tap: ad-to-customer logged with the phone key",
      (len(ce), ce[0].get("pk") if ce else "", (ce[0].get("meta") or {}).get("to_customer") if ce else None), (1, PK, True))

# --- Check-in
CI = [tr.make_event("quote", "OR-261111-0042", total=800, items=["CBC", "Lipid Profile"], phone_key=PK,
                    referral_source=tr.WHATSAPP_SOURCE),
      tr.make_event("sent", "OR-261111-0042", total=800, phone_key=PK)]
fake, g, gh = page("pages/9_Check_In.py", CI, typed={"ci_q": PHONE})
check("check-in: phone finds the open quote", any("OR-261111-0042" in str(c) for c in fake.calls if c[0] == "caption")
      or any(k.startswith("s_paid_OR-261111-0042") for k in fake.session_state), True)
fake, g, gh = page("pages/9_Check_In.py", CI, typed={"ci_q": "or-261111-0042", "s_paid_OR-261111-0042": 950},
                   clicks={"s_in_OR-261111-0042"})
cv = evs(gh, "converted")
check("check-in: «حضر» logs the visit with the actual paid amount",
      (len(cv), cv[0]["total"] if cv else 0, (cv[0].get("meta") or {}).get("via") if cv else ""), (1, 950, "checkin"))
check("…and the quote is now «visited»", tr.stage_of(tr.quote_records(gh.events())["OR-261111-0042"]), "visited")
fake, g, gh = page("pages/9_Check_In.py", CI + [tr.make_event("booked", "OR-261111-0042",
                                                             meta={"appointment": f"{date.today()}T18:00:00"},
                                                             contact={"name": "Mona", "phone": E164})])
check("check-in: today's appointment + reminder link", any("تذكير" in c[1] for c in fake.calls if c[0] == "link"), True)

# --- Replies
fake, g, gh = page("pages/8_Replies.py", [], typed={"rp_msg": "الأسعار عندكم غالية جداً"})
check("replies: pasted message auto-picks the price-objection reply", fake.session_state["rp_reply"], "price_high")
fake, g, gh = page("pages/8_Replies.py", [], state={"_rp_prefill": {"rp_name": "Mona", "rp_phone": PHONE,
                                                                     "rp_reply": "home_visit", "rp_msg": "عايزة سحب منزلي"}})
check("replies: hand-off from the invoice (name/phone/reply)", (fake.session_state["rp_name"],
                                                                fake.session_state["rp_reply"]), ("Mona", "home_visit"))
fake, g, gh = page("pages/8_Replies.py", [], state={"rp_phone": PHONE, "rp_reply": "ask_prices"},
                   typed={"rp_outcome": "followup"}, clicks={"rp_log"}, secrets={"store_contacts": True})
check("replies: follow-up with no quote -> registered as a lead", ([e["type"] for e in gh.events()],
                                                                  bool(evs(gh, "lead") and evs(gh, "lead")[0]["meta"]["next_due"])),
      (["lead", "reply"], True))
QR = [tr.make_event("quote", "OR-1", total=1100, items=["Lipid Profile", "CBC"], phone_key=PK, discount=100)]
fake, g, gh = page("pages/8_Replies.py", QR, state={"rp_phone": PHONE, "rp_reply": "price_quote"})
txt = [v for k, v in fake.session_state.items() if str(k).startswith("rp_txt_price_quote")]
check("replies: quote reply filled from the logged quote (total + code + prep)",
      bool(txt) and all(x in txt[0] for x in ("1,100", "OR-1", "صيام")), True)

# --- Follow-up / Customers / Dashboard / Branches
FU = L + [tr.make_event("quote", "Q11", total=300), tr.make_event("booked", "Q11",
          meta={"appointment": (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds")},
          contact={"name": "Mona", "phone": E164})]
fake, g, gh = page("pages/3_Follow_Up.py", FU)
check("follow-up page: lead card + appointment reminder, no errors",
      (fake.messages("error"), any("تذكير بالميعاد" in c[1] for c in fake.calls if c[0] == "link")), ([], True))
fake, g, gh = page("pages/5_Customers.py", R)
check("customers page: recall tab lists the due customer", any("Hany" in str(c) for c in fake.calls), True)
fake, g, gh = page("pages/1_Dashboard.py", F)
check("dashboard: WhatsApp funnel computed", (g["wf"]["quotes"], g["wf"]["visited"]), (2, 1))
fake, g, gh = page("pages/6_Branches.py", [], typed={"br_who": "Hussein", "pol_limit": 40}, clicks={"pol_save"})
stored = gh.files.get(cs.CONFIG_PATH)
import json as _j
check("branches → Policy: admin saves a new limit (audited)",
      (_j.loads(stored["content"])["policy"]["discount_limit_pct"] if stored else None,
       [e["type"] for e in gh.events()]), (40.0, ["config_change"]))

print("\n" + "=" * 78)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
