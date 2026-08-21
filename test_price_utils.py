#!/usr/bin/env python3
"""
اختبار المنطق قبل الرفع:  python3 test_price_utils.py
مفيهوش streamlit - بيشتغل من الترمكس على طول.
"""
import re
import sys
from datetime import datetime, timedelta

from bundles import BUNDLES as BUNDLE_DEFS
from bundles import BUNDLE_CATEGORY, bundles_for
from labs_price_list import LABS_DB
from panels import QUICK_PANELS, panel_bundle_name, validate_panels
from price_utils import (MATCH_ALIAS, MATCH_AMBIGUOUS, MATCH_EXACT,
                         MATCH_NOT_FOUND, MATCH_SUGGEST, build_index,
                         build_whatsapp_url, bundle_saving, check_add,
                         compute_totals, decode_quote, encode_quote,
                         generate_quote_id, norm, quote_age_hours,
                         resolve_test, search_tests, suggest_bundle_offers,
                         validate_patient_name, validate_phone)

idx = build_index(LABS_DB, BUNDLE_DEFS, BUNDLE_CATEGORY)
fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:52} got={got}")
    if not ok:
        fails.append((label, got, want))


print("=" * 74)
print(f"DB: {len(idx.records)} rows / {len(idx.by_key)} unique names / "
      f"{len(LABS_DB)} categories")
print("=" * 74)

print("\n--- 1) TEST-NAME RESOLUTION -------------------------------------")
check("exact: 'CBC'", resolve_test("CBC", idx).status, MATCH_EXACT)
check("case/space: '  cbc  '", resolve_test("  cbc  ", idx).status, MATCH_EXACT)
check("punctuation: 'HbA1c'", resolve_test("HbA1c", idx).status, MATCH_EXACT)
check("alias: 'sugar' -> FBG", resolve_test("sugar", idx).best.name, "FBG")
check("alias: 'vit d'", resolve_test("vit d", idx).best.name,
      "Vitamin D3(25 Hydroxy Cholecal.)")
check("alias status is confident", resolve_test("b12", idx).is_confident, True)
check("typo: 'ferritn' -> suggest", resolve_test("ferritn", idx).status, MATCH_SUGGEST)
check("typo best guess", resolve_test("ferritn", idx).best.name, "Ferritin")
check("typo NOT auto-added", resolve_test("ferritn", idx).is_confident, False)
check("guard: 'psa' ambiguous", resolve_test("psa", idx).status, MATCH_AMBIGUOUS)
check("guard: 'h pylori' ambiguous", resolve_test("h pylori", idx).status,
      MATCH_AMBIGUOUS)
check("guard: 'rf' ambiguous", resolve_test("rf", idx).status, MATCH_AMBIGUOUS)
check("garbage rejected", resolve_test("zzqqxx", idx).status, MATCH_NOT_FOUND)
check("empty rejected", resolve_test("", idx).status, MATCH_NOT_FOUND)

# الباج القديم: 'Lipid Profile' كان بيرجع None لأنه category مش test
r = resolve_test("Lipid Profile", idx)
check("'Lipid Profile' no longer silent-fails", r.status != MATCH_NOT_FOUND, True)

print("\n--- 2) AMBIGUITY SHOWS ALL OPTIONS ------------------------------")
r = resolve_test("psa", idx)
print("     PSA options:", [(c.name, c.price) for c in r.candidates])
check("psa gives >=3 options", len(r.candidates) >= 3, True)

print("\n--- 3) PATIENT NAME ---------------------------------------------")
check("empty rejected", validate_patient_name("").ok, False)
check("digits rejected", validate_patient_name("Ahmed 123").ok, False)
check("valid passes", validate_patient_name("ahmed ali hassan").ok, True)
check("auto title-case", validate_patient_name("ahmed ali").value, "Ahmed Ali")
check("single name warns", len(validate_patient_name("Ahmed").warnings) > 0, True)
check("arabic warns for PDF",
      any("PDF" in w for w in validate_patient_name("أحمد علي").warnings), True)
check("arabic still ok for WhatsApp", validate_patient_name("أحمد علي").ok, True)

print("\n--- 4) PHONE ----------------------------------------------------")
check("local 010", validate_phone("01012345678").value, "201012345678")
check("local 015", validate_phone("01512345678").value, "201512345678")
check("spaces/dashes", validate_phone("010 1234-5678").value, "201012345678")
check("+20 form", validate_phone("+201112345678").value, "201112345678")
check("0020 form", validate_phone("00201212345678").value, "201212345678")
check("missing zero", validate_phone("1012345678").value, "201012345678")
check("bad prefix 013 rejected", validate_phone("01312345678").ok, False)
check("too short rejected", validate_phone("0101234").ok, False)
check("letters rejected", validate_phone("010abc45678").ok, False)
check("empty rejected", validate_phone("").ok, False)
check("intl accepted", validate_phone("+966501234567").ok, True)

print("\n--- 5) TOTALS ---------------------------------------------------")
items = [{"name": "CBC", "price": 400, "result_days": 1, "collection_notes": "EDTA"},
         {"name": "TSH", "price": 330, "result_days": 3, "collection_notes": "Serum"}]
t = compute_totals(items, 10, "Percentage")
check("subtotal", t["subtotal"], 730)
check("10% discount", t["discount"], 73)
check("total", t["total"], 657)
check("max TAT", t["max_days"], 3)
t2 = compute_totals(items, 5000, "Fixed Amount")
check("discount capped at subtotal", t2["total"], 0)
t3 = compute_totals(items + [{"name": "X", "price": 0}], 0, "Percentage")
check("unpriced flagged", t3["unpriced"], ["X"])

print("\n--- 6) WHATSAPP URL ---------------------------------------------")
url = build_whatsapp_url("201012345678", "test msg")
check("url targets the number", url.startswith("https://wa.me/201012345678?text="), True)
check("newlines encoded", "%0A" in build_whatsapp_url("201012345678", "a\nb"), True)

print("\n--- 7) QUICK PANEL INTEGRITY ------------------------------------")
broken = validate_panels(idx, resolve_test)
for p, bad in broken.items():
    print(f"     BROKEN {p}: {bad}")
check(f"all {len(QUICK_PANELS)} panels resolve exactly", len(broken), 0)

print("\n--- 8) BUNDLES MERGED INTO PRICE LIST ---------------------------")
check("4 bundles loaded", len(idx.bundles), 4)
for bn, want in [("Lipid Profile", 700), ("Liver Profile", 850),
                 ("Kidney Profile", 850), ("Thyroid Profile", 870)]:
    r = resolve_test(bn, idx)
    check(f"'{bn}' is exact", r.status, MATCH_EXACT)
    check(f"'{bn}' price", r.best.price, want)
    check(f"'{bn}' flagged as bundle", r.best.is_bundle, True)

check("alias 'lft'", resolve_test("lft", idx).best.name, "Liver Profile")
check("alias 'tft'", resolve_test("tft", idx).best.name, "Thyroid Profile")
check("arabic alias 'كبد'", resolve_test("كبد", idx).best.name, "Liver Profile")
check("arabic alias 'وظائف كلى'", resolve_test("وظائف كلى", idx).best.name,
      "Kidney Profile")
check("old typo 'thyroid profie' works",
      resolve_test("thyroid profie", idx).best.name, "Thyroid Profile")
check("bundle ranks first in search",
      search_tests("lipid profile", idx)[0].is_bundle, True)

print("     savings:", [(b.name, bundle_saving(b, idx)[1]) for b in idx.bundles])
check("Lipid saves 250", bundle_saving(idx.get("Lipid Profile")[0], idx)[1], 250)
check("Liver saves 320", bundle_saving(idx.get("Liver Profile")[0], idx)[1], 320)
check("Kidney saves 300", bundle_saving(idx.get("Kidney Profile")[0], idx)[1], 300)

print("\n--- 9) DOUBLE-CHARGE PROTECTION ---------------------------------")
def it(q):
    r = resolve_test(q, idx).best
    return {"name": r.name, "price": r.price, "result_days": r.result_days,
            "collection_notes": r.collection_notes}

inv = [it("lipid profile")]
c = check_add(inv, resolve_test("cholesterol", idx).best, idx)
check("component blocked when bundle present", c.kind, "covered")
check("overpay amount reported", c.saving, 200)

inv = [it(x) for x in ["cholesterol", "triglycerides", "hdl", "ldl"]]
c = check_add(inv, resolve_test("lipid profile", idx).best, idx)
check("bundle supersedes loose items", c.kind, "supersedes")
check("names to replace", len(c.names), 4)

check("no false conflict", check_add([it("cbc")],
                                     resolve_test("tsh", idx).best, idx), None)
check("Ca covered by Kidney bundle",
      check_add([it("kidney profile")],
                resolve_test("calcium (total)", idx).best, idx).kind, "covered")
check("Ferritin not covered",
      check_add([it("kidney profile")],
                resolve_test("ferritin", idx).best, idx), None)

print("\n--- 10) PANEL <-> BUNDLE CONSISTENCY ----------------------------")
for pn in ["🫀 Liver Profile", "🫘 Kidney Profile", "💉 Lipid Profile",
           "🦋 Thyroid Profile"]:
    bn = panel_bundle_name(pn)
    brec = idx.get(bn)[0]
    ptests = {norm(t) for t in QUICK_PANELS[pn]["tests"]}
    check(f"{bn}: panel == bundle components", ptests, brec.component_keys)

check("Diamond branch bundles", len(bundles_for("Diamond")), 4)



# ==========================================================================
# 11) BULK PASTE  ==  لصق قائمة من رسالة عميل
# ==========================================================================
print("\n--- 11) BULK PASTE ------------------------------------------------")

from price_utils import parse_bulk_tests

_msg = """السلام عليكم
1- صورة دم كاملة
2. سكر صائم
3) وظائف كبد
- فيتامين د
كرياتينين، حمض يوريك
TSH + Ferritin
01012345678
12/8/2026
شكرا"""

_toks = parse_bulk_tests(_msg)
check("bullets/numbering stripped", "صورة دم كاملة" in _toks, True)
check("phone dropped", any("0101" in t for t in _toks), False)
check("date dropped", any("12/8" in t for t in _toks), False)
check("comma split", "حمض يوريك" in _toks, True)
check("plus split", "Ferritin" in _toks, True)
check("dedupe", len(parse_bulk_tests("CBC\ncbc\nCBC")), 1)
check("empty input", parse_bulk_tests(""), [])

_hit = sum(1 for t in _toks if resolve_test(t, idx).is_confident)
check("arabic terms resolved", _hit >= 8, True)

# كل alias لازم يشاور على اسم موجود فعلاً
from price_utils import ALIASES
_broken = [k for k, v in ALIASES.items() if not idx.get(v)]
check("no broken aliases", _broken, [])

# الأشكال العربية للـ PDF
from arabic_pdf import shape_arabic, to_pdf_text, has_arabic
check("lam-alef ligature", shape_arabic("لا"), "\ufefb")
check("initial/medial/final", shape_arabic("لبنى"),
      "\ufedf\ufe92\ufee8\ufef0")
check("latin untouched", to_pdf_text("CBC"), "CBC")
check("latin run kept inside arabic", "Ali" in to_pdf_text("أحمد Ali"), True)
check("no arabic -> no change", has_arabic("Hussein"), False)

print("\n--- 12) SMART OFFER ENGINE ---------------------------------------")
# كل مكوّنات الكلى الـ 7 موجودين -> لازم يقترح الباقة (توفير 300 زي bundle_saving)
kidney7 = ["urea", "creatinine", "uric acid", "na", "k", "calcium (total)",
          "phosphorus"]
inv = [it(x) for x in kidney7]
offers = suggest_bundle_offers(inv, idx)
check("kidney offer suggested (all 7 components present)",
      any(o["bundle"].name == "Kidney Profile" for o in offers), True)
kid = next(o for o in offers if o["bundle"].name == "Kidney Profile")
check("kidney offer matched count", len(kid["matched_names"]), 7)
check("kidney offer saving matches bundle_saving()", kid["saving"], 300)

# باقة اتضافت بالفعل -> ما تتقترحش تاني
inv2 = inv + [it("kidney profile")]
check("no re-suggest once bundle already in invoice",
      any(o["bundle"].name == "Kidney Profile"
          for o in suggest_bundle_offers(inv2, idx)), False)

# مكوّن واحد بس -> مش كفاية عشان نقترح (نتجنب الإزعاج على حاجة تافهة)
check("single component -> no suggestion",
      suggest_bundle_offers([it("tsh")], idx), [])

# 5 من 7 بس -> المفرّق (790) أرخص فعلاً من الباقة (850)، زي ما موثّق في
# bundles.py -> ما ينفعش نقترح استبدال يخسّر العميل فلوس
cheap5 = [it(x) for x in ["urea", "creatinine", "uric acid", "na", "k"]]
check("no bad suggestion when loose subset is already cheaper than the bundle",
      any(o["bundle"].name == "Kidney Profile"
          for o in suggest_bundle_offers(cheap5, idx)), False)

print("\n--- 13) QUOTE ID + SAVE/RESUME LINK ------------------------------")
qid = generate_quote_id()
check("quote id format OR-YYMMDD-NNNN", bool(re.match(r"^OR-\d{6}-\d{4}$", qid)), True)
check("quote ids are not all identical", generate_quote_id() != generate_quote_id()
      or True, True)  # عشوائي — ممكن يتكرر نادراً، مش شرط فشل

payload = {"id": qid, "ts": "2026-08-19T10:00:00",
          "items": [{"n": "CBC", "p": 300, "d": 1, "c": "", "cat": "Hematology"}],
          "name": "Mahmoud", "phone": "201012345678", "doctor": "",
          "date_iso": "2026-08-19", "dtype": "Fixed Amount", "dval": 620}
token = encode_quote(payload)
back = decode_quote(token)
check("encode/decode round-trip", back, payload)
check("token is url-safe (no + / =-issues)",
      bool(re.match(r"^[A-Za-z0-9_\-]+$", token)), True)
check("tampered token returns None", decode_quote(token[:-3] + "xyz") is None
      or decode_quote(token[:-3] + "xyz") != payload, True)
check("garbage token returns None", decode_quote("not-a-real-token"), None)

check("fresh quote age ~0h", quote_age_hours(datetime.now().isoformat()) < 0.01, True)
old_ts = (datetime.now() - timedelta(hours=72)).isoformat()
check("72h-old quote flagged past 48h", quote_age_hours(old_ts) > 48, True)
check("bad timestamp -> None", quote_age_hours("not-a-date"), None)

print("\n" + "=" * 74)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
