#!/usr/bin/env python3
"""
اختبار توليد الـ PDF قبل الرفع:  python3 test_pdf_invoice.py
محتاج fpdf2 متثبت.  مفيهوش streamlit - بيشتغل من الترمكس على طول.

الباج اللي الاختبار ده بيمنع رجوعه:
    multi_cell(0, ...) مرتين ورا بعض من غير ما x يرجع للهامش.
    fpdf2 بيسيب x على يمين الخلية (new_x=RIGHT)، فالنداء التاني
    بيحسب عرض = صفر ويرمي:
        FPDFException: Not enough horizontal space to render a single character
    الشرط: نوتتين مختلفتين أو أكتر في نفس الفاتورة = تقريباً كل فاتورة.
"""
import sys

from pdf_invoice import build_pdf, unicode_ready

fails = []


def check(label, fn):
    try:
        data = fn()
        ok = isinstance(data, bytes) and data[:4] == b"%PDF" and len(data) > 500
        note = f"{len(data)} bytes"
    except Exception as e:
        ok, note = False, f"{type(e).__name__}: {e}"
    print(f"{'PASS' if ok else 'FAIL'}  {label:44} {note}")
    if not ok:
        fails.append((label, note))


def items(n, note="collection note", name="Test"):
    return [{"name": f"{name} {i}", "price": 100 + i, "result_days": 1,
             "collection_notes": f"{note} {i}"} for i in range(n)]


TOT = {"subtotal": 790, "discount": 158, "discount_label": "خصم",
       "total": 632, "count": 4, "max_days": 1, "unpriced": []}


def build(its, tot=None, name="Ahmed Hassan"):
    return lambda: build_pdf(its, tot or TOT, name, "201016876282",
                             "Dr. Tarek El-Shafei", "17-08-2026",
                             "https://maps.app.goo.gl/example")


print("=" * 74)
print(f"unicode font available: {unicode_ready()}")
print("=" * 74)

check("empty invoice", build([], {**TOT, "max_days": None}))
check("1 item / 1 note", build(items(1)))
check("2 items / 2 notes  <-- THE REGRESSION", build(items(2)))
check("4 items / 4 notes  <-- real invoice", build(items(4)))
check("8 items / 8 notes", build(items(8)))
check("12 notes (capped at 8)", build(items(12)))
check("5 items sharing one note",
      build([{**i, "collection_notes": "same note"} for i in items(5)]))
check("no notes at all",
      build([{**i, "collection_notes": ""} for i in items(4)]))
check("very long test name (wraps)", build(items(2, name="X" * 160)))
check("unbreakable 300-char token",
      build([{"name": "A" * 300, "price": 1, "result_days": None,
              "collection_notes": "B" * 400}]))
check("60 items (multi-page)", build(items(60)))
check("zero discount", build(items(3), {**TOT, "discount": 0}))
check("unpriced item -> TBD",
      build([{"name": "New test", "price": 0, "result_days": None,
              "collection_notes": "serum"}], {**TOT, "max_days": None}))

if unicode_ready():
    check("arabic patient name", build(items(3), name="أحمد حسن محمد"))
    check("arabic test name",
          build([{"name": "صورة دم كاملة", "price": 150, "result_days": 1,
                  "collection_notes": "2 ml EDTA"},
                 {"name": "وظائف كبد", "price": 300, "result_days": 1,
                  "collection_notes": "2 ml serum"}]))
    check("mixed arabic + latin", build(items(2), name="أحمد Ali Hassan"))

print("\n" + "=" * 74)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
