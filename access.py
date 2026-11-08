# access.py
# ============================================================
#  🔒 بوابة كلمة سر خفيفة للصفحات الحسّاسة (Dashboard / المتابعة / العروض)
#  secrets: access_password = "..."  (أو dashboard_password للتوافق)
#  - متظبطة  -> الصفحة بتطلب كلمة السر قبل أي بيانات
#  - مش متظبطة -> بتعدّي، بس بتظهر تحذير إن الصفحة مفتوحة للكل
#  ده مش نظام صلاحيات (Roles) — كلمة سر واحدة للإدارة.
# ============================================================

from __future__ import annotations

import hmac
from typing import Callable, Optional

SECRET_KEYS = ("access_password", "dashboard_password")


def configured_password(secrets) -> str:
    try:
        for k in SECRET_KEYS:
            v = secrets.get(k, "")
            if v:
                return str(v)
    except Exception:
        pass
    return ""


def check_password(entered: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(str(entered or "").encode("utf-8"),
                                                 expected.encode("utf-8"))


def staff_password(secrets) -> str:
    try:
        return str(secrets.get("staff_password", "") or "")
    except Exception:
        return ""


def require_access(st, label: str = "الصفحة دي", level: str = "admin") -> None:
    """
    بتوقّف الصفحة (st.stop) لو كلمة السر متظبطة ومتدخلتش. تُستدعى بعد set_page_config.
      level="admin": كلمة سر الإدارة (access_password / dashboard_password)
      level="staff": كلمة سر الموظفين (staff_password) أو الإدارة — لو staff_password
                     مش متظبطة، كلمة سر الإدارة بتفتح كل حاجة زي الأول.
    من غير أي كلمة سر: الصفحة مفتوحة وبيظهر تحذير.
    """
    admin_pw, staff_pw = configured_password(st.secrets), staff_password(st.secrets)
    if not admin_pw and not staff_pw:
        st.warning(f"🔓 {label} مفتوحة لأي حد معاه اللينك — ضيف `access_password` "
                   "في Streamlit Secrets عشان تتحمي.")
        return
    admin_ok = bool(st.session_state.get("_access_ok"))
    staff_ok = bool(st.session_state.get("_staff_ok"))
    if admin_ok or (level == "staff" and staff_ok):
        return
    st.markdown("### 🔒 دخول")
    pw = st.text_input("كلمة السر", type="password", key="_access_pw")
    if pw:
        if admin_pw and check_password(pw, admin_pw):
            st.session_state["_access_ok"] = True
            st.rerun()
        elif level == "staff" and staff_pw and check_password(pw, staff_pw):
            st.session_state["_staff_ok"] = True
            st.rerun()
        elif staff_pw and check_password(pw, staff_pw):
            st.error("كلمة السر دي للموظفين — الصفحة دي للإدارة")
        else:
            st.error("كلمة السر غلط")
    st.stop()


def admin_gate(st, key: str = "_gate_pw", label: str = "🔐 للإدارة") -> bool:
    """
    بوابة داخل الصفحة (من غير ما توقّفها): True لو الإدارة مفتوحة. من غير كلمة سر
    متظبطة بترجّع True (زي بقية البوابات). بتُستخدم لموافقات الخصم وتعديل الإعدادات.
    """
    expected = configured_password(st.secrets)
    if not expected or st.session_state.get("_access_ok"):
        return True
    st.caption(label)
    pw = st.text_input("كلمة سر الإدارة", type="password", key=key)
    if pw and check_password(pw, expected):
        st.session_state["_access_ok"] = True
        st.rerun()
    elif pw:
        st.error("كلمة السر غلط")
    return False


def secret_bool(secrets, key: str, default: bool = False) -> bool:
    """قيمة منطقية من secrets (true/false/"true"/1) — بتتحمّل غياب ملف secrets كله."""
    try:
        v = secrets.get(key, default)
    except Exception:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def secret_float(secrets, key: str, default: float = 0.0) -> float:
    try:
        return float(secrets.get(key, default) or default)
    except Exception:
        return default


def secret_str(secrets, key: str, default: str = "") -> str:
    try:
        return str(secrets.get(key, default) or default)
    except Exception:
        return default
