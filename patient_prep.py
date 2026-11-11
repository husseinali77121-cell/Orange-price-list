# patient_prep.py
# ============================================================
#  🧪 تعليمات التحضير للعميل («محتاج صيام؟») — أكتر سؤال بيتسأل على الواتساب.
#  قائمة الأسعار فيها «نوع العينة» للمعمل (2 ml serum…) مش تعليمات للعميل، فدي قائمة منفصلة
#  بتتطابق على أسماء التحاليل في الفاتورة. منطق بحت -> test_whatsapp_suite.py
#
#  ⚠️ دي تعليمات عامة افتراضية — راجعها طبياً وعدّلها حسب سياسة المعمل. لو التحليل مش في
#  القائمة مابنقولش «مش محتاج تحضير»؛ بنسيب التأكيد للمعمل.
# ============================================================

from __future__ import annotations

import re
from typing import Iterable, List, Optional

# (نمط على الاسم بعد lowercase, نص التعليمات). الترتيب مهم: أول قاعدة تنطبق بتكسب لكل تحليل.
PREP_RULES = [
    (r"tolerance|glucose \d(\.\d)? ?hr|ogtt|gtt",
     "منحنى السكر: صيام 8–12 ساعة (المية مسموحة)، والتحليل بياخد حوالي ساعتين في المعمل"),
    (r"ppbg|post ?prandial|\(p\.p\)|postprandial",
     "السكر الفاطر: السحب بعد الأكل بساعتين بالظبط"),
    (r"^fbg$|fasting|homa|insulin \(fasting\)",
     "صيام 8–12 ساعة قبل السحب (المية مسموحة)"),
    (r"lipid|cholesterol|triglycerides|^ldl$|^hdl$|^vldl$|total lipid",
     "الدهون: صيام 9–12 ساعة قبل السحب (المية مسموحة)"),
    (r"^iron \(serum\)$|^tibc$|transferrin saturation",
     "الحديد: يفضّل السحب الصبح وانت صايم"),
    (r"cortisol \(am\)",
     "الكورتيزول الصباحي: السحب الصبح بدري (من 7 لـ 9 ص)"),
    (r"prolactin",
     "البرولاكتين: يفضّل السحب الصبح مع راحة 15–20 دقيقة قبل السحب"),
    (r"^semen examination$",
     "السائل المنوي: امتناع من 2 لـ 7 أيام قبل العينة، والعينة تتعمل في المعمل أو توصل خلال ساعة"),
    (r"^urine examination$|^urine culture$",
     "البول: أول بول الصبح (منتصف التبول) في كوب معقّم من المعمل"),
    (r"^stool examination$|^stool culture$",
     "البراز: عينة طازة في علبة نظيفة جافة وتوصل المعمل خلال ساعتين"),
]

_COMPILED = [(re.compile(p, re.I), t) for p, t in PREP_RULES]


def prep_for_test(name: str) -> Optional[str]:
    n = (name or "").strip().lower()
    for rx, text in _COMPILED:
        if rx.search(n):
            return text
    return None


def prep_lines(names: Iterable[str], bundle_components: Optional[dict] = None) -> List[str]:
    """
    تعليمات مش مكررة لكل تحاليل الفاتورة. bundle_components = {اسم الباقة: [مكوّناتها]} —
    عشان Lipid Profile مثلاً يطلّع تعليمات الصيام من مكوّناته.
    """
    out, seen = [], set()
    for n in names or []:
        cands = [n] + list((bundle_components or {}).get(n, []))
        for c in cands:
            t = prep_for_test(c)
            if t and t not in seen:
                seen.add(t)
                out.append(t)
                break
    return out


def prep_block(names: Iterable[str], bundle_components: Optional[dict] = None) -> str:
    lines = prep_lines(names, bundle_components)
    if not lines:
        return ""
    return "🧪 *قبل التحليل:*\n" + "\n".join(f"• {x}" for x in lines)


def eta_text(result_days: Iterable) -> str:
    """«النتيجة خلال X يوم» من أطول مدة في التحاليل (أو فاضي لو مفيش بيانات)."""
    days = [int(d) for d in result_days if isinstance(d, (int, float)) and d]
    if not days:
        return ""
    m = max(days)
    if m <= 1:
        return "⏱️ النتيجة خلال يوم"
    if m == 2:
        return "⏱️ النتيجة خلال يومين"
    return f"⏱️ النتيجة خلال {m} {'يوم' if m > 10 else 'أيام'}"
