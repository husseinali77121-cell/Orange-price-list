# marketing.py
# ============================================================
#  رسائل تسويقية جاهزة للواتساب — بدون streamlit (قابل للاختبار)
#  كل قالب بيتبني من بيانات حقيقية (الباقات + اسم العميل + إجمالي الفاتورة)
#  والموظف بيعدّل النص قبل الإرسال. التعديل على الصياغة من هنا بس.
# ============================================================

from urllib.parse import quote

MARKETING_KINDS = {
    "offer": "📦 عروض الباقات",
    "followup": "⏰ متابعة عرض سعر",
    "home_visit": "🏠 السحب من المنزل",
    "referral": "🤝 رشّح لصاحبك",
    "review": "⭐ طلب تقييم بعد الخدمة",
}


def share_url(message: str, phone_e164: str = "") -> str:
    base = f"https://wa.me/{phone_e164}" if phone_e164 else "https://wa.me/"
    return f"{base}?text={quote(message, safe='')}"


def _greet(name: str, lang: str) -> str:
    name = (name or "").strip()
    if lang == "en":
        return f"Hello {name} 🍊" if name else "Hello 🍊"
    return f"أهلاً {name} 🍊" if name else "أهلاً بحضرتك 🍊"


def _bundle_lines(bundles, currency: str, lang: str) -> list:
    lines = []
    for b in bundles:
        line = f"📦 {b['name']}: {b['price']:,} {currency}"
        if b.get("saving", 0) > 0:
            line += (f" (save {b['saving']:,})" if lang == "en"
                     else f" (توفير {b['saving']:,} {currency})")
        lines.append(line)
    return lines


def build_marketing_message(kind: str, lang: str = "ar", *, lab: str, name: str = "",
                            total: int = 0, currency: str = "EGP", bundles=(),
                            review_url: str = "") -> str:
    en = lang == "en"
    g = _greet(name, lang)

    if kind == "offer":
        lines = _bundle_lines(bundles, currency, lang)
        head = f"Current packages at {lab}:" if en else f"عروض {lab} الحالية:"
        tail = ("To book or ask anything, just reply here ✅" if en
                else "للحجز أو الاستفسار ابعتلنا هنا ✅")
        return "\n".join([g, head, *lines, tail]) if lines else "\n".join([g, tail])

    if kind == "followup":
        amt = f" ({total:,} {currency})" if total else ""
        if en:
            return (f"{g}\nJust checking on the quote we sent you{amt}. "
                    f"Happy to adjust the tests or book an appointment whenever suits you.")
        return (f"{g}\nبنطمّن على عرض السعر اللي بعتناهولك{amt}. "
                f"لو حابب تعدّل في التحاليل أو تحجز ميعاد إحنا تحت أمرك.")

    if kind == "home_visit":
        if en:
            return (f"{g}\n{lab} offers home sample collection — no travel, no waiting. "
                    f"Send us your address and the tests you need and we'll arrange a time.")
        return (f"{g}\n{lab} بتوفرلك خدمة سحب العينات من البيت — من غير زحمة ولا مواصلات. "
                f"ابعتلنا العنوان والتحاليل المطلوبة وهنرتب معاد مناسب ليك.")

    if kind == "referral":
        who = name.strip() if name and name.strip() else ""
        if en:
            ref = f" and mention {who}" if who else ""
            return (f"{g}\nKnow someone who needs lab tests? Send them our way{ref} "
                    f"when they book — thank you for trusting {lab}.")
        ref = f" وقولّه يذكر اسم {who} وقت الحجز" if who else ""
        return (f"{g}\nلو حد من أهلك أو أصحابك محتاج تحاليل ابعتله رقمنا{ref}. "
                f"شكراً لثقتك في {lab} 🙏")

    if kind == "review":
        if en:
            parts = [f"Thank you for choosing {lab} 🙏",
                     "Your feedback matters — if you were happy with our service, please rate us:"]
        else:
            parts = [f"شكراً لثقتك في {lab} 🙏",
                     "رأيك يهمنا — لو الخدمة عجبتك ياريت تقيّمنا هنا:"]
        if review_url:
            parts.append(review_url)
        return "\n".join(parts)

    raise ValueError(f"unknown marketing kind: {kind}")
