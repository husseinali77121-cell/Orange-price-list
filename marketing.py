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


OPTOUT_LINE_AR = "لو مش حابب نتواصل معاك تاني ابعتلنا «إيقاف» وهنوقف الرسائل."


def build_followup_message(*, lab: str, name: str = "", items=(), total: int = 0,
                           currency: str = "ج.م", attempt: int = 0,
                           optout_line: bool = True, lead: bool = False, cta: str = "",
                           code: str = "", home_visit: bool = True) -> str:
    """رسالة متابعة لعرض اتبعت ولسه من غير قرار (صفحة «متابعة النهاردة»).
    attempt = كام محاولة اتعملت قبل كده — التسلسل: تذكير ودّي ← قيمة (سحب منزلي/حجز سهل) ← آخر
    تذكير خفيف. lead = استفسار من غير عرض سعر (لسه مستنيين الروشتة/أسماء التحاليل).
    cta = سطور «للحجز ردّ برقم…» · code = سطر كود العرض."""
    g = _greet(name, "ar")
    names = [str(i) for i in items][:4]
    more = len(list(items)) - len(names)
    what = "، ".join(names) + (f" و{more} تحاليل تانية" if more > 0 else "") if names else ""
    amt = f" بإجمالي {total:,} {currency}" if total else ""
    if lead:
        if attempt >= 2:
            body = "آخر تذكير 🙏 لو لسه محتاج التحاليل ابعتلنا صورة الروشتة وهنرد عليك بالسعر على طول."
        elif attempt == 1:
            body = ("حابين نطمّن لو لسه محتاج التحاليل 🍊 ابعتلنا صورة الروشتة أو أسماء التحاليل "
                    "وهنبعتلك الإجمالي وأي عرض متاح" + (" — والسحب المنزلي متاح حسب الحجز 🏠." if home_visit else "."))
        else:
            body = ("بنطمّن على حضرتك 🍊 لو لسه محتاج التحاليل ابعتلنا صورة الروشتة أو أسماء التحاليل "
                    "وهنرد عليك بالإجمالي وأي عرض متاح.")
    elif attempt >= 2:
        body = (f"آخر تذكير بخصوص عرض التحاليل{amt} 🙏 "
                f"لو لسه محتاجه ابعتلنا وهنحجزلك ميعاد مناسب.")
    elif attempt == 1:
        body = (f"حابين نسهّلها عليك 🍊 عرض التحاليل" + (f" ({what})" if what else "") + f"{amt} لسه متاح، "
                + ("وتقدر تعمله في الفرع أو بسحب منزلي من غير مشوار 🏠. " if home_visit else "")
                + "قولّنا الميعاد اللي يناسبك ونحجزلك ✅")
    else:
        body = (f"بنفكّرك بعرض التحاليل اللي طلبته" + (f" ({what})" if what else "") + f"{amt}. "
                f"لو حابب تعدّل في التحاليل أو تحجز ميعاد إحنا تحت أمرك ✅")
    parts = [g, f"من {lab}", body]
    if cta and attempt < 2:
        parts += ["", cta]
    if code and not lead:
        parts.append(code)
    if optout_line:
        parts.append(OPTOUT_LINE_AR)
    return "\n".join(parts)
