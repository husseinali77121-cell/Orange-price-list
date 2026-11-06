#!/usr/bin/env python3
"""
اختبار: لينكات العروض المشفّرة + انتهاء الصلاحية، وأحداث sent/followup/optout،
وقايمة المتابعة، وتصنيف العميل، ومؤشرات الداشبورد.
    python3 test_followup_security.py
"""
import sys
from datetime import datetime, timedelta

from price_utils import (QUOTE_TTL_HOURS, decode_quote_checked, encode_quote,
                         quote_age_hours)
from tracking import (customer_profile, followup_queue, make_event,
                      marketing_kpis, optout_keys, phone_key, quote_records,
                      summarize_events)

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:64} got={got}")
    if not ok:
        fails.append((label, got, want))


SECRET = "s3cret-key"
NOW = datetime(2026, 11, 5, 12, 0, 0)

# ------------------------------------------------------------
# 1) لينك مشفّر: مفيهوش بيانات مقروءة، وبيتفتح بنفس المفتاح بس
# ------------------------------------------------------------
payload = {"id": "OR-261105-0001", "ts": NOW.isoformat(timespec="seconds"),
           "name": "Hussein Ali", "phone": "01097902820",
           "items": [{"n": "CBC", "p": 100}]}
tok = encode_quote(payload, SECRET)
check("encrypted token prefix", tok.startswith("e1."), True)
check("no plaintext name/phone in token", "Hussein" not in tok and "0109790" not in tok, True)
check("decodes with same secret", decode_quote_checked(tok, SECRET), (payload, "ok"))
check("wrong secret rejected", decode_quote_checked(tok, "other")[1], "bad_signature")
check("no secret can't open encrypted", decode_quote_checked(tok, "")[1], "corrupt")
check("tokens are randomized (nonce)", encode_quote(payload, SECRET) != tok, True)

# أي تلاعب في حرف = رفض
body = tok[3:]
for pos in (0, 5, len(body) // 2, len(body) - 3):
    flipped = body[:pos] + ("A" if body[pos] != "A" else "B") + body[pos + 1:]
    check(f"tampered char @{pos} rejected", decode_quote_checked("e1." + flipped, SECRET)[0], None)
check("truncated token rejected", decode_quote_checked(tok[:-10], SECRET)[0], None)
check("empty token", decode_quote_checked("", SECRET)[0], None)
check("garbage token", decode_quote_checked("e1.@@@", SECRET)[0], None)

# توافق مع الصيغة القديمة (موقّعة بس) + من غير secret
legacy = encode_quote(payload, SECRET, legacy=True)
check("legacy signed link still opens", decode_quote_checked(legacy, SECRET), (payload, "ok"))
check("no-secret link still works (unverified)",
      decode_quote_checked(encode_quote(payload, ""), "")[1], "unverified")

# ------------------------------------------------------------
# 2) انتهاء الصلاحية
# ------------------------------------------------------------
fresh = encode_quote({**payload, "ts": (NOW - timedelta(hours=47)).isoformat()}, SECRET)
old = encode_quote({**payload, "ts": (NOW - timedelta(hours=49)).isoformat()}, SECRET)
nots = encode_quote({k: v for k, v in payload.items() if k != "ts"}, SECRET)
check("47h link opens (ttl 48)", decode_quote_checked(fresh, SECRET, max_age_hours=QUOTE_TTL_HOURS, now=NOW)[1], "ok")
check("49h link expired", decode_quote_checked(old, SECRET, max_age_hours=QUOTE_TTL_HOURS, now=NOW), (None, "expired"))
check("missing ts -> expired (fail closed)", decode_quote_checked(nots, SECRET, max_age_hours=48, now=NOW)[1], "expired")
future = encode_quote({**payload, "ts": (NOW + timedelta(hours=30)).isoformat()}, SECRET)
check("future-dated ts -> expired", decode_quote_checked(future, SECRET, max_age_hours=48, now=NOW)[1], "expired")
check("no ttl given -> old still opens (backward compat)", decode_quote_checked(old, SECRET)[1], "ok")
check("quote_age_hours with now", round(quote_age_hours((NOW - timedelta(hours=5)).isoformat(), now=NOW)), 5)

# ------------------------------------------------------------
# 3) بصمة الموبايل
# ------------------------------------------------------------
pk1 = phone_key("201097902820", SECRET)
check("phone key length", len(pk1), 16)
check("phone key deterministic", phone_key("+20 109 790 2820", SECRET), pk1)
check("phone key differs per number", phone_key("201097902821", SECRET) != pk1, True)
check("phone key differs per secret", phone_key("201097902820", "x") != pk1, True)
check("no secret -> empty key", phone_key("201097902820", ""), "")
check("short number -> empty key", phone_key("123", SECRET), "")
check("key doesn't contain number", "1097902820" not in pk1, True)

# ------------------------------------------------------------
# 4) أحداث + قايمة المتابعة
# ------------------------------------------------------------

def ev(typ, qid, hours_ago, **kw):
    return make_event(typ, qid, now=NOW - timedelta(hours=hours_ago), **kw)


A, B, C, D, E_ = "OR-A", "OR-B", "OR-C", "OR-D", "OR-E"
pkA, pkB = phone_key("201000000001", SECRET), phone_key("201000000002", SECRET)
events = [
    # A: اتبعت من 30 ساعة، لسه من غير قرار -> due
    ev("quote", A, 31, branch="Diamond", total=700, discount=100, phone_key=pkA,
       items=["Lipid Profile"], campaign_id="OL-261101-AAAA", referral_source="📘 Facebook"),
    ev("sent", A, 30, branch="Diamond", contact={"name": "Ahmed Ali", "phone": "201000000001"}),
    # B: اتبعت من 5 ساعات -> upcoming
    ev("quote", B, 6, branch="La Cité", total=300, phone_key=pkB, items=["CBC"]),
    ev("sent", B, 5, branch="La Cité"),
    # C: اتبعت واتباع -> مش في القايمة
    ev("quote", C, 80, branch="Diamond", total=900, phone_key=pkA, items=["Lipid Profile"],
       campaign_id="OL-261101-AAAA"),
    ev("sent", C, 79),
    ev("converted", C, 60, branch="Diamond", total=900),
    # D: اتبعت من 30 ساعة وفيه optout -> مش في القايمة
    ev("quote", D, 31, branch="Diamond", total=200, phone_key=pkB),
    ev("sent", D, 30),
    ev("optout", D, 2, phone_key=pkB),
    # E: اتجهّز بس ماتبعتش -> مش في القايمة (require_sent)
    ev("quote", E_, 40, branch="Diamond", total=150),
]
q = followup_queue(events, NOW)
check("due list = [A]", [x["quote_id"] for x in q["due"]], [A])
check("upcoming list = [B]... but B opted out by pk", [x["quote_id"] for x in q["upcoming"]], [])
check("converted not queued", C not in [x["quote_id"] for k in q.values() for x in k], True)
check("optout by phone key excludes ALL that number's quotes",
      B not in [x["quote_id"] for k in q.values() for x in k], True)
check("unsent quote not queued", E_ not in [x["quote_id"] for k in q.values() for x in k], True)
check("contact carried to queue item", q["due"][0]["contact"]["name"], "Ahmed Ali")
check("due_at = sent + 24h", q["due"][0]["due_at"], NOW - timedelta(hours=30) + timedelta(hours=24))

# snooze: followup بميعاد بعد بكرة -> upcoming
ev_snooze = events + [ev("followup", A, 1, meta={"next_due": (NOW + timedelta(hours=20)).isoformat()})]
q2 = followup_queue(ev_snooze, NOW)
check("snoozed -> upcoming", ([x["quote_id"] for x in q2["due"]], [x["quote_id"] for x in q2["upcoming"]]), ([], [A]))
check("attempts counted", q2["upcoming"][0]["attempts"], 1)

# 3 محاولات -> exhausted
ev_ex = events + [ev("followup", A, h) for h in (20, 10, 2)]
q3 = followup_queue(ev_ex, NOW)
check("3 attempts -> exhausted", ([x["quote_id"] for x in q3["due"]], [x["quote_id"] for x in q3["exhausted"]]), ([], [A]))

# stale بعد 14 يوم
ev_old = [ev("quote", "OR-X", 24 * 20, total=100), ev("sent", "OR-X", 24 * 20)]
check("stale after 14 days", [x["quote_id"] for x in followup_queue(ev_old, NOW)["stale"]], ["OR-X"])

# optout بالـ quote_id لوحده (من غير بصمة)
ev_q_opt = [ev("quote", "OR-Y", 30, total=100), ev("sent", "OR-Y", 30), ev("optout", "OR-Y", 1)]
check("optout by quote id", sum(len(v) for v in followup_queue(ev_q_opt, NOW).values()), 0)

# ------------------------------------------------------------
# 5) تصنيف العميل
# ------------------------------------------------------------
check("pkA = Returning (2 quotes, 1 converted)", customer_profile(events, pkA)["label"], "Returning")
check("pkA revenue", customer_profile(events, pkA)["revenue"], 900)
check("pkB opted out flag", customer_profile(events, pkB)["optout"], True)
check("unknown key = New", customer_profile(events, "deadbeef00000000")["label"], "New")
vip_ev = []
for i in range(3):
    vip_ev += [ev("quote", f"V{i}", 100 - i, phone_key="vipvipvipvipvipv", total=100),
               ev("converted", f"V{i}", 50 - i, total=100)]
check("3 purchases = VIP", customer_profile(vip_ev, "vipvipvipvipvipv")["label"], "VIP")
check("empty key = New", customer_profile(events, "")["label"], "New")
check("optout_keys", optout_keys(events), {pkB})

# ------------------------------------------------------------
# 6) مؤشرات الداشبورد
# ------------------------------------------------------------
k = marketing_kpis(events)
check("kpi sent", k["sent"], 4)
check("kpi prepared_not_sent", k["prepared_not_sent"], 1)
check("kpi avg quote value", k["avg_quote_value"], round((700 + 300 + 900 + 200 + 150) / 5))
check("kpi avg discount pct", k["avg_discount_pct"], round(100.0 * 100 / (700 + 100 + 300 + 900 + 200 + 150), 1))
check("kpi customers (distinct phone keys)", k["customers"], 2)
check("kpi returning customers", k["returning_customers"], 2)
check("kpi hours to convert (sent 79h -> converted 60h)", k["avg_hours_to_convert"], 19.0)
check("kpi branch Diamond quotes", k["by_branch"]["Diamond"]["quotes"], 4)
check("kpi branch Diamond revenue", k["by_branch"]["Diamond"]["revenue"], 900)
cs = k["campaign_stats"]["OL-261101-AAAA"]
check("campaign: 2 quotes, 1 converted, revenue 900", (cs["quotes"], cs["converted"], cs["revenue"]), (2, 1, 900))
check("kpi lost value (no lost)", k["lost_value"], 0)
check("kpis on empty", marketing_kpis([])["avg_quote_value"], 0)

# الأرقام القديمة ماتتأثرتش بالأنواع الجديدة
s = summarize_events(events)
check("summary quotes unaffected", s["quotes"], 5)
check("summary converted", s["converted"], 1)
check("summary pending", s["pending"], 4)

# تعديل القرار: converted بعد lost للعرض نفسه -> الأحدث
ev_flip = [ev("quote", "Z", 10, total=500), ev("lost_sale", "Z", 5, total=500, reason="السعر"),
           ev("converted", "Z", 1, total=500)]
check("latest decision wins in records", quote_records(ev_flip)["Z"]["decision"], "converted")

print("\n" + "=" * 74)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
