#!/usr/bin/env python3
"""
اختبار توقيع لينكات العروض + إعادة التسعير + منع تكرار الإيراد:
    python3 test_integrity.py
"""
import sys
from datetime import datetime, timedelta

from bundles import BUNDLES
from labs_price_list import LABS_DB
from price_utils import (build_index, decode_quote, decode_quote_checked,
                         encode_quote, reprice_saved_items)
from tracking import make_event, summarize_events

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:58} got={got}")
    if not ok:
        fails.append((label, got, want))


# ---- توقيع اللينك ----
pay = {"id": "OR-1", "dval": 20, "items": [{"n": "CBC", "p": 100}]}
tok = encode_quote(pay, "s3cret")
check("signed roundtrip", decode_quote(tok, "s3cret"), pay)
check("signed status ok", decode_quote_checked(tok, "s3cret")[1], "ok")
body, sig = tok.split(".")
forged = encode_quote({**pay, "dval": 100})            # body معدّل بنفس التوقيع القديم
check("edited body rejected", decode_quote(forged.split(".")[0] + "." + sig, "s3cret"), None)
check("edited status", decode_quote_checked(forged.split(".")[0] + "." + sig, "s3cret")[1],
      "bad_signature")
check("wrong secret rejected", decode_quote(tok, "other"), None)
check("unsigned rejected when secret set", decode_quote_checked(encode_quote(pay), "s3cret"),
      (None, "unsigned"))
check("no secret -> unverified", decode_quote_checked(encode_quote(pay))[1], "unverified")
check("garbage", decode_quote_checked("zzz.yyy", "s3cret")[1], "bad_signature")
check("non-ascii sig no crash", decode_quote_checked("abc.\u0639\u0631\u0628\u064a", "k")[1],
      "bad_signature")

# ---- إعادة التسعير ----
IDX = build_index(LABS_DB, BUNDLES)
real = IDX.records[0]
saved = [{"n": real.name, "p": real.price + 50, "cat": real.category},
         {"n": "Totally Missing Test", "p": 77}, {"bad": 1}]
items, changed, missing = reprice_saved_items(saved, IDX)
check("repriced to current", items[0]["price"], real.price)
check("change reported", changed, [(real.name, real.price + 50, real.price)])
check("missing kept at old price", (missing, items[1]["price"]), (["Totally Missing Test"], 77))
check("malformed item skipped", len(items), 2)

# ---- منع تكرار الإيراد ----
t0 = datetime(2026, 10, 29, 10, 0)
def ev(kind, qid, mins, **kw):
    return make_event(kind, qid, now=t0 + timedelta(minutes=mins), **kw)

dup = [ev("quote", "A", 0, referral_source="📱 Google", total=500),
       ev("converted", "A", 1, total=500), ev("converted", "A", 2, total=500)]
s = summarize_events(dup)
check("double converted counts once", (s["converted"], s["revenue_converted"]), (1, 500))

flip = [ev("quote", "B", 0), ev("converted", "B", 1, total=300),
        ev("lost_sale", "B", 2, reason="السعر", total=300)]
s = summarize_events(flip)
check("converted then lost -> lost only", (s["converted"], s["lost"], s["revenue_converted"],
      s["revenue_lost"]), (0, 1, 0, 300))

flip2 = [ev("quote", "C", 0), ev("lost_sale", "C", 1, reason="السعر", total=200),
         ev("converted", "C", 2, total=200)]
s = summarize_events(flip2)
check("lost then converted -> converted only", (s["converted"], s["lost"], s["pending"]),
      (1, 0, 0))
check("lost reason not counted after flip", s["top_lost_reasons"], [])

s = summarize_events([ev("quote", "D", 0), ev("quote", "D", 1)])
check("duplicate quote events count once", (s["quotes"], s["top_sources"], s["pending"]),
      (1, [("غير محدد", 1)], 1))

print("\n" + "=" * 74)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
