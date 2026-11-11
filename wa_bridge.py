# wa_bridge.py
# ============================================================
#  📲 زرار واتساب «بضغطة واحدة»: بيفتح محادثة العميل وفي نفس اللحظة بيبلّغ البرنامج إن الرسالة
#  اتبعتت (فيتسجّل الإرسال + المتابعة من غير زرار تاني).
#
#  إزاي: نفس طريقة زرار المايك (voice.py) — الـ iframe بتاع components.html بيكتب «توكن» في خانة
#  نص صغيرة في الصفحة (aria-label ثابت) ويعمل input+blur، فـ Streamlit يعمل rerun والصفحة تسجّل.
#  لو ده ماشتغلش لأي سبب (متصفح قديم)، اللينك نفسه بيفتح واتساب عادي، وفيه زرار يدوي احتياطي.
#  الجزء ده HTML بس — اللي بيتسجّل وإمتى في الصفحة نفسها (Invoice.py / Marketing Studio).
# ============================================================

from __future__ import annotations

import html
import json
from typing import Optional, Tuple

BRIDGE_ARIA = "wa-send-bridge"

# CSS: خانة الجسر موجودة (لازم عشان focus/blur يشتغلوا) بس مش باينة
BRIDGE_CSS = f"""
<style>
div[data-testid="stTextInput"]:has(input[aria-label="{BRIDGE_ARIA}"]) {{
  height:1px !important; min-height:0 !important; overflow:hidden !important; opacity:0 !important;
  margin:0 !important; padding:0 !important;
}}
</style>
"""

_HTML = """
<div style="font-family:sans-serif;direction:rtl">
<a id="go" href="__URL__" target="_blank" rel="noopener"
   style="display:block;text-decoration:none;background:__BG__;color:#fff;text-align:center;
          padding:11px 8px;border-radius:8px;font-weight:700;font-size:1rem;line-height:1.3">__LABEL__</a>
<div id="st" style="margin-top:.3rem;font-size:.8rem;color:#555;text-align:center">__HINT__</div>
</div>
<script>
const go = document.getElementById('go'), st = document.getElementById('st');
go.addEventListener('click', () => {
  try {
    const P = window.parent;
    const inp = P.document.querySelector('input[aria-label="__ARIA__"]');
    if (!inp) { st.textContent = __FAIL__; return; }
    inp.focus();
    const setter = Object.getOwnPropertyDescriptor(P.HTMLInputElement.prototype, 'value').set;
    setter.call(inp, __TOKEN__);
    inp.dispatchEvent(new P.Event('input', { bubbles: true }));
    inp.blur();
    st.textContent = __OK__;
  } catch (e) { st.textContent = __FAIL__; }
});
</script>
"""


def send_button_html(url: str, label: str, token: str, *, aria: str = BRIDGE_ARIA,
                     hint: str = "", ok_text: str = "✔ اتفتح واتساب — بيتسجّل الإرسال والمتابعة…",
                     fail_text: str = "اتفتح واتساب — سجّل الإرسال بالزرار اللي تحت", bg: str = "#25D366") -> str:
    """HTML لـ components.html(…, height≈80): لينك واتساب + كتابة token في خانة الجسر."""
    return (_HTML.replace("__URL__", html.escape(url, quote=True))
            .replace("__LABEL__", html.escape(label))
            .replace("__HINT__", html.escape(hint))
            .replace("__BG__", bg)
            .replace("__ARIA__", aria)
            .replace("__TOKEN__", json.dumps(token))
            .replace("__OK__", json.dumps(ok_text))
            .replace("__FAIL__", json.dumps(fail_text)))


def make_token(kind: str, ref: str) -> str:
    """kind = sent (عرض سعر) | camp (إعلان الاستوديو) — ref = كود العرض/الحملة."""
    return f"{kind}:{ref}"


def parse_token(value: str) -> Optional[Tuple[str, str]]:
    v = (value or "").strip()
    kind, sep, ref = v.partition(":")
    if not sep or kind not in ("sent", "camp") or not ref or len(ref) > 40:
        return None
    return kind, ref
