#!/usr/bin/env python3
"""
اختبار Smart Replies (الردود الجاهزة) + متابعة «هفكر وأرد» من غير تكرار + تحليل الاعتراضات +
Setup check + لينكات التطبيق + فحص الريبو.
    python3 test_replies.py
"""
import re
import sys
from datetime import datetime, timedelta
from urllib.parse import unquote

import config_store as cs
import fake_streamlit as fs
import github_store as gs
import offers_catalog as OC
import replies as RP
import setup_check as sc
import tracking as tr
from price_utils import validate_phone

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:70} got={got}")
    if not ok:
        fails.append((label, got, want))


NOW = datetime.now()


def ev(typ, qid, hours_ago, **kw):
    return tr.make_event(typ, qid, now=NOW - timedelta(hours=hours_ago), **kw)


# ------------------------------------------------------------
# 1) كتالوج الردود
# ------------------------------------------------------------
ids = [r["id"] for r in RP.REPLIES]
check("21 replies, unique ids", (len(ids), len(set(ids))), (21, 21))
check("4 groups, each used", {r["group"] for r in RP.REPLIES}, set(RP.GROUPS))
check("the objections from the plan exist",
      {"price_high", "cheaper_elsewhere", "ask_discount", "ask_prices", "will_think"} <= set(ids), True)
check("every reply has a short and a long version (short < long)",
      [r["id"] for r in RP.REPLIES if not (r["short"].strip() and r["long"].strip() and len(r["short"]) < len(r["long"]))], [])
used = {v for r in RP.REPLIES for v in re.findall(r"\{(\w+)\}", r["short"] + r["long"])}
check("templates only use known placeholders", used <= RP.VARS, True)
check("objection keys are labelled", [r["id"] for r in RP.REPLIES if r["kind"] == "objection" and r["objection"]
                                      and r["objection"] not in RP.OBJECTION_LABELS], [])
check("loss reasons mapped to real reasons", [r["id"] for r in RP.REPLIES if r["reason"] and r["reason"] not in tr.LOST_SALE_REASONS], [])
check("the four loss categories exist (price / competitor / no reply / postponed)",
      {"السعر", "معمل تاني", "مش بيرد", "تأجيل لوقتا تاني".replace("لوقتا", "لوقت")} <= set(tr.LOST_SALE_REASONS), True)
check("«هفكر وأرد» schedules a 24h follow-up by default", (RP.get("will_think")["followup_hours"], RP.get("will_think")["objection"]), (24, "postpone"))
check("price objection reply says so", ("price" == RP.get("price_high")["objection"], "غالية" in RP.get("price_high")["title"]), (True, True))
check("group index covers all replies", sum(len(v) for v in RP.by_group().values()), len(RP.REPLIES))

# ------------------------------------------------------------
# 2) بناء الرد
# ------------------------------------------------------------
tpl = RP.get("price_high")
t = RP.render_reply(tpl, "short", name="Mona Ahmed", lab="معمل أورانج لاب")
check("name personalises the greeting (first name)", t.startswith("أهلاً Mona 🍊"), True)
check("no name -> generic greeting", RP.render_reply(tpl, "short").startswith("أهلاً بحضرتك 🍊"), True)
check("arabic name works too", RP.render_reply(tpl, "short", name="منى أحمد").startswith("أهلاً منى 🍊"), True)
check("optional blocks vanish when empty (no braces left)", "{" not in t and "العروض المتاحة" not in t, True)
lines = RP.offer_lines([OC.get("4")], [{"name": "CBC week", "promo_price": 300, "original_price": 400}])
check("offer lines: catalog offer + promotion", lines, "• عرض أورانج 1: 3,750 ج بدل 4,710 ج\n• CBC week: 300 ج بدل 400 ج")
t = RP.render_reply(tpl, "long", name="Mona", offers_text=lines, fhv_text="🎁 زيارة مجانية", branch_text="📍 فرع دياموند")
check("long reply carries offers + free visit + branch, in order",
      t.index("العروض المتاحة") < t.index("زيارة مجانية") < t.index("فرع دياموند"), True)
check("short is shorter than long for every reply with all options",
      all(len(RP.render_reply(r, "short", offers_text="• x", fhv_text="f", branch_text="b")) <
          len(RP.render_reply(r, "long", offers_text="• x", fhv_text="f", branch_text="b")) for r in RP.REPLIES), True)
check("no placeholder survives in any reply/version",
      [(r["id"], v) for r in RP.REPLIES for v in ("short", "long")
       if re.search(r"\{\w+\}", RP.render_reply(r, v, name="a", offers_text="o", fhv_text="f", branch_text="b", review_url="u"))], [])
check("no triple blank lines", all("\n\n\n" not in RP.render_reply(r, "long", branch_text="b") for r in RP.REPLIES), True)
check("review link only when configured", ("https://g.page/r" in RP.render_reply(RP.get("thanks"), "short", review_url="https://g.page/r"),
                                           "قيّمنا" in RP.render_reply(RP.get("thanks"), "short")), (True, False))
check("branch_info reply is just the branch block",
      "📍 فرع" in RP.render_reply(RP.get("branch_info"), "short", branch_text="📍 فرع دياموند: x"), True)
check("honest wording: no invented prices/promises in replies",
      [r["id"] for r in RP.REPLIES if re.search(r"\d{3,}", r["short"] + r["long"])], [])

# ------------------------------------------------------------
# 3) منع تكرار المتابعة
# ------------------------------------------------------------
def rec_of(events, qid):
    return tr.quote_records(events)[qid]


base = [ev("quote", "Q1", 30, total=900, phone_key="pkA"), ev("sent", "Q1", 29)]
check("fresh sent quote can be followed up", tr.can_schedule_followup(rec_of(base, "Q1"), NOW), (True, ""))
sched = base + [ev("followup", "Q1", 2, meta={"next_due": (NOW + timedelta(hours=22)).isoformat()})]
ok, why = tr.can_schedule_followup(rec_of(sched, "Q1"), NOW)
check("already scheduled -> refused", (ok, "مجدولة" in why), (False, True))
recent = base + [ev("followup", "Q1", 5, meta={"next_due": (NOW - timedelta(hours=1)).isoformat()})]
ok, why = tr.can_schedule_followup(rec_of(recent, "Q1"), NOW)
check("followed up <12h ago -> refused", (ok, "12" in why), (False, True))
old_fu = base + [ev("followup", "Q1", 20, meta={"next_due": (NOW - timedelta(hours=1)).isoformat()})]
check("followed up 20h ago and due -> allowed", tr.can_schedule_followup(rec_of(old_fu, "Q1"), NOW)[0], True)
three = base + [ev("followup", "Q1", h, meta={"next_due": (NOW - timedelta(hours=1)).isoformat()}) for h in (60, 40, 20)]
check("3 attempts -> refused", tr.can_schedule_followup(rec_of(three, "Q1"), NOW)[1].startswith("خلّصت"), True)
check("visited/lost quote -> refused", [tr.can_schedule_followup(rec_of(base + [ev(t_, "Q1", 3, total=900)], "Q1"), NOW)[0]
                                        for t_ in ("converted", "lost_sale")], [False, False])
check("opted-out phone -> refused", tr.can_schedule_followup(rec_of(base, "Q1"), NOW, opted={"pkA"})[1], "العميل طلب إيقاف الرسائل")
check("custom gap respected", tr.can_schedule_followup(rec_of(recent, "Q1"), NOW, min_gap_hours=2)[0], True)

# ------------------------------------------------------------
# 4) تحليل الاعتراضات
# ------------------------------------------------------------
def rp(qid, h, obj, kind="objection"):
    return ev("reply", qid, h, meta={"objection": obj, "kind": kind, "reply": "x", "version": "short"})


E = [ev("quote", "P1", 90, total=1000), ev("sent", "P1", 89), ev("lost_sale", "P1", 50, reason="السعر", total=1000),
     ev("quote", "P2", 90, total=1200), ev("sent", "P2", 89), ev("converted", "P2", 20, total=1200),
     ev("quote", "P3", 90, total=700), ev("sent", "P3", 89),
     rp("P1", 80, "price"), rp("P2", 80, "price"), rp("P2", 70, "price"), rp("P3", 80, "postpone"),
     rp("P1", 60, "", kind="booking"), ev("reply", "", 5, meta={"objection": "price", "kind": "objection"})]
st_ = tr.objection_stats(E)
check("objections counted (not booking/service replies)", (st_["price"]["count"], st_["postpone"]["count"]), (4, 1))
check("outcomes of the quotes that had the objection", (st_["price"]["quotes"], st_["price"]["visited"], st_["price"]["lost"], st_["price"]["open"]), (2, 1, 1, 0))
check("visit rate per objection + top loss reason", (st_["price"]["visit_rate_pct"], st_["price"]["top_reasons"]), (50.0, [("السعر", 1)]))
check("open quote with 'postpone'", (st_["postpone"]["open"], st_["postpone"]["visit_rate_pct"]), (1, 0.0))
check("reply events never break the other KPIs", (tr.summarize_events(E)["quotes"], tr.marketing_kpis(E)["sent"]), (3, 3))
check("no replies -> empty stats", tr.objection_stats([]), {})

# ------------------------------------------------------------
# 5) Setup check + اللينكات
# ------------------------------------------------------------
cfg = cs.default_config()
cfg["branches"]["Diamond"]["phone"] = "+20 100 000 0001"
cfg["branches"]["Orange (La Cité)"]["phone"] = "+20 100 000 0002"
good_secrets = {"gh_events_token": "t", "gh_events_repo": "u/r", "quote_secret": "x" * 32, "access_password": "a",
                "staff_password": "s", "store_contacts": "true", "discount_approval_pin": "1234"}
good_links = {"app_url": "https://orange.streamlit.app", "review_url": "https://g.page/r/abc", "facebook_page_url": "https://facebook.com/orange"}
ok_repo = {"ok": True, "private": True, "default_branch": "main", "error": ""}
checks = sc.run_checks(good_secrets, cfg, good_links, ok_repo, default_phone="+20 100 000 0001", offers_phone="01000000001")
check("a fully configured setup has no failures/warnings", sc.summary(checks)["fail"] + sc.summary(checks)["warn"], 0)
fail_titles = lambda ch: [c["title"] for c in ch if c["status"] == "fail"]
warn_titles = lambda ch: [c["title"] for c in ch if c["status"] == "warn"]
c = sc.run_checks(good_secrets, cfg, {**good_links, "app_url": "https://REPLACE-WITH-YOUR-STREAMLIT-APP-URL"}, ok_repo)
check("placeholder app url is a failure", any("app_url" in t_ for t_ in fail_titles(c)), True)
c = sc.run_checks(good_secrets, cfg, {**good_links, "app_url": ""}, ok_repo)
check("empty app url is a failure", any("app_url" in t_ for t_ in fail_titles(c)), True)
c = sc.run_checks(good_secrets, cfg, good_links, {**ok_repo, "private": False})
check("PUBLIC events repo is a failure", any("Public" in t_ for t_ in fail_titles(c)), True)
c = sc.run_checks(good_secrets, cfg, good_links, {"ok": False, "private": None, "error": "GitHub (404)"})
check("unreachable repo is a failure", any("مش متاح" in t_ for t_ in fail_titles(c)), True)
c = sc.run_checks({}, cfg, good_links, None)
check("no secrets: tracking + quote_secret fail, passwords warn", (any("GitHub" in t_ for t_ in fail_titles(c)),
      any("quote_secret" in t_ for t_ in fail_titles(c)), any("access_password" in t_ for t_ in warn_titles(c))), (True, True, True))
c = sc.run_checks({**good_secrets, "quote_secret": "short"}, cfg, good_links, ok_repo)
check("short quote_secret is a warning", any("quote_secret قصير" in t_ for t_ in warn_titles(c)), True)
same = cs.default_config()
c = sc.run_checks(good_secrets, same, good_links, ok_repo)
check("both branches on the same phone -> warning", any("نفس الرقم" in t_ for t_ in warn_titles(c)), True)
bad_phone = cs.default_config()
bad_phone["branches"]["Diamond"]["phone"] = "123"
check("invalid branch phone is a failure", any("Diamond" in t_ or "دياموند" in t_ for t_ in fail_titles(sc.run_checks(good_secrets, bad_phone, good_links, ok_repo))), True)
c = sc.run_checks(good_secrets, cfg, good_links, ok_repo, default_phone="+20 109 790 2820", offers_phone="01032847185")
check("two different phone numbers in the program -> warning", any("رقمين مختلفين" in t_ for t_ in warn_titles(c)), True)
c = sc.run_checks(good_secrets, cfg, {**good_links, "review_url": "", "facebook_page_url": ""}, ok_repo)
check("missing review/facebook links -> warnings", len([t_ for t_ in warn_titles(c) if "فاضي" in t_]), 2)
c = sc.run_checks({**good_secrets, "discount_approval_pin": ""}, cfg, good_links, ok_repo)
check("discount limit without PIN -> warning", any("من غير كود موافقة" in t_ for t_ in warn_titles(c)), True)
c = sc.run_checks({**good_secrets, "store_contacts": "false"}, cfg, good_links, ok_repo)
check("store_contacts off -> explained warning", any("store_contacts مقفول" in t_ for t_ in warn_titles(c)), True)

check("links: config wins, then secrets, then empty",
      (cs.resolve_links({"links": {"app_url": "https://a.app/", "review_url": ""}}, {"review_url": "https://r", "app_url": "https://s"}),
       cs.resolve_links(cs.default_config(), {"app_url": "https://s.app"})["app_url"],
       cs.resolve_links(cs.default_config(), {})["app_url"]),
      ({"app_url": "https://a.app", "review_url": "https://r", "facebook_page_url": ""}, "https://s.app", ""))
check("valid_url", [cs.valid_url(u) for u in ("https://a.b/c", "http://a.b", "a.b", "", "https://x")], [True, False, False, False, False])

gh = fs.FakeGitHub()
gs.requests = gh
store = gs.GithubEventStore("t", "u/r")
check("repo_info: private repo", store.repo_info(), {"ok": True, "private": True, "default_branch": "main", "error": ""})
gh.repo_private = False
check("repo_info: public repo detected", store.repo_info()["private"], False)
gh.repo_status = 404
ri = store.repo_info()
check("repo_info: 404 -> not ok with a hint", (ri["ok"], "الريبو" in ri["error"]), (False, True))
gh.repo_status, gh.repo_private = 200, True

# ------------------------------------------------------------
# 6) صفحة الردود (Streamlit وهمي)
# ------------------------------------------------------------
SECRET, PHONE = "abc", "01012345678"
PK = tr.phone_key(validate_phone(PHONE).value, SECRET)
SEC = {"gh_events_token": "t", "gh_events_repo": "u/r", "quote_secret": SECRET}
RPG = "pages/8_Replies.py"


def page(path, events=None, config=None, secrets=None, **kw):
    g_ = fs.FakeGitHub()
    gs.requests = g_
    if events:
        g_.put_json(f"events/{tr.month_key()}.json", events)
    if config is not None:
        g_.put_json(cs.CONFIG_PATH, config)
    fake, g = fs.run_script(path, secrets={**SEC, **(secrets or {})}, **kw)
    return fake, g, g_


def wa(fake):
    return [unquote(c[2]) for c in fake.calls if c[0] == "link" and "wa.me" in c[2]]


def evs(gh_, typ):
    return [e for e in gh_.events() if e["type"] == typ]


sent = [ev("quote", "F1", 31, branch="Diamond", total=1800, phone_key=PK, items=["CBC"],
           contact={"name": "Mona Ahmed", "phone": "201012345678"}), ev("sent", "F1", 30, branch="Diamond", phone_key=PK)]
fake, g, gh = page(RPG)
check("replies page renders; all replies offered", fake.options["rp_reply"], ids)
fake, g, gh = page(RPG, typed={"rp_name": "Mona Ahmed", "rp_phone": PHONE, "rp_reply": "price_high"})
check("reply goes to the customer's number, with their name",
      (any(l.startswith("https://wa.me/201012345678?text=") and "أهلاً Mona" in l for l in wa(fake))), True)
fake, g, gh = page(RPG, typed={"rp_reply": "price_high", "rp_version": "long", "rp_offers": ["4"]})
check("long version + chosen catalog offer appear in the reply",
      any("الإجمالي" in str(c) or "عرض أورانج 1: 3,750" in str(c) for c in fake.calls if c[0] == "code"), True)
fake, g, gh = page(RPG, typed={"rp_reply": "branch_info", "rp_branch": "Diamond"})
check("branch info reply carries the selected branch (map + address)",
      any("zvE73ScU1ykTE7vNA" in str(c) and "امام دياموند" in str(c) for c in fake.calls if c[0] == "code"), True)
fake, g, gh = page(RPG, typed={"rp_reply": "branch_info", "rp_branch": "Orange (La Cité)"})
check("switching branch switches the block", any("XR1kcfeN1XJ36i3J7" in str(c) and "zvE73" not in str(c) for c in fake.calls if c[0] == "code"), True)

LOG = {"rp_reply": "will_think", "rp_quote": "F1", "rp_phone": PHONE, "rp_name": "Mona"}
fake, g, gh = page(RPG, sent, typed=LOG, clicks={"rp_log"}, state={"staff_name": "Mona"})
r_, f_ = evs(gh, "reply"), evs(gh, "followup")
check("«هفكر وأرد»: reply logged with objection + staff + phone key",
      (len(r_), r_[0]["meta"]["objection"], r_[0]["meta"]["reply"], r_[0].get("staff"), r_[0].get("pk"), r_[0]["quote_id"]),
      (1, "postpone", "will_think", "Mona", PK, "F1"))
nd = datetime.fromisoformat(f_[0]["meta"]["next_due"]) if f_ else None
check("…and a follow-up is scheduled ~24h ahead (via reply)", (len(f_), nd is not None and 23.5 < (nd - NOW).total_seconds() / 3600 < 24.5,
                                                                f_[0]["meta"]["via"] if f_ else None), (1, True, "reply"))
dup = sent + [ev("followup", "F1", 2, meta={"next_due": (NOW + timedelta(hours=22)).isoformat()})]
fake, g, gh = page(RPG, dup, typed=LOG, clicks={"rp_log"})
check("second «هفكر وأرد» within hours: reply logged, NO duplicate follow-up",
      (len(evs(gh, "reply")), len(evs(gh, "followup"))), (1, 1))
fake, g, gh = page(RPG, sent, typed={**LOG, "rp_outcome": "lost", "rp_reason": "السعر", "rp_reply": "price_high"}, clicks={"rp_log"})
check("price objection + «فات»: lost sale logged with the reason and total",
      [(e["reason"], e["total"], e["quote_id"]) for e in evs(gh, "lost_sale")], [("السعر", 1800, "F1")])
fake, g, gh = page(RPG, sent, typed={**LOG, "rp_outcome": "none"}, clicks={"rp_log"})
check("«سجّل الرد بس»: only the reply event", ([e["type"] for e in gh.events() if e["type"] in ("reply", "followup", "lost_sale")]), ["reply"])
fake, g, gh = page(RPG, sent, typed={"rp_reply": "will_think", "rp_outcome": "followup"}, clicks={"rp_log"})
check("follow-up without choosing a quote -> refused with a message",
      (len(gh.events()), any("اختار العرض" in m for m in fake.messages("error"))), (len(evs(gh, "quote")) + len(evs(gh, "sent")), True))
fake, g, gh = page(RPG, sent, typed={"rp_reply": "branch_info", "rp_phone": PHONE}, clicks={"rp_log"})
check("booking/service replies never become objections", [e["meta"]["kind"] for e in evs(gh, "reply")], ["booking"])
optev = sent + [ev("optout", "F1", 3, phone_key=PK)]
fake, g, gh = page(RPG, optev, typed={"rp_phone": PHONE, "rp_reply": "price_high"})
check("opted-out customer: warning and no WhatsApp button", (any("طلب إيقاف" in m for m in fake.messages("warning")), wa(fake)), (True, []))
fake, g, gh = page(RPG, sent, typed={"rp_phone": PHONE, "rp_reply": "stop_messages"}, clicks={"rp_optout"})
check("«إيقاف الرسائل» reply can register the opt-out", [e["pk"] for e in evs(gh, "optout")], [PK])
fake, g, gh = page(RPG, secrets={"gh_events_token": "", "gh_events_repo": ""}, typed={"rp_reply": "price_high"})
check("without tracking: the reply still works, logging explained",
      (any(c[0] == "link" for c in fake.calls), any("التسجيل محتاج" in str(c) for c in fake.calls if c[0] == "info")), (True, True))
fake, g, gh = page(RPG, secrets={"access_password": "adm", "staff_password": "stf"}, typed={"_access_pw": "stf"})
check("replies page opens with the STAFF password", any(c[0] == "link" or c[0] == "code" for c in fake.calls), True)
fake, g, gh = page(RPG, secrets={"access_password": "adm", "staff_password": "stf"})
check("replies page is locked without a password", any(c[0] == "code" for c in fake.calls), False)

# ------------------------------------------------------------
# 7) الداشبورد + الفروع (Links + Setup) + الفاتورة بلينك التطبيق
# ------------------------------------------------------------
fake, g, gh = page("pages/1_Dashboard.py", E)
frames = [c[1][0] for c in fake.calls if c[0] == "dataframe" and c[1] and hasattr(c[1][0], "columns")]
obj_frames = [f for f in frames if "الاعتراض" in list(f.columns)]
check("dashboard shows the objection analysis", (len(obj_frames), obj_frames[0].iloc[0]["الاعتراض"] if obj_frames else None, int(obj_frames[0].iloc[0]["اتقال كام مرة"]) if obj_frames else None), (1, "السعر غالي", 4))

fake, g, gh = page("pages/6_Branches.py", clicks={"lk_save"}, typed={"br_who": "Hussein", "lk_app": "https://orange.streamlit.app/",
                                                                       "lk_review": "https://g.page/r/abc"})
links = cs.effective(__import__("json").loads(gh.files[cs.CONFIG_PATH]["content"]))["links"]
check("Links tab saves the links (trailing slash trimmed)", (links["app_url"], links["review_url"]), ("https://orange.streamlit.app", "https://g.page/r/abc"))
fake, g, gh = page("pages/6_Branches.py", clicks={"lk_save"}, typed={"br_who": "H", "lk_app": "not-a-url"})
check("invalid link refused", (cs.CONFIG_PATH in gh.files, any("لينك مش صحيح" in m for m in fake.messages("error"))), (False, True))
fake, g, gh = page("pages/6_Branches.py", clicks={"lk_save"}, typed={"br_who": "", "lk_app": "https://a.app"})
check("link edit needs the editor's name", cs.CONFIG_PATH in gh.files, False)
fake, g, gh = page("pages/6_Branches.py")
mets = {c[1][0]: None for c in fake.calls if c[0] == "metric"}
check("Setup check tab renders its summary", {"✅ تمام", "⚠️ مراجعة", "❌ لازم تتصلّح"} <= set(mets), True)
gh2 = fs.FakeGitHub()
gh2.repo_private = False
gs.requests = gh2
fake, g = fs.run_script("pages/6_Branches.py", secrets=SEC)
check("Setup check flags a public repo", any("Public" in str(c) for c in fake.calls if c[0] == "write"), True)

ITEMS = [{"uid": "a1", "name": "CBC", "price": 400, "result_days": 1, "collection_notes": "EDTA", "category": "HEMATOLOGY", "source": "manual"}]
fake, g, gh = page("Invoice.py", state={"items": [dict(i) for i in ITEMS], "p_name": "Ahmed Ali Hassan", "p_phone": PHONE}, clicks={"💾 احفظ العرض"})
check("without a configured app url the saved link has the placeholder + warning",
      (fake.session_state["saved_link"].startswith("https://REPLACE"), any("لسه محطوطش" in m for m in fake.messages("warning"))), (True, True))
fake, g, gh = page("Invoice.py", state={"items": [dict(i) for i in ITEMS], "p_name": "Ahmed Ali Hassan", "p_phone": PHONE}, clicks={"💾 احفظ العرض"},
                   config={"links": {"app_url": "https://orange.streamlit.app/"}})
check("app url from the Links tab is used in saved quote links",
      (fake.session_state["saved_link"].startswith("https://orange.streamlit.app/?q="), any("لسه محطوطش" in m for m in fake.messages("warning"))), (True, False))
fake, g, gh = page("Invoice.py", state={"items": [dict(i) for i in ITEMS], "p_name": "Ahmed Ali Hassan", "p_phone": PHONE}, clicks={"💾 احفظ العرض"},
                   secrets={"app_url": "https://from-secrets.streamlit.app"})
check("app_url secret works as a fallback", fake.session_state["saved_link"].startswith("https://from-secrets.streamlit.app/?q="), True)

# ------------------------------------------------------------
# 8) توقيت القاهرة
# ------------------------------------------------------------
import os
import time as _time
import tzsetup

if os.path.exists("/usr/share/zoneinfo/Africa/Cairo"):
    from datetime import timezone
    off = (datetime.now() - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() / 3600
    check("process timezone is Cairo (UTC+2/+3) — not UTC", round(off) in (2, 3), True)
    check("tz names are Eastern European", _time.tzname[0] in ("EET", "EEST", "+02", "+03") or "EE" in _time.tzname[0], True)
else:
    print("INFO  tzdata not installed here — Cairo timezone check skipped")
check("importing tracking applies the Cairo timezone", os.environ.get("TZ"), "Africa/Cairo")
check("APP_TIMEZONE can override it", (tzsetup.apply("UTC"), os.environ.get("TZ")), (hasattr(_time, "tzset"), "UTC"))
tzsetup.apply("Africa/Cairo")

print("\n" + "=" * 80)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
