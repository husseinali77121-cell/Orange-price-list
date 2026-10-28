# voice.py
# ============================================================
#  الأمر الصوتي — بدون streamlit (قابل للاختبار)
#
#  الفكرة: زرار مايك (Web Speech API في المتصفح) بيكتب النص المسموع في
#  خانة text_input في الصفحة، وبعدها Python بيعدّيه على نفس بوابة التحقق
#  بتاعة البحث العادي (resolve_test): المؤكد بيتضاف لوحده، والمشكوك فيه
#  بيستنى تأكيدك. مفيش تخمين — التعرّف الصوتي ممكن يغلط.
#
#  بيشتغل على Chrome (أندرويد/كمبيوتر) وبـ HTTPS. لو المتصفح مش بيدعمه
#  الخانة نفسها شغالة بالكتابة أو بمايك الكيبورد.
# ============================================================

import re

VOICE_ARIA = "voice command"      # aria-label للخانة اللي الـ JS بيكتب فيها

_FILLER = re.compile(r"^\s*(?:please\s+)?(?:add|insert|أضف|اضف|ضيف|عايز|عاوز)\s+",
                     re.IGNORECASE)
_SPLIT = re.compile(r"\s*(?:,|;|،|\+|&|\band\b|\bplus\b)\s*", re.IGNORECASE)
# "c b c" -> "cbc"  (المتعرّف الصوتي أحياناً بيفصل الحروف)
_SPELLED = re.compile(r"\b(?:[A-Za-z]\s+)+[A-Za-z]\b")


def split_voice_command(text: str) -> list:
    """جملة منطوقة -> أسماء تحاليل مرشّحة (من غير مطابقة ولا تخمين)."""
    s = _FILLER.sub("", (text or "").strip())
    out, seen = [], set()
    for part in _SPLIT.split(s):
        p = _SPELLED.sub(lambda m: m.group(0).replace(" ", ""), part)
        p = p.strip(" \t.:-–—?؟!\"'")
        if len(p) < 2 or p.lower() in seen:
            continue
        seen.add(p.lower())
        out.append(p)
    return out


_MIC_HTML = """
<div style="font-family:sans-serif;direction:rtl">
<button id="mic" style="width:100%;padding:.7rem;font-size:1rem;border-radius:8px;
 border:1px solid #f57c00;background:#fff3e0;color:#e65100;font-weight:700">
 🎤 اضغط وتكلّم</button>
<div id="st" style="margin-top:.4rem;font-size:.85rem;color:#555"></div></div>
<script>
const P = window.parent;
const SR = P.SpeechRecognition || P.webkitSpeechRecognition ||
           window.SpeechRecognition || window.webkitSpeechRecognition;
const btn = document.getElementById('mic'), st = document.getElementById('st');
if (!SR) {
  btn.disabled = true;
  st.textContent = 'المتصفح ده مش بيدعم الأمر الصوتي — استخدم Chrome أو اكتب في الخانة';
} else {
  const rec = new SR();
  rec.lang = '__LANG__'; rec.interimResults = false; rec.maxAlternatives = 1;
  let on = false;
  btn.onclick = () => { if (on) { rec.stop(); return; } try { rec.start(); } catch (e) {} };
  rec.onstart = () => { on = true; btn.textContent = '⏹ بسمعك... (اضغط للإيقاف)'; };
  rec.onend = () => { on = false; btn.textContent = '🎤 اضغط وتكلّم'; };
  rec.onerror = e => { st.textContent = 'تعذّر التسجيل: ' + e.error; };
  rec.onresult = e => {
    const text = e.results[0][0].transcript;
    const inp = P.document.querySelector('input[aria-label="__ARIA__"]');
    if (!inp) { st.textContent = 'مش لاقي خانة الصوت — افتح القسم تاني'; return; }
    inp.focus();
    const setter = Object.getOwnPropertyDescriptor(P.HTMLInputElement.prototype, 'value').set;
    setter.call(inp, text);
    inp.dispatchEvent(new P.Event('input', { bubbles: true }));
    inp.blur();
    st.textContent = 'سمعت: ' + text;
  };
}
</script>
"""


def mic_html(lang: str = "en-US", aria: str = VOICE_ARIA) -> str:
    """HTML للـ components.html — lang مثلاً en-US أو ar-EG."""
    return _MIC_HTML.replace("__LANG__", lang).replace("__ARIA__", aria)
