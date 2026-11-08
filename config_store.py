# config_store.py
# ============================================================
#  ⚙️ إعدادات الإدارة القابلة للتعديل من البرنامج (من غير تعديل كود):
#  بيانات الفروع · حملات المزايا (زيارة منزلية مجانية…) · قواعد VIP ·
#  أنواع الهدايا · قايمة الموظفين · مناطق العملاء.
#  التخزين: config/app_config.json على GitHub (نفس ريبو الأحداث). الافتراضي مبني
#  من brand.py وcampaigns.py، وأي قيمة متخزّنة بتغطّي الافتراضي. كل تعديل بيتسجّل
#  كحدث config_change (مين عدّل وإيه) = Audit Log.
# ============================================================

from __future__ import annotations

import copy
import re
from typing import Dict, List, Optional

from brand import BRANCH_INFO, DEFAULT_PHONE, WORKING_HOURS_AR
from campaigns import FREE_HOME_VISIT_SEED
from tracking import DEFAULT_VIP_RULES

CONFIG_PATH = "config/app_config.json"
SECTIONS = ("branches", "campaigns", "vip", "gifts", "staff", "areas")

DEFAULT_AREAS = ["6 October", "Sheikh Zayed", "Other"]
DEFAULT_GIFTS = [{"id": "welcome_gift", "name": "Welcome Gift", "cost": 0}]
BRANCH_NAMES_EN = {"Orange (La Cité)": "La Cité Branch", "Diamond": "Diamond Branch"}


def default_config() -> dict:
    branches = {}
    for key, info in BRANCH_INFO.items():
        branches[key] = {
            "name_ar": info["name_ar"], "name_en": BRANCH_NAMES_EN.get(key, key),
            "address": info["address"], "maps": info["maps"],
            "phone": DEFAULT_PHONE, "hours": WORKING_HOURS_AR,
            "services": ["تحاليل طبية", "زيارات منزلية (حسب الحجز)"],
        }
    return {"branches": branches, "campaigns": [copy.deepcopy(FREE_HOME_VISIT_SEED)],
            "vip": dict(DEFAULT_VIP_RULES), "gifts": copy.deepcopy(DEFAULT_GIFTS),
            "staff": [], "areas": list(DEFAULT_AREAS)}


def effective(stored) -> dict:
    """الافتراضي + المتخزّن (الفروع تتدمج حقل بحقل؛ باقي الأقسام المتخزّن بيغطّي)."""
    cfg = default_config()
    if not isinstance(stored, dict):
        return cfg
    for key, info in (stored.get("branches") or {}).items():
        if isinstance(info, dict):
            cfg["branches"].setdefault(key, {}).update(info)
    for sec in ("campaigns", "gifts", "staff", "areas"):
        if isinstance(stored.get(sec), list):
            cfg[sec] = stored[sec]
    if isinstance(stored.get("vip"), dict):
        cfg["vip"].update(stored["vip"])
    return cfg


def load(store) -> dict:
    """بيقرا الإعدادات؛ أي مشكلة (مفيش تتبّع/شبكة) = الافتراضي."""
    if not store:
        return default_config()
    try:
        data, _ = store.read(CONFIG_PATH)
        return effective(data)
    except Exception:
        return default_config()


def save_section(store, section: str, value, *, who: str, note: str = "") -> dict:
    """بيحفظ قسم واحد (CAS) ويسجّل config_change. ValueError لو من غير اسم المعدِّل."""
    from github_store import events_path
    from tracking import make_event, month_key
    if section not in SECTIONS:
        raise ValueError(f"قسم مش معروف: {section}")
    if not (who or "").strip():
        raise ValueError("اكتب اسمك — كل تعديل بيتسجّل باسم اللي عمله")

    def apply(d):
        d = dict(d) if isinstance(d, dict) else {}
        d[section] = value
        return d

    store.update(CONFIG_PATH, apply, message=f"config: {section} by {who.strip()}")
    store.append(events_path(month_key()), make_event(
        "config_change", f"CFG-{section}", meta={"section": section, "by": who.strip(), "note": note}))
    return load(store)


# ------------------------------------------------------------
# تحقق
# ------------------------------------------------------------

def validate_branch(info: dict) -> List[str]:
    errs = []
    if not (info.get("name_ar") or "").strip():
        errs.append("اسم الفرع مطلوب")
    if not (info.get("address") or "").strip():
        errs.append("العنوان مطلوب")
    if not re.match(r"^https://", (info.get("maps") or "").strip()):
        errs.append("لينك الخريطة لازم يبدأ بـ https://")
    if not (info.get("hours") or "").strip():
        errs.append("مواعيد العمل مطلوبة")
    if info.get("phone") and len(re.sub(r"\D", "", info["phone"])) < 8:
        errs.append("رقم التواصل غير صالح")
    return errs


def branch_block(info: dict, *, compact: bool = False) -> str:
    """بيانات الفرع اللي بتتبعت مع عرض السعر: عنوان + مواعيد + رقم + خريطة (+ خدمات)."""
    if compact:
        return f"📍 {info['name_ar']}\n🗺️ {info['maps']}"
    lines = [f"📍 {info['name_ar']}: {info['address']}", f"🕘 {info['hours']}"]
    if info.get("phone"):
        lines.append(f"📞 {info['phone']}")
    lines.append(f"🗺️ {info['maps']}")
    if info.get("services"):
        lines.append("الخدمات: " + "، ".join(info["services"]))
    return "\n".join(lines)
