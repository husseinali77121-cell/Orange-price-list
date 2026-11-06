# share_widget.py
# ============================================================
#  📲 زرار «شارك الصورة نفسها» (Web Share API) — مشترك بين Marketing Studio
#  والفاتورة. بيبعت الصورة كملف مع النص من قايمة المشاركة بتاعة الموبايل
#  (واتساب / فيسبوك / إنستجرام…). لينكات wa.me بتاخد نص بس — ده الطريق الوحيد
#  لإرفاق صورة من المتصفح. لو المتصفح مش بيدعمه: حمّل الصورة، أو اضغط مطوّلاً عليها.
# ============================================================

from __future__ import annotations

import base64
import json


def share_button_html(jpg_bytes: bytes, text: str, filename: str,
                      label: str = "📲 شارك الصورة نفسها (واتساب / فيسبوك / إنستجرام)") -> str:
    b64 = base64.b64encode(jpg_bytes).decode("ascii")
    safe_text = json.dumps(text or "", ensure_ascii=False).replace("</", "<\\/")
    safe_name = json.dumps((filename or "orange.jpg").replace("\\", "").replace('"', ""))
    safe_label = (label or "").replace("<", "&lt;")
    return f"""
<button id="sh" style="width:100%;padding:12px;border:0;border-radius:10px;
 background:#E96D23;color:#fff;font-size:16px;font-weight:700;cursor:pointer">{safe_label}</button>
<div id="msg" style="font:13px sans-serif;color:#b26a00;margin-top:6px;direction:rtl"></div>
<script>
const B64 = "{b64}";
const TEXT = {safe_text};
const NAME = {safe_name};
const msg = t => document.getElementById('msg').textContent = t;
document.getElementById('sh').onclick = async () => {{
  try {{
    const bin = atob(B64), arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const file = new File([arr], NAME, {{type: "image/jpeg"}});
    if (navigator.canShare && navigator.canShare({{files: [file]}})) {{
      await navigator.share({{files: [file], text: TEXT}});
    }} else {{
      msg("المتصفح ده مش بيدعم مشاركة الصور — اضغط مطوّلاً على الصورة ← مشاركة، أو حمّلها.");
    }}
  }} catch (e) {{
    if (e.name !== "AbortError") msg("المشاركة مش متاحة هنا — اضغط مطوّلاً على الصورة ← مشاركة، أو حمّلها.");
  }}
}};
</script>
"""
