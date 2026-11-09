# tzsetup.py
# ============================================================
#  🕒 توقيت القاهرة لكل البرنامج. Streamlit Cloud بيشتغل UTC، فـ datetime.now() / date.today()
#  كانوا بيتأخروا 2–3 ساعات عن القاهرة (حملة بتنتهي 30 نوفمبر، ميعاد متابعة، مواعيد حجز).
#  الاستيراد بيظبط توقيت العملية كلها مرة واحدة (Linux) من غير ما نغيّر أي استدعاء.
#  تغيير التوقيت: متغيّر البيئة APP_TIMEZONE (الافتراضي Africa/Cairo).
#  ملحوظة: الأحداث القديمة المتسجّلة بـ UTC هتبقى فرقها 2–3 ساعات عن الجديدة — مش بيأثر على التحليل.
# ============================================================

import os
import time

APP_TZ = os.environ.get("APP_TIMEZONE", "Africa/Cairo")


def apply(tz: str = APP_TZ) -> bool:
    """بيظبط التوقيت. بيرجّع False على نظام من غير tzset (Windows) — توقيته المحلي هو المستخدم."""
    os.environ["TZ"] = tz
    if hasattr(time, "tzset"):
        time.tzset()
        return True
    return False


apply()
