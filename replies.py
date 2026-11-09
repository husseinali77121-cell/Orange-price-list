# replies.py
# ============================================================
#  💬 Smart Replies — ردود جاهزة مربوطة باعتراض العميل («أسعاركم غالية؟»، «هفكر وأرد»…)
#  لكل اعتراض رد مختصر ورد مطوّل. الموظف بيخصّص: اسم العميل، الفرع (عنوان/مواعيد/خريطة)،
#  والعروض اللي تتضاف. القواعد بسيطة (من غير AI): الرد بيتبنّي من قالب + متغيّرات.
#  الإرسال بإيد الموظف (البرنامج ما بيبعتش تلقائي). التسجيل (reply event) هو اللي بيغذّي
#  تحليل الاعتراضات في الداشبورد. منطق بحت -> test_replies.py
# ============================================================

from __future__ import annotations

import re
from typing import Dict, List, Optional

GROUPS = {"prices": "💰 الأسعار والاعتراضات", "booking": "📅 الحجز والخدمات", "service": "🧡 خدمة العملاء"}

OBJECTION_LABELS = {
    "price": "السعر غالي", "competitor": "معمل تاني / أرخص", "discount": "طلب خصم",
    "postpone": "هفكر وأرد", "no_time": "مفيش وقت",
}

# المتغيّرات المسموحة في القوالب
VARS = {"greet", "lab", "offers", "fhv", "branch", "review", "phone"}

REPLIES: List[dict] = [
    # ---------------- الأسعار والاعتراضات ----------------
    {"id": "price_high", "group": "prices", "title": "أسعاركم غالية؟", "kind": "objection", "objection": "price",
     "followup_hours": 24, "reason": "السعر", "action": "",
     "short": "{greet}\nمتفهمين حضرتك 🙏 ابعتلنا الروشتة أو أسماء التحاليل وهنراجعها ونوضحلك الإجمالي وأي عرض متاح قبل ما تقرر.{offers}{fhv}",
     "long": ("{greet}\n\nمتفهمين حضرتك، ومن حقك تختار الأنسب ليك. في {lab} بنهتم بجودة إجراءات سحب العينات "
              "ومراجعة النتائج، وهدفنا إن حضرتك تحصل على خدمة واضحة من أول خطوة.\n\n"
              "ابعتلنا صورة الروشتة أو أسماء التحاليل، وهنراجعها لحضرتك ونوضح الإجمالي وأي عروض متاحة حاليًا "
              "قبل ما تقرر.{offers}{fhv}{branch}\n\nيسعدنا نخدمك 🧡")},
    {"id": "cheaper_elsewhere", "group": "prices", "title": "في معمل أرخص؟", "kind": "objection", "objection": "competitor",
     "followup_hours": 24, "reason": "معمل تاني", "action": "",
     "short": "{greet}\nحقك تقارن 🙏 ابعتلنا عرض السعر اللي معاك ونقارن نفس التحاليل بالظبط ونوضحلك أي فرق وأي عرض متاح.{offers}",
     "long": ("{greet}\n\nحقك تقارن وتختار الأنسب ليك 🙏 الأسعار بتختلف حسب التحاليل المشمولة وطريقة الإجراء، "
              "وعشان المقارنة تبقى عادلة ابعتلنا عرض السعر أو الروشتة وهنوضحلك الإجمالي تحليل بتحليل، "
              "وأي عروض أو باقات ممكن تقلّل التكلفة.{offers}{fhv}{branch}\n\nالقرار في الآخر لحضرتك، ويسعدنا نخدمك 🧡")},
    {"id": "ask_discount", "group": "prices", "title": "ممكن خصم؟", "kind": "objection", "objection": "discount",
     "followup_hours": 24, "reason": "السعر", "action": "",
     "short": "{greet}\nأكيد 🍊 بنراجع العروض المتاحة على تحاليلك وبتتطبّق على الفاتورة.{offers}{fhv}\nابعتلنا الروشتة أو أسماء التحاليل.",
     "long": ("{greet}\n\nأكيد 🍊 هنراجع العروض والباقات المتاحة على التحاليل المطلوبة، وأنسب عرض بيتطبّق على "
              "الفاتورة ونوضحلك قيمة التوفير قبل ما تقرر.{offers}{fhv}\n\n"
              "ابعتلنا صورة الروشتة أو أسماء التحاليل ونرد على حضرتك بالإجمالي.{branch}")},
    {"id": "ask_prices", "group": "prices", "title": "عايز أعرف الأسعار", "kind": "objection", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nابعتلنا صورة الروشتة أو أسماء التحاليل وهنرد على حضرتك بالإجمالي وأي عرض متاح 🍊{offers}",
     "long": ("{greet}\n\nيسعدنا نساعد حضرتك 🍊 ابعتلنا صورة الروشتة أو أسماء التحاليل المطلوبة، وهنرد عليك "
              "بالإجمالي وأي عروض متاحة. وتقدر كمان تكتب رقم العرض من القائمة وهنبعتلك تفاصيله.{offers}{fhv}{branch}")},
    {"id": "will_think", "group": "prices", "title": "هفكر وأرد", "kind": "objection", "objection": "postpone",
     "followup_hours": 24, "reason": "هيفكر ويرد", "action": "",
     "short": "{greet}\nعلى راحتك 🙏 هنكون موجودين لأي استفسار، ولو حبيت تعدّل في التحاليل أو تشوف عرض تاني ابعتلنا.{offers}",
     "long": ("{greet}\n\nخد وقتك براحتك 🙏 ولو حابب نتواصل مع حضرتك بكرة نفكّرك أو نجاوب على أي سؤال، "
              "قولّنا. ولو فضّلت ما نتواصلش، برضه تقدر تكلّمنا في أي وقت.{offers}{fhv}{branch}\n\nيسعدنا نخدمك 🧡")},
    {"id": "no_time", "group": "prices", "title": "مشغول / مفيش وقت", "kind": "objection", "objection": "no_time",
     "followup_hours": 24, "reason": "مفيش وقت", "action": "",
     "short": "{greet}\nمفيش مشكلة 🙏 عندنا سحب منزلي في أي وقت حسب الحجز، قولّنا الميعاد والعنوان ونرتب لحضرتك.{fhv}",
     "long": ("{greet}\n\nمفيش مشكلة خالص 🙏 وفّرنا السحب المنزلي عشان الوقت. قولّنا الميعاد المناسب والعنوان "
              "والتحاليل المطلوبة، ونرتب الزيارة لحضرتك.{fhv}{branch}")},
    # ---------------- الحجز والخدمات ----------------
    {"id": "want_book", "group": "booking", "title": "عايز أحجز", "kind": "booking", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nيسعدنا نحجزلك 🍊 ابعتلنا: الاسم، التحاليل المطلوبة، اليوم والساعة المناسبين، ولو زيارة منزلية العنوان والمنطقة.{branch}",
     "long": ("{greet}\n\nيسعدنا نحجزلك 🍊 عشان نأكد الحجز ابعتلنا:\n• الاسم\n• التحاليل المطلوبة\n"
              "• اليوم والساعة المناسبين\n• لو زيارة منزلية: العنوان والمنطقة{offers}{fhv}{branch}\n\nفي انتظارك 🧡")},
    {"id": "home_visit", "group": "booking", "title": "السحب المنزلي", "kind": "booking", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nالسحب المنزلي متاح في أي وقت حسب الحجز 🏠 ابعتلنا العنوان والمنطقة والميعاد والتحاليل المطلوبة.{fhv}",
     "long": ("{greet}\n\nالسحب المنزلي متاح في أي وقت حسب الحجز 🏠 عشان نرتبه لحضرتك ابعتلنا العنوان والمنطقة "
              "والميعاد المناسب والتحاليل المطلوبة.{offers}{fhv}\n\nيسعدنا نخدمك 🧡")},
    {"id": "branch_info", "group": "booking", "title": "العنوان ومواعيد العمل", "kind": "booking", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nأهلاً بحضرتك 🍊{branch}",
     "long": "{greet}\n\nيسعدنا زيارتك في {lab} 🍊{branch}\n\nلو محتاج حاجة قبل ما تيجي كلّمنا ❤️"},
    # ---------------- خدمة العملاء ----------------
    {"id": "delay_apology", "group": "service", "title": "اعتذار عن التأخير", "kind": "service", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nنعتذر لحضرتك عن التأخير 🙏 بنراجع الموضوع حالاً ونرد عليك في أسرع وقت.",
     "long": ("{greet}\n\nنعتذر لحضرتك جداً عن التأخير 🙏 بنراجع الموضوع حالاً مع الفريق المختص، "
              "وهنرد على حضرتك بالتفاصيل في أسرع وقت. شكراً لتفهمك وصبرك.")},
    {"id": "result_inquiry", "group": "service", "title": "الاستفسار عن النتيجة", "kind": "service", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nابعتلنا اسم المريض ورقم الفاتورة وهنراجع حالة النتيجة ونرد على حضرتك 🍊",
     "long": ("{greet}\n\nشكراً لتواصلك 🍊 عشان نراجع حالة النتيجة ابعتلنا اسم المريض ورقم الفاتورة (أو التاريخ "
              "والفرع)، وهنرد على حضرتك بحالتها في أقرب وقت.{branch}")},
    {"id": "thanks", "group": "service", "title": "شكراً بعد الزيارة", "kind": "service", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nشكراً لاختيارك {lab} 🧡 يسعدنا نخدمك دايماً.{review}",
     "long": ("{greet}\n\nشكراً لاختيارك {lab} 🧡 يسعدنا إنك كنت معانا، وصحتك ورضاك أولويتنا. "
              "لو عندك أي ملاحظة أو احتجت أي مساعدة، إحنا موجودين.{review}")},
    {"id": "stop_messages", "group": "service", "title": "إيقاف الرسائل", "kind": "service", "objection": "",
     "followup_hours": 0, "reason": "", "action": "optout",
     "short": "{greet}\nتم إيقاف إرسال الرسائل التسويقية على رقمك ✅",
     "long": ("{greet}\n\nتم إيقاف إرسال الرسائل التسويقية على رقمك ✅ ولو حبيت ترجع تستقبل عروضنا ابعتلنا "
              "كلمة «عروض»، وفي أي وقت تحتاج فيه خدمتنا إحنا موجودين 🧡")},
]


def get(reply_id: str) -> Optional[dict]:
    return next((r for r in REPLIES if r["id"] == reply_id), None)


def by_group() -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {g: [] for g in GROUPS}
    for r in REPLIES:
        out[r["group"]].append(r)
    return out


def offer_lines(offers: List[dict], promos: Optional[List[dict]] = None) -> str:
    """سطور العروض المختارة: عروض الكتالوج (رقم + سعر قبل/بعد) وعروض «إدارة العروض»."""
    lines = []
    for o in offers:
        if not o.get("after"):
            continue
        line = f"• {o['title']}: {o['after']:,} ج"
        if o.get("before"):
            line += f" بدل {o['before']:,} ج"
        lines.append(line)
    for p in promos or []:
        lines.append(f"• {p['name']}: {p['promo_price']:,} ج بدل {p['original_price']:,} ج")
    return "\n".join(lines)


def render_reply(tpl: dict, version: str = "short", *, name: str = "", lab: str = "",
                 offers_text: str = "", fhv_text: str = "", branch_text: str = "",
                 review_url: str = "", phone: str = "") -> str:
    """
    بيبني الرد من القالب. المتغيّرات الاختيارية (العروض/الزيارة المجانية/الفرع/التقييم) بتختفي
    لو فاضية، وبتتحط بسطر فاصل لو موجودة.
    """
    text = tpl["long" if version == "long" else "short"]
    first = (name or "").strip().split(" ")[0] if (name or "").strip() else ""
    values = {
        "greet": f"أهلاً {first} 🍊" if first else "أهلاً بحضرتك 🍊",
        "lab": lab or "معمل أورانج لاب",
        "offers": ("\n\nالعروض المتاحة:\n" + offers_text) if offers_text.strip() else "",
        "fhv": ("\n\n" + fhv_text.strip()) if fhv_text.strip() else "",
        "branch": ("\n\n" + branch_text.strip()) if branch_text.strip() else "",
        "review": (f"\n\nلو حبيت تقيّمنا: {review_url.strip()}") if review_url.strip() else "",
        "phone": phone or "",
    }
    out = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), text)
    return re.sub(r"\n{3,}", "\n\n", out).strip()
