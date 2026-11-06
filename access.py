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


def require_access(st, label: str = "الصفحة دي") -> None:
    """بتوقّف الصفحة (st.stop) لو كلمة السر متظبطة ومتدخلتش. تُستدعى بعد set_page_config."""
    expected = configured_password(st.secrets)
    if not expected:
        st.warning(f"🔓 {label} مفتوحة لأي حد معاه اللينك — ضيف `access_password` "
                   "في Streamlit Secrets عشان تتحمي.")
        return
    if st.session_state.get("_access_ok"):
        return
    st.markdown("### 🔒 دخول الإدارة")
    pw = st.text_input("كلمة السر", type="password", key="_access_pw")
    if pw:
        if check_password(pw, expected):
            st.session_state["_access_ok"] = True
            st.rerun()
        else:
            st.error("كلمة السر غلط")
    st.stop()


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
