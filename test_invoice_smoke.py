#!/usr/bin/env python3
"""
تشغيل Invoice.py والصفحات الجديدة كاملة على Streamlit وهمي + GitHub وهمي
(fake_streamlit.py) — بيتأكد إن الأحداث والبوابات والأزرار المنطقية شغّالة:
    python3 test_invoice_smoke.py
ده مش بديل عن تجربة الشاشة الحقيقية على Streamlit، بس بيمسك الأخطاء المنطقية.
"""
import sys
from datetime import date, datetime, timedelta

import fake_streamlit as fs
import github_store as gs
import promotions as pr
from price_utils import encode_quote, validate_phone
from tracking import make_event, month_key, phone_key

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:66} got={got}")
    if not ok:
        fails.append((label, got, want))


SECRET = "abc"
PHONE = "01012345678"
PK = phone_key(validate_phone(PHONE).value, SECRET)
ITEMS = [{"uid": "a1", "name": "CBC", "price": 400, "result_days": 1,
          "collection_notes": "EDTA", "category": "HEMATOLOGY", "source": "manual"},
         {"uid": "a2", "name": "Ferritin", "price": 400, "result_days": 1,
          "collection_notes": "serum", "category": "Iron Profile", "source": "manual"}]
SEC = {"gh_events_token": "t", "gh_events_repo": "u/r", "quote_secret": SECRET}


def invoice(state=None, secrets=None, clicks=(), typed=None, query=None, gh=None, events=None, promos=None):
    gh = gh or fs.FakeGitHub()
    gs.requests = gh
    if events:
        gh.put_json(f"events/{month_key()}.json", events)
    if promos is not None:
        gh.put_json(pr.PROMO_PATH, promos)
    st_ = {"items": [dict(i) for i in ITEMS], "p_name": "Ahmed Ali Hassan", "p_phone": PHONE}
    st_.update(state or {})
    fake, g = fs.run_script("Invoice.py", state=st_, secrets={**SEC, **(secrets or {})},
                            clicks=clicks, typed=typed, query=query)
    return fake, g, gh


def types(gh):
    return [e["type"] for e in gh.events()]


# ------------------------------------------------------------
# 1) الأساس: quote event بحملة وبصمة وخصم
# ------------------------------------------------------------
fake, g, gh = invoice(state={"campaign_id": "OL-261105-AB12", "discount_value": 100.0,
                             "discount_type": "Fixed Amount", "disc_gen": 0,
                             "disc_Fixed Amount_0": 100.0})
q = [e for e in gh.events() if e["type"] == "quote"][0]
check("no errors on filled invoice", fake.messages("error"), [])
check("quote event logged once", types(gh), ["quote"])
check("quote carries campaign id", q.get("campaign_id"), "OL-261105-AB12")
check("quote carries phone key (not the number)", (q.get("pk"), PHONE in str(q)), (PK, False))
check("quote carries discount + net total", (q.get("discount"), q["total"]), (100, 700))

fake, g, gh = invoice(state={"campaign_id": "garbage"})
q = [e for e in gh.events() if e["type"] == "quote"][0]
check("invalid campaign code not recorded", "campaign_id" in q, False)

fake, g, gh = invoice(secrets={"quote_secret": ""})
q = [e for e in gh.events() if e["type"] == "quote"][0]
check("no secret -> no phone key stored (can't hash safely)", "pk" in q, False)

# ------------------------------------------------------------
# 2) زرار «تم الإرسال»
# ------------------------------------------------------------
fake, g, gh = invoice(clicks={"btn_sent"})
sent = [e for e in gh.events() if e["type"] == "sent"]
check("sent button logs exactly one sent event", types(gh), ["quote", "sent"])
check("sent: carries pk + totals + items", (sent[0].get("pk"), sent[0]["total"], sent[0]["items"]),
      (PK, 800, ["CBC", "Ferritin"]))
check("sent: contact NOT stored by default", "contact" in sent[0], False)
check("sent: flash success shown", any("اتبعت" in m for m in fake.messages("success")), True)

fake, g, gh = invoice(clicks={"btn_sent"}, secrets={"store_contacts": True})
sent = [e for e in gh.events() if e["type"] == "sent"][0]
check("sent: contact stored only when store_contacts=true",
      sent.get("contact"), {"name": "Ahmed Ali Hassan", "phone": validate_phone(PHONE).value})

fake, g, gh = invoice(clicks={"btn_sent"}, secrets={"gh_events_token": "", "gh_events_repo": ""})
check("sent without tracking configured: warning, no crash",
      (types(gh), any("مش متظبط" in m for m in fake.messages("warning"))), ([], True))

fake, g, gh = invoice(clicks={"btn_sent"}, state={"p_phone": "123"})
check("sent button hidden when phone invalid", types(gh), [])

# ------------------------------------------------------------
# 3) موافقة الخصم
# ------------------------------------------------------------
disc30 = {"discount_type": "Percentage", "discount_value": 30.0, "disc_Percentage_0": 30.0}
pol = {"discount_limit_pct": 20, "discount_approval_pin": "1234"}
fake, g, gh = invoice(state=disc30, secrets=pol)
check("30% > limit: blocked, no quote logged", (types(gh), "الخصم محتاج موافقة المسؤول" in g["blockers"]),
      ([], True))
fake, g, gh = invoice(state=disc30, secrets=pol, typed={"disc_pin": "9999"})
check("wrong PIN: still blocked + error", (types(gh), any("غلط" in m for m in fake.messages("error"))),
      ([], True))
fake, g, gh = invoice(state=disc30, secrets=pol, typed={"disc_pin": "1234"})
q = [e for e in gh.events() if e["type"] == "quote"]
check("right PIN: unblocked, quote logged with approval", (len(q), q[0]["meta"] if q else None),
      (1, {"approved": True}))
fake, g, gh = invoice(state={**disc30, "discount_value": 15.0, "disc_Percentage_0": 15.0}, secrets=pol)
check("15% under limit: no approval needed", (types(gh), g["blockers"]), (["quote"], []))
fake, g, gh = invoice(state=disc30, secrets={"discount_limit_pct": 20})
check("limit without PIN configured: warns, doesn't block", (types(gh), any(
    "discount_approval_pin" in m for m in fake.messages("warning"))), (["quote"], True))
fake, g, gh = invoice(state=disc30)
check("no policy configured: no restriction", types(gh), ["quote"])

# ------------------------------------------------------------
# 4) اللينك المحفوظ: تشفير + انتهاء + حملة
# ------------------------------------------------------------
now = datetime.now()
payload = {"id": "OR-261105-0001", "ts": now.isoformat(timespec="seconds"),
           "items": [{"n": "CBC", "p": 400, "d": 1, "c": "EDTA", "cat": "HEMATOLOGY"}],
           "name": "Mona Ahmed Samy", "phone": PHONE, "doctor": "", "date_iso": date.today().isoformat(),
           "dtype": "Percentage", "dval": 0.0, "cid": "OL-261105-AB12"}
tok = encode_quote(payload, SECRET)
fake, g, gh = invoice(state={"items": [], "p_name": "", "p_phone": ""}, query={"q": tok})
check("fresh link restores items/name/campaign",
      ([i["name"] for i in fake.session_state["items"]], fake.session_state["p_name"],
       fake.session_state["campaign_id"]), (["CBC"], "Mona Ahmed Samy", "OL-261105-AB12"))
check("restored quote keeps its id", fake.session_state["quote_id"], "OR-261105-0001")

old_tok = encode_quote({**payload, "ts": (now - timedelta(hours=49)).isoformat(timespec="seconds")}, SECRET)
fake, g, gh = invoice(state={"items": [], "p_name": "", "p_phone": ""}, query={"q": old_tok})
check("49h link refused with clear message", (fake.session_state["items"], any(
    "انتهت صلاحيته" in m for m in fake.messages("error"))), ([], True))
fake, g, gh = invoice(state={"items": [], "p_name": "", "p_phone": ""}, query={"q": old_tok},
                      secrets={"quote_ttl_hours": 72})
check("ttl configurable (72h accepts 49h link)", len(fake.session_state["items"]), 1)
fake, g, gh = invoice(state={"items": [], "p_name": "", "p_phone": ""}, query={"q": tok[:-4] + "AAAA"})
check("tampered link refused", (fake.session_state["items"], any(
    "تالف" in m for m in fake.messages("error"))), ([], True))

# ------------------------------------------------------------
# 5) عميل متكرر / موقوف
# ------------------------------------------------------------
T = datetime.now()


def ev(typ, qid, hours_ago, **kw):
    return make_event(typ, qid, now=T - timedelta(hours=hours_ago), **kw)


hist = [ev("quote", "H1", 200, phone_key=PK, total=500), ev("converted", "H1", 150, total=500),
        ev("quote", "H2", 100, phone_key=PK, total=300)]
fake, g, gh = invoice(events=hist)
check("returning customer shown", any("Returning" in str(c) for c in fake.calls if c[0] == "caption"), True)

opt = hist + [ev("optout", "H2", 5, phone_key=PK)]
fake, g, gh = invoice(events=opt)
check("opted-out customer: warning shown", any("إيقاف" in m for m in fake.messages("warning")), True)
check("opted-out: marketing section locked (script stops there)", "mk" not in g, True)
fake, g, gh = invoice(events=hist)
check("normal customer: marketing section reachable", "mk" in g, True)

# ------------------------------------------------------------
# 6) العروض داخل الفاتورة
# ------------------------------------------------------------
promo = pr.new_promotion(name="CBC week", target="CBC", original_price=400, promo_price=300,
                         start=date.today() - timedelta(days=1), end=date.today() + timedelta(days=5))
fake, g, gh = invoice(state={"items": []}, promos=[promo], clicks={f"promo_{promo['id']}"})
check("promo add button adds item at promo price",
      [(i["name"], i["price"], i["source"]) for i in fake.session_state["items"]],
      [("CBC", 300, f"promo:{promo['id']}")])
expired = {**promo, "start": (date.today() - timedelta(days=20)).isoformat(),
           "end": (date.today() - timedelta(days=10)).isoformat()}
fake, g, gh = invoice(state={"items": []}, promos=[expired])
check("expired promo not offered", not any("عروض شغّالة" in str(c) for c in fake.calls), True)
fake, g, gh = invoice(state={"items": [], "p_name": "", "p_phone": ""}, query={"q": tok}, promos=[promo])
check("restored quote re-priced with active promo", [i["price"] for i in fake.session_state["items"]], [300])

# ------------------------------------------------------------
# 7) صفحة المتابعة
# ------------------------------------------------------------
FU = "pages/3_Follow_Up.py"
fu_ev = [ev("quote", "F1", 31, branch="Diamond", total=700, phone_key=PK, items=["Lipid Profile"]),
         ev("sent", "F1", 30, branch="Diamond", total=700, items=["Lipid Profile"], phone_key=PK,
            contact={"name": "Ahmed Ali", "phone": "201012345678"})]


def page(path, events=None, secrets=None, clicks=(), typed=None, promos=None):
    gh = fs.FakeGitHub()
    gs.requests = gh
    if events:
        gh.put_json(f"events/{month_key()}.json", events)
    if promos is not None:
        gh.put_json(pr.PROMO_PATH, promos)
    fake, g = fs.run_script(path, secrets={**SEC, **(secrets or {})}, clicks=clicks, typed=typed)
    return fake, g, gh


fake, g, gh = page(FU, fu_ev)
links = [c for c in fake.calls if c[0] == "link"]
check("follow-up: due card with whatsapp to the stored number",
      any("wa.me/201012345678" in c[2] for c in links), True)
check("follow-up message carries opt-out line", any("إيقاف" in unquote for unquote in
                                                    [__import__("urllib.parse").parse.unquote(c[2]) for c in links]), True)
fake, g, gh = page(FU, fu_ev, clicks={"f1_F1"})
check("follow-up: 'contacted' logs followup with next_due",
      [(e["type"], bool(e.get("meta", {}).get("next_due"))) for e in gh.events() if e["type"] == "followup"],
      [("followup", True)])
fake, g, gh = page(FU, fu_ev, clicks={"cv_F1"})
check("follow-up: converted logged with total", [(e["type"], e["total"]) for e in gh.events()
                                                if e["type"] == "converted"], [("converted", 700)])
fake, g, gh = page(FU, fu_ev, clicks={"oo_F1"})
oo = [e for e in gh.events() if e["type"] == "optout"]
check("follow-up: opt-out logged with phone key", (len(oo), oo[0].get("pk") if oo else None), (1, PK))
fake, g, gh = page(FU, fu_ev, clicks={"ls_F1"})
check("follow-up: lost logged with a reason", [e.get("reason") for e in gh.events() if e["type"] == "lost_sale"] != [], True)
fake, g, gh = page(FU, fu_ev[:1])
check("follow-up: unsent quote not listed", any(c[0] == "link" for c in fake.calls), False)
fake, g, gh = page(FU, fu_ev, secrets={"access_password": "pw"})
check("follow-up gate: stops without password", any(c[0] == "link" for c in fake.calls), False)
fake, g, gh = page(FU, fu_ev, secrets={"access_password": "pw"}, typed={"_access_pw": "pw"})
check("follow-up gate: opens with password", any(c[0] == "link" for c in fake.calls), True)

# ------------------------------------------------------------
# 8) الداشبورد (بوابة + مؤشرات)
# ------------------------------------------------------------
DB = "pages/1_Dashboard.py"
db_ev = [ev("quote", "D1", 50, branch="Diamond", total=700, discount=100, phone_key=PK,
            items=["Lipid Profile"], campaign_id="OL-261105-AB12"),
         ev("sent", "D1", 49, branch="Diamond", total=700, discount=100, phone_key=PK),
         ev("converted", "D1", 20, branch="Diamond", total=700)]
fake, g, gh = page(DB, db_ev)
metrics = {c[1][0] for c in fake.calls if c[0] == "metric"}
check("dashboard renders new KPIs", {"اتبعتت فعلاً", "متوسط قيمة العرض", "متوسط الخصم",
                                     "📉 قيمة فرص البيع المفقودة"} <= metrics, True)
check("dashboard: old 'lost revenue' wording gone", "💸 إيراد ضايع (Lost)" in metrics, False)
fake, g, gh = page(DB, db_ev, secrets={"access_password": "pw"})
check("dashboard gate: no metrics without password", any(c[0] == "metric" for c in fake.calls), False)
fake, g, gh = page(DB, db_ev, secrets={"access_password": "pw"}, typed={"_access_pw": "pw"})
check("dashboard gate: metrics after password", any(c[0] == "metric" for c in fake.calls), True)
fake, g, gh = page(DB, db_ev)
check("dashboard open-access warning when no password", any("مفتوحة" in m for m in fake.messages("warning")), True)

# ------------------------------------------------------------
# 9) صفحة العروض + استوديو
# ------------------------------------------------------------
PP = "pages/4_Promotions.py"
fake, g, gh = page(PP, clicks={"💾 احفظ العرض"},
                   typed={"pr_pick": "Lipid Profile", "pr_name": "Lipid Nov", "pr_price": 600})
saved = gh.files.get(pr.PROMO_PATH)
check("promotions page saves a promo to GitHub", bool(saved), True)
if saved:
    import json
    lst = json.loads(saved["content"])
    check("saved promo values", (lst[0]["target"], lst[0]["original_price"], lst[0]["promo_price"]),
          ("Lipid Profile", 700, 600))
fake, g, gh = page(PP, clicks={"💾 احفظ العرض"},
                   typed={"pr_pick": "Lipid Profile", "pr_name": "bad", "pr_price": 700})
check("promotions page rejects promo >= list price", (pr.PROMO_PATH in gh.files, any(
    "أقل من السعر الأصلي" in m for m in fake.messages("error"))), (False, True))
fake, g, gh = page(PP, promos=[promo])
check("promotions page lists existing promo + audit tab renders", any(
    c[0] == "dataframe" for c in fake.calls), True)

SS = "pages/2_Marketing_Studio.py"
fake, g, gh = page(SS, promos=[{**promo, "target": "Lipid Profile", "original_price": 700, "promo_price": 600}])
check("studio renders with active promo present", any(c[0] == "image" for c in fake.calls), True)

# ------------------------------------------------------------
# 10) التنقّل بين الصفحات + صورة العروض + المشاركة
# ------------------------------------------------------------
import os
import re

import navigation
import share_widget

fake, g, gh = invoice()
links = [c[1][0] for c in fake.calls if c[0] == "page_link"]
check("invoice shows links to the 4 other pages (not itself)",
      sorted(links), sorted(p for p, _i, _l in navigation.NAV_PAGES if p != "Invoice.py"))
src = open("Invoice.py", encoding="utf-8").read()
check("invoice no longer hides the whole header (holds the pages toggle)",
      re.search(r'header\[data-testid="stHeader"\]\s*\{display:none', src) is None, True)

for path, name in [("pages/1_Dashboard.py", "1_Dashboard"), ("pages/3_Follow_Up.py", "3_Follow_Up"),
                   ("pages/4_Promotions.py", "4_Promotions"), ("pages/2_Marketing_Studio.py", "2_Studio")]:
    f_, g_, gh_ = page(path)
    ln = [c[1][0] for c in f_.calls if c[0] == "page_link"]
    check(f"{name}: nav present, excludes itself, links back to invoice",
          (path not in ln, "Invoice.py" in ln, len(ln)), (True, True, 4))

check("no stray files in pages/ (every page starts with a number)",
      [f for f in os.listdir("pages") if f.endswith(".py") and not f[0].isdigit()], [])
check("every nav target exists on disk", [p for p, _i, _l in navigation.NAV_PAGES if not os.path.exists(p)], [])


class Flaky(fs.FakeSt):
    def page_link(self, path, label=None, icon=None, **kw):
        if "Dashboard" in path:
            raise RuntimeError("page not found")
        if "kwargs_old" in kw:
            raise TypeError
        self.calls.append(("page_link_ok", path))


fk = Flaky()
check("nav survives a missing page (no crash, others shown)", navigation.render_nav(fk, ""), 4)


class OldStreamlit(fs.FakeSt):
    def page_link(self, path, label=None, icon=None, **kw):
        if "use_container_width" in kw:
            raise TypeError("unexpected keyword")
        self.calls.append(("page_link_ok", path))


check("nav falls back for old Streamlit (no use_container_width)", navigation.render_nav(OldStreamlit(), ""), 5)

# صورة عروض الباقات داخل الفاتورة
fake, g, gh = invoice()
html = [c[1] for c in fake.calls if c[0] == "components.html"]
check("marketing expander: offers image rendered", any(c[0] == "image" for c in fake.calls), True)
dl = [c[1] for c in fake.calls if c[0] == "download"]
check("marketing expander: PNG + JPG download buttons for the image",
      (any("PNG" in d for d in dl), any("JPG" in d for d in dl)), (True, True))
check("marketing expander: share-image button embedded", any("navigator.share" in h for h in html), True)
fake, g, gh = invoice(typed={"mk_img_size": "story"})
check("image size selectable (story)", any(c[0] == "image" for c in fake.calls), True)

# المشاركة: مفيش كسر للـ script ولا حقن
evil = 'عرض </script><script>alert(1)</script> "quote" \\ end'
h = share_widget.share_button_html(b"\xff\xd8\xff", evil, 'bad"name\\.jpg')
check("share html: single script block (no breakout)", h.count("</script>"), 1)
check("share html: text embedded as JSON string", '"عرض <\\/script>' in h, True)
check("share html: filename sanitized", 'bad"name' not in h and "badname.jpg" in h, True)
check("share html: base64 image present", "const B64 = \"/9j/\"" in h or "const B64 = \"" in h, True)

print("\n" + "=" * 78)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
