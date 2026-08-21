#!/usr/bin/env python3
"""
اختبار منطق التتبّع (Referral Source + Lost Sale) قبل الرفع:
    python3 test_tracking.py
مفيهوش شبكة ولا streamlit — بيشتغل من الترمكس على طول.
"""
import sys
from datetime import datetime

from tracking import (LOST_SALE_REASONS, REFERRAL_SOURCES, make_event,
                      month_key, summarize_events)

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:58} got={got}")
    if not ok:
        fails.append((label, got, want))


print("=" * 74)
print("--- 1) EVENT BUILDING --------------------------------------------")

now = datetime(2026, 8, 19, 10, 0, 0)
ev = make_event("quote", "OR-260819-0001", branch="Diamond",
                referral_source=REFERRAL_SOURCES[0], total=2000, count=6, now=now)
check("event has correct type", ev["type"], "quote")
check("event has quote_id", ev["quote_id"], "OR-260819-0001")
check("event has branch", ev["branch"], "Diamond")
check("event has ts", ev["ts"], "2026-08-19T10:00:00")
check("event has referral_source", ev["referral_source"], REFERRAL_SOURCES[0])
check("event has total", ev["total"], 2000)
check("event has count", ev["count"], 6)

ev2 = make_event("lost_sale", "OR-260819-0002", reason=LOST_SALE_REASONS[0],
                 total=1200)
check("lost_sale has reason", ev2["reason"], LOST_SALE_REASONS[0])
check("no referral_source key when not given", "referral_source" in ev2, False)

try:
    make_event("bogus", "x")
    check("bad event_type raises", False, True)
except ValueError:
    check("bad event_type raises", True, True)

check("month_key format", month_key(now), "2026-08")

ev3 = make_event("quote", "Q1", items=["CBC", "Vitamin D3", "Kidney Profile"], now=now)
check("quote event carries items list", ev3["items"],
      ["CBC", "Vitamin D3", "Kidney Profile"])
ev4 = make_event("lost_sale", "Q2", reason="السعر")
check("no items key when not given", "items" in ev4, False)

print("\n--- 2) SUMMARIZE: BASIC COUNTS -------------------------------------")

events = [
    make_event("quote", "Q1", referral_source="👨‍⚕️ طبيب / عيادة", total=1000, now=now),
    make_event("converted", "Q1", total=1000, now=now),

    make_event("quote", "Q2", referral_source="💬 WhatsApp", total=800, now=now),
    make_event("lost_sale", "Q2", reason="السعر", total=800, now=now),

    make_event("quote", "Q3", referral_source="💬 WhatsApp", total=500, now=now),
    make_event("lost_sale", "Q3", reason="السعر", total=500, now=now),

    make_event("quote", "Q4", referral_source="🚶 Walk-in", total=600, now=now),
    # Q4 لسه معلّق — مفيش lost_sale ولا converted بعد
]

s = summarize_events(events)
check("total quotes", s["quotes"], 4)
check("total converted", s["converted"], 1)
check("total lost", s["lost"], 2)
check("total pending", s["pending"], 1)
check("conversion pct = converted/(converted+lost)", s["conversion_pct"], 33.3)
check("revenue converted", s["revenue_converted"], 1000)
check("revenue lost", s["revenue_lost"], 1300)

print("\n--- 3) SUMMARIZE: TOP REASONS / SOURCES ----------------------------")
check("top lost reason is price (2x)", s["top_lost_reasons"][0], ("السعر", 2))
check("top source is WhatsApp (2x)", s["top_sources"][0], ("💬 WhatsApp", 2))
check("all 3 sources counted", len(s["top_sources"]), 3)

print("\n--- 4) SUMMARIZE: EDGE CASES ---------------------------------------")
check("empty events -> zeroed summary",
      summarize_events([])["quotes"], 0)
check("empty events -> 0% conversion (no /0 crash)",
      summarize_events([])["conversion_pct"], 0.0)

# نفس quote_id يترجّع له quote تاني (نادر بس ممكن) — لازم يفضل يتعد مرة واحدة
dup = [
    make_event("quote", "Q9", total=100, now=now),
    make_event("quote", "Q9", total=100, now=now),
]
check("duplicate quote events for same id counted once",
      summarize_events(dup)["quotes"], 1)

print("\n--- 5) TOP TESTS + PACKAGE CONVERSION -------------------------------")

pkg_events = [
    make_event("quote", "P1", total=1150,
              items=["Urea", "Creatinine", "Kidney Profile"], now=now),
    make_event("converted", "P1", total=850, now=now),

    make_event("quote", "P2", total=1150, items=["Kidney Profile", "CBC"], now=now),
    make_event("lost_sale", "P2", reason="السعر", total=1150, now=now),

    make_event("quote", "P3", total=300, items=["CBC"], now=now),
    make_event("converted", "P3", total=300, now=now),

    # نفس التحليل مكرر جوه نفس الفاتورة -> يتحسب مرة واحدة بس
    make_event("quote", "P4", total=600, items=["CBC", "CBC"], now=now),
]

s2 = summarize_events(pkg_events, bundle_names={"Kidney Profile"})
check("top_tests: CBC appears in 3 quotes (P2,P3,P4 - not double counted in P4)",
      dict(s2["top_tests"])["CBC"], 3)
check("top_tests: Kidney Profile appears in 2 quotes",
      dict(s2["top_tests"])["Kidney Profile"], 2)
check("package_stats only includes known bundle names",
      set(s2["package_stats"].keys()), {"Kidney Profile"})
kp = s2["package_stats"]["Kidney Profile"]
check("Kidney Profile: 2 quotes total", kp["quotes"], 2)
check("Kidney Profile: 1 converted, 1 lost", (kp["converted"], kp["lost"]), (1, 1))
check("Kidney Profile: 50% conversion", kp["conversion_pct"], 50.0)

check("no bundle_names given -> empty package_stats",
      summarize_events(pkg_events)["package_stats"], {})

print("\n" + "=" * 74)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
