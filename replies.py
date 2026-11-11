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

GROUPS = {"start": "👋 أول رسالة", "prices": "💰 الأسعار والاعتراضات", "booking": "📅 الحجز والخدمات",
          "service": "🧡 خدمة العملاء"}

OBJECTION_LABELS = {
    "price": "السعر غالي", "competitor": "معمل تاني / أرخص", "discount": "طلب خصم",
    "postpone": "هفكر وأرد", "no_time": "مفيش وقت",
}

# المتغيّرات المسموحة في القوالب. كل «بلوك» (عروض، فرع، عرض سعر…) بيختفي لو فاضي وبيتحط بسطر فاصل لو موجود.
VARS = {"greet", "lab", "offers", "fhv", "branch", "review", "phone",
        "quote", "code", "prep", "eta", "appt", "cta"}
BLOCK_VARS = ("offers", "fhv", "branch", "review", "quote", "code", "prep", "eta", "appt", "cta")

REPLIES: List[dict] = [
    # ---------------- أول رسالة ----------------
    {"id": "welcome", "group": "start", "title": "أهلاً — أول رسالة", "kind": "service", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nنورتنا في {lab} 🧡 ابعتلنا صورة الروشتة أو أسماء التحاليل، وهنرد على حضرتك بالإجمالي وأي عرض متاح في دقايق.{offers}",
     "long": ("{greet}\n\nنورتنا في {lab} 🧡 عشان نخدمك بسرعة:\n📸 ابعت صورة الروشتة، أو\n✍️ اكتب أسماء التحاليل\n"
              "وهنرد عليك بالإجمالي وأي عرض متاح.\n\n🏠 السحب المنزلي متاح حسب الحجز.{offers}{fhv}{branch}")},
    {"id": "prescription_received", "group": "start", "title": "وصلتنا الروشتة", "kind": "service", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nوصلتنا الروشتة ✅ بنراجعها دلوقتي وهنبعتلك الإجمالي وأي عرض متاح خلال دقايق 🍊",
     "long": ("{greet}\n\nوصلتنا الروشتة ✅ شكراً لحضرتك.\nبنراجع التحاليل المطلوبة وهنبعتلك الإجمالي وأي عروض أو "
              "باقات توفّر عليك خلال دقايق 🍊{fhv}")},
    {"id": "price_quote", "group": "start", "title": "عرض السعر (من الفاتورة)", "kind": "quote", "objection": "",
     "followup_hours": 24, "reason": "", "action": "",
     "fallback": {"quote": "ابعتلنا أسماء التحاليل أو صورة الروشتة وهنبعتلك الإجمالي على طول 🍊"},
     "short": "{greet}{quote}{eta}{prep}{cta}{code}",
     "long": ("{greet}\n\nده عرض السعر للتحاليل المطلوبة 🍊{quote}{eta}{prep}{offers}{fhv}{cta}{branch}{code}"
              "\n\nتحت أمرك في أي سؤال 🧡")},
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
     "short": "{greet}\nأكيد 🍊 بنراجع العروض المتاحة على تحاليلك وبتتطبّق على الفاتورة.{offers}{fhv}{quote}\nابعتلنا الروشتة أو أسماء التحاليل.",
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
              "قولّنا. ولو فضّلت ما نتواصلش، برضه تقدر تكلّمنا في أي وقت.{quote}{offers}{fhv}{cta}{branch}{code}\n\nيسعدنا نخدمك 🧡")},
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
    {"id": "prep", "group": "booking", "title": "محتاج صيام؟ / التحضير", "kind": "booking", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "fallback": {"prep": "ابعتلنا أسماء التحاليل (أو رقم العرض) وهنقولك تعليمات التحضير لكل تحليل بالظبط 🙏"},
     "short": "{greet}{prep}\nلو عندك أي سؤال تاني إحنا موجودين 🍊",
     "long": ("{greet}\n\nسؤال مهم 👌 عشان النتيجة تطلع دقيقة:{prep}\n\nولو الدكتور كاتب تعليمات مختلفة اتّبع كلامه، "
              "ولو عندك أي سؤال ابعتلنا 🍊{cta}")},
    {"id": "result_time", "group": "booking", "title": "النتيجة بتطلع إمتى؟", "kind": "booking", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "fallback": {"eta": "معاد النتيجة بيختلف حسب التحليل — ابعتلنا أسماء التحاليل ونقولك بالظبط ⏱️"},
     "short": "{greet}{eta}\nوهنبلغ حضرتك أول ما تجهز 🍊",
     "long": "{greet}\n\n{lab} بيهتم بالدقة والسرعة مع بعض 🍊{eta}\n\nوهنبلغ حضرتك أول ما النتيجة تجهز.{cta}"},
    {"id": "booking_confirm", "group": "booking", "title": "تأكيد الحجز", "kind": "booking", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nتم تأكيد حجزك ✅{appt}{prep}{branch}{code}",
     "long": ("{greet}\n\nتم تأكيد حجز حضرتك ✅{appt}{quote}{prep}{fhv}{branch}{code}"
              "\n\nلو حابب تغيّر الميعاد ابعتلنا في أي وقت 🧡")},
    {"id": "appt_reminder", "group": "booking", "title": "تذكير بالميعاد (قبلها بيوم)", "kind": "booking", "objection": "",
     "followup_hours": 0, "reason": "", "action": "",
     "short": "{greet}\nبنفكّرك بميعادك معانا 🍊{appt}{prep}{branch}",
     "long": ("{greet}\n\nبنفكّر حضرتك بميعاد التحاليل 🍊{appt}{prep}{branch}"
              "\n\nلو محتاج تغيّر الميعاد قولّنا ونرتبلك ميعاد تاني 🙏")},
    {"id": "missed_appt", "group": "booking", "title": "ماحضرش الميعاد", "kind": "booking", "objection": "",
     "followup_hours": 24, "reason": "تأجيل لوقت تاني", "action": "",
     "short": "{greet}\nافتقدناك في ميعادك 🙏 تحب نحجزلك ميعاد تاني أو سحب منزلي يناسبك؟{offers}{fhv}",
     "long": ("{greet}\n\nافتقدناك في ميعاد التحاليل 🙏 ولا يهمك، نقدر نحجزلك ميعاد تاني في الوقت اللي يناسبك أو "
              "سحب منزلي من غير مشوار.{quote}{offers}{fhv}{cta}{branch}\n\nابعتلنا اليوم والساعة المناسبين 🧡")},
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
                 review_url: str = "", phone: str = "", quote_text: str = "", code_text: str = "",
                 prep_text: str = "", eta_text: str = "", appt_text: str = "", cta_text: str = "") -> str:
    """
    بيبني الرد من القالب. المتغيّرات الاختيارية (العروض/الزيارة المجانية/الفرع/التقييم/عرض السعر/الكود/
    التحضير/النتيجة/الميعاد/طريقة الحجز) بتختفي لو فاضية، وبتتحط بسطر فاصل لو موجودة. القالب ممكن يحدد
    fallback لمتغيّر أساسي (مثلاً رد «محتاج صيام؟» من غير تحاليل ← اطلب أسماء التحاليل).
    """
    text = tpl["long" if version == "long" else "short"]
    first = (name or "").strip().split(" ")[0] if (name or "").strip() else ""
    blocks = {"offers": ("العروض المتاحة:\n" + offers_text) if offers_text.strip() else "",
              "fhv": fhv_text, "branch": branch_text,
              "review": f"لو حبيت تقيّمنا: {review_url.strip()}" if review_url.strip() else "",
              "quote": quote_text, "code": code_text, "prep": prep_text, "eta": eta_text,
              "appt": appt_text, "cta": cta_text}
    for k, fb in (tpl.get("fallback") or {}).items():
        if not (blocks.get(k) or "").strip():
            blocks[k] = fb
    values = {"greet": f"أهلاً {first} 🍊" if first else "أهلاً بحضرتك 🍊",
              "lab": lab or "معمل أورانج لاب", "phone": phone or ""}
    for k in BLOCK_VARS:
        v = (blocks.get(k) or "").strip()
        values[k] = ("\n\n" + v) if v else ""
    out = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), text)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


# ------------------------------------------------------------
# بلوكات بتتبني من بيانات حقيقية (الفاتورة / العرض المسجّل / الفروع)
# ------------------------------------------------------------

_AR_DAYS = ("الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت", "الحد")


def quote_block(items, total: int, *, discount: int = 0, currency: str = "ج", max_items: int = 8) -> str:
    """«🧾 عرض السعر» — أسماء التحاليل + الإجمالي (+ الخصم). من غير سعر كل تحليل زي رسالة الفاتورة."""
    names = [str(i) for i in items or []]
    if not names or not total:
        return ""
    shown = names[:max_items]
    lines = ["🧾 *عرض السعر:*"] + [f"• {n}" for n in shown]
    if len(names) > max_items:
        lines.append(f"• + {len(names) - max_items} تحاليل تانية")
    if discount:
        lines.append(f"الخصم: {int(discount):,} {currency} 🎁")
    lines.append(f"*الإجمالي: {int(total):,} {currency}*")
    return "\n".join(lines)


def code_line(quote_id: str) -> str:
    return f"🔖 كود العرض: {quote_id} — اذكره عند الحضور أو الحجز" if quote_id else ""


def appt_line(iso: str) -> str:
    """«📅 الميعاد: الخميس 12/11 — 10:30 ص» من ISO."""
    from datetime import datetime
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    h12 = d.hour % 12 or 12
    ampm = "ص" if d.hour < 12 else "م"
    return f"📅 الميعاد: {_AR_DAYS[d.weekday()]} {d.day}/{d.month} — الساعة {h12}:{d.minute:02d} {ampm}"


def booking_cta(branch_names: List[str], *, home: bool = True) -> str:
    """«✅ للحجز ردّ برقم: 1️⃣ فرع لاسيتيه · 2️⃣ فرع دياموند · 3️⃣ سحب منزلي»."""
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    opts = [n for n in branch_names if n][:4] + (["سحب منزلي 🏠"] if home else [])
    if not opts:
        return ""
    return "✅ *للحجز ردّ برقم:*\n" + "\n".join(f"{nums[i]} {o}" for i, o in enumerate(opts))


def suggested(intents: List[dict]) -> List[dict]:
    """نوايا wa_inquiry.detect_intents ← قوالب الردود المقابلة (اللي موجودة بس)."""
    out = []
    for x in intents or []:
        t = get(x.get("reply", ""))
        if t and t not in out:
            out.append(t)
    return out
