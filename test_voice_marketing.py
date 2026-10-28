#!/usr/bin/env python3
"""
اختبار الأمر الصوتي (تقسيم الجملة) + قوالب التسويق:
    python3 test_voice_marketing.py
مفيهوش شبكة ولا streamlit.
"""
import sys

from labs_price_list import LABS_DB
from bundles import BUNDLES
from marketing import MARKETING_KINDS, build_marketing_message, share_url
from price_utils import build_index, resolve_test
from voice import mic_html, split_voice_command

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:58} got={got}")
    if not ok:
        fails.append((label, got, want))


check("single test", split_voice_command("CBC"), ["CBC"])
check("and-split", split_voice_command("CBC and ESR and glucose"), ["CBC", "ESR", "glucose"])
check("spelled letters", split_voice_command("c b c"), ["cbc"])
check("filler + comma", split_voice_command("please add TSH, ferritin"), ["TSH", "ferritin"])
check("dedupe", split_voice_command("cbc and CBC"), ["cbc"])
check("empty", split_voice_command("  "), [])
check("arabic kept whole", split_voice_command("صورة دم كاملة"), ["صورة دم كاملة"])
check("vitamin d not spelled", split_voice_command("vitamin d"), ["vitamin d"])

html = mic_html("ar-EG")
check("mic html lang injected", "'ar-EG'" in html and "__LANG__" not in html, True)
check("mic html aria injected", "__ARIA__" not in html, True)

# الاسم المنطوق لازم يوصل لنفس بوابة التحقق: CBC لازم يتعرّف مؤكد
IDX = build_index(LABS_DB, BUNDLES)
check("CBC resolves confidently", resolve_test("CBC", IDX).is_confident, True)

rows = [{"name": "Lipid Profile", "price": 700, "saving": 250},
        {"name": "Thyroid Profile", "price": 870, "saving": 0}]
m = build_marketing_message("offer", "ar", lab="معمل", name="أحمد", bundles=rows, currency="ج.م")
check("offer shows saving", "توفير 250" in m and "أحمد" in m, True)
check("offer hides zero saving", m.count("توفير") == 1, True)
check("followup shows total", "1,200" in build_marketing_message(
    "followup", "ar", lab="L", total=1200, currency="EGP"), True)
check("review link only when set",
      "https://x.y" in build_marketing_message("review", "en", lab="L", review_url="https://x.y")
      and "http" not in build_marketing_message("review", "en", lab="L"), True)
check("all kinds build in both langs", all(
    build_marketing_message(k, l, lab="L", bundles=rows) for k in MARKETING_KINDS
    for l in ("ar", "en")), True)
check("share_url with phone", share_url("a b", "201012345678").startswith(
    "https://wa.me/201012345678?text=a%20b"), True)
check("share_url no phone", share_url("x").startswith("https://wa.me/?text="), True)

print("\n" + "=" * 74)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
