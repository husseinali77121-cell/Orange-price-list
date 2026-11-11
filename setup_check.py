# setup_check.py
# ============================================================
#  🩺 فحص الإعدادات قبل التشغيل الفعلي: Secrets، الروابط، أرقام الفروع، حماية البيانات.
#  بيرجّع قايمة {status: ok|warn|fail, title, hint}. منطق بحت (من غير شبكة) — فحص الريبو
#  (Private؟) جاي من github_store.repo_info() ومتبعت كـ store_info. -> test_replies.py
# ============================================================

from __future__ import annotations

import re
from typing import Dict, List, Optional

from config_store import valid_url
from price_utils import validate_phone

_PLACEHOLDER = re.compile(r"REPLACE|YOUR-|example\.com", re.I)


def _chk(status: str, title: str, hint: str = "") -> Dict[str, str]:
    return {"status": status, "title": title, "hint": hint}


def _sec(secrets, key: str) -> str:
    try:
        return str((secrets or {}).get(key, "") or "")
    except Exception:
        return ""


def run_checks(secrets, cfg: dict, links: dict, store_info: Optional[dict] = None, *,
               default_phone: str = "", offers_phone: str = "", pending_offers: int = 0) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []

    # --- التتبّع وحماية البيانات
    token, repo = _sec(secrets, "gh_events_token"), _sec(secrets, "gh_events_repo")
    if not token or not repo:
        out.append(_chk("fail", "تتبّع العروض (GitHub) مش متظبط",
                        "ضيف gh_events_token و gh_events_repo في Secrets — من غيرهم الداشبورد والمتابعة فاضيين."))
    elif store_info is None:
        out.append(_chk("warn", "ماقدرتش أفحص الريبو", "تأكد من اسم الريبو والـ Token يدوي."))
    elif not store_info.get("ok"):
        out.append(_chk("fail", "الريبو مش متاح بالـ Token ده", store_info.get("error", "")))
    elif store_info.get("private") is False:
        out.append(_chk("fail", "ريبو الأحداث Public!",
                        "ملفات الأحداث فيها أسماء التحاليل وقيم الفواتير وبصمة رقم العميل — لازم Private دايماً."))
    else:
        out.append(_chk("ok", "ريبو الأحداث Private وشغّال"))
    qs = _sec(secrets, "quote_secret")
    if not qs:
        out.append(_chk("fail", "quote_secret مش متظبط",
                        "لينكات العروض مش مشفّرة وبصمة العميل (متكرر/موقوف) مش بتتعمل."))
    elif len(qs) < 16:
        out.append(_chk("warn", "quote_secret قصير", "استخدم نص عشوائي 32 حرف+ ومتغيّروش بعد كده (بيبوّظ البصمات القديمة)."))
    else:
        out.append(_chk("ok", "quote_secret متظبط", "ما تغيّروش — تغييره بيبوّظ لينكات العروض وتعرّف العملاء."))
    if not _sec(secrets, "access_password"):
        out.append(_chk("warn", "مفيش access_password", "Dashboard والفروع والعروض مفتوحة لأي حد معاه اللينك."))
    else:
        out.append(_chk("ok", "كلمة سر الإدارة متظبطة"))
    if not _sec(secrets, "staff_password"):
        out.append(_chk("warn", "مفيش staff_password", "كلمة سر الإدارة هي اللي بتفتح صفحات الموظفين (Follow-up / Customers / Gifts)."))
    contacts = _sec(secrets, "store_contacts").lower() in ("1", "true", "yes", "on")
    out.append(_chk("ok" if contacts else "warn",
                    "store_contacts مفعّل" if contacts else "store_contacts مقفول",
                    "الاسم والرقم بيتخزّنوا — الريبو لازم يفضل Private." if contacts else
                    "الخصوصية أعلى، لكن واتساب المتابعة/VIP/الاسترجاع المباشر مش هيشتغل."))
    from config_store import discount_limit
    limit = discount_limit(cfg)
    if limit <= 0:
        out.append(_chk("warn", "مفيش حد للخصم", "حدّده من تبويب Policy (الافتراضي 50%)."))
    elif not _sec(secrets, "discount_approval_pin"):
        out.append(_chk("warn", f"حد الخصم {limit:.0f}% من غير كود موافقة",
                        "ضيف discount_approval_pin في Secrets وإلا الخصم الكبير هيظهر تحذير بس من غير ما يقفل الإرسال."))
    else:
        out.append(_chk("ok", f"حد الخصم {limit:.0f}% — أكبر منه محتاج كود موافقة"))
    old = _sec(secrets, "discount_limit_pct")
    if old:
        try:
            differs = abs(float(old) - limit) > 1e-9
        except ValueError:
            differs = True
        if differs:
            out.append(_chk("warn", f"discount_limit_pct = {old} في Secrets مابقاش مستخدم",
                            f"الحد الفعلي {limit:.0f}% من تبويب Policy — امسح السطر من Secrets عشان مايلخبطش."))

    # --- الروابط
    app = links.get("app_url", "")
    if not app or _PLACEHOLDER.search(app) or not valid_url(app):
        out.append(_chk("fail", "لينك التطبيق (app_url) مش متظبط",
                        "لينكات العروض المحفوظة مش هتفتح. حطه من تبويب Links (لينك Streamlit بتاعك)."))
    else:
        out.append(_chk("ok", "لينك التطبيق متظبط"))
    for key, label, level in (("review_url", "لينك تقييم Google Maps (رسالة «طلب تقييم» والشكر)", "warn"),
                              ("facebook_page_url", "لينك صفحة فيسبوك (زرار المشاركة)", "warn")):
        if not links.get(key):
            out.append(_chk(level, f"{label} فاضي", "اتضاف من تبويب Links."))
        elif not valid_url(links[key]):
            out.append(_chk("fail", f"{label} مش لينك صحيح", links[key]))
        else:
            out.append(_chk("ok", label.split(" (")[0] + " متظبط"))

    # --- الفروع والأرقام
    phones = []
    for key, b in cfg.get("branches", {}).items():
        v = validate_phone((b.get("phone") or "").replace(" ", ""))
        if not b.get("phone") or not v.ok:
            out.append(_chk("fail", f"رقم {b.get('name_ar', key)} غير صالح", "الرقم ده بيتكتب على الصور والرسائل."))
        phones.append(re.sub(r"\D", "", b.get("phone") or ""))
        if not valid_url(b.get("maps", "")):
            out.append(_chk("fail", f"لينك خريطة {b.get('name_ar', key)} مش صالح"))
    if len(phones) > 1 and len(set(phones)) == 1:
        out.append(_chk("warn", "الفرعين على نفس الرقم", "لو لكل فرع رقم، عدّله من تبويب Branches."))
    if default_phone and offers_phone and re.sub(r"\D", "", default_phone)[-10:] != re.sub(r"\D", "", offers_phone)[-10:]:
        out.append(_chk("warn", "رقمين مختلفين في البرنامج",
                        f"رقم الصور {default_phone} ورقم رسائل العروض {offers_phone} — اختار الرقم الصحيح لكل استخدام."))

    # --- حملات وعروض
    for c in cfg.get("campaigns", []):
        if c.get("active", True) and c.get("end"):
            out.append(_chk("ok", f"حملة «{c['name']}» شغّالة لحد {c['end']}"))
    if pending_offers:
        out.append(_chk("warn", f"{pending_offers} رقم في القائمة الترحيبية من غير تفاصيل", "ضيفهم في offers_data.py."))
    return out


def summary(checks: List[Dict[str, str]]) -> Dict[str, int]:
    out = {"ok": 0, "warn": 0, "fail": 0}
    for c in checks:
        out[c["status"]] += 1
    return out
