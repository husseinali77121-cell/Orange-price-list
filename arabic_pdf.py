# arabic_pdf.py
# ============================================================
#  دعم العربي في الـ PDF - من غير أي مكتبة جديدة
#
#  fpdf2 بيرسم الحروف زي ما هي: مش بيوصّلها ولا بيقلب الاتجاه.
#  فالملف ده بيعمل حاجتين قبل ما النص يروح للـ PDF:
#    1) shape  : يحوّل الحرف لشكله الصح (أول/وسط/آخر/منفصل)
#    2) reorder: يقلب الترتيب لليمين مع الحفاظ على الإنجليزي والأرقام
#
#  لو arabic_reshaper + python-bidi متثبتين بيستخدمهم (أدق)،
#  وإلا بيشتغل بالتنفيذ الداخلي. الاتنين اختياريين تماماً.
# ============================================================

import os
import re
import unicodedata

# ------------------------------------------------------------
# 1) جدول الأشكال: حرف -> (منفصل, آخر, أول, وسط)
#    None = الشكل ده مش موجود للحرف ده
# ------------------------------------------------------------

# حروف بتوصل من الناحيتين
_DUAL = {
    0x0626: (0xFE89, 0xFE8A, 0xFE8B, 0xFE8C),  # ئ
    0x0628: (0xFE8F, 0xFE90, 0xFE91, 0xFE92),  # ب
    0x062A: (0xFE95, 0xFE96, 0xFE97, 0xFE98),  # ت
    0x062B: (0xFE99, 0xFE9A, 0xFE9B, 0xFE9C),  # ث
    0x062C: (0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0),  # ج
    0x062D: (0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4),  # ح
    0x062E: (0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8),  # خ
    0x0633: (0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4),  # س
    0x0634: (0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8),  # ش
    0x0635: (0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC),  # ص
    0x0636: (0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0),  # ض
    0x0637: (0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4),  # ط
    0x0638: (0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8),  # ظ
    0x0639: (0xFEC9, 0xFECA, 0xFECB, 0xFECC),  # ع
    0x063A: (0xFECD, 0xFECE, 0xFECF, 0xFED0),  # غ
    0x0641: (0xFED1, 0xFED2, 0xFED3, 0xFED4),  # ف
    0x0642: (0xFED5, 0xFED6, 0xFED7, 0xFED8),  # ق
    0x0643: (0xFED9, 0xFEDA, 0xFEDB, 0xFEDC),  # ك
    0x0644: (0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0),  # ل
    0x0645: (0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4),  # م
    0x0646: (0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8),  # ن
    0x0647: (0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC),  # ه
    0x064A: (0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4),  # ي
    0x0649: (0xFEEF, 0xFEF0, 0xFBE8, 0xFBE9),  # ى
    0x06CC: (0xFBFC, 0xFBFD, 0xFBFE, 0xFBFF),  # ی (فارسي)
    0x067E: (0xFB56, 0xFB57, 0xFB58, 0xFB59),  # پ
    0x0686: (0xFB7A, 0xFB7B, 0xFB7C, 0xFB7D),  # چ
    0x06A4: (0xFB6A, 0xFB6B, 0xFB6C, 0xFB6D),  # ڤ
    0x06AF: (0xFB92, 0xFB93, 0xFB94, 0xFB95),  # گ
}

# حروف بتوصل من اليمين بس (اللي بعدها ما بيوصلش بيها)
_RIGHT = {
    0x0622: (0xFE81, 0xFE82, None, None),      # آ
    0x0623: (0xFE83, 0xFE84, None, None),      # أ
    0x0624: (0xFE85, 0xFE86, None, None),      # ؤ
    0x0625: (0xFE87, 0xFE88, None, None),      # إ
    0x0627: (0xFE8D, 0xFE8E, None, None),      # ا
    0x0629: (0xFE93, 0xFE94, None, None),      # ة
    0x062F: (0xFEA9, 0xFEAA, None, None),      # د
    0x0630: (0xFEAB, 0xFEAC, None, None),      # ذ
    0x0631: (0xFEAD, 0xFEAE, None, None),      # ر
    0x0632: (0xFEAF, 0xFEB0, None, None),      # ز
    0x0648: (0xFEED, 0xFEEE, None, None),      # و
    0x0698: (0xFB8A, 0xFB8B, None, None),      # ژ
}

_FORMS = {**_DUAL, **_RIGHT}

# لام + ألف -> حرف واحد
_LAM_ALEF = {
    0x0622: (0xFEF5, 0xFEF6),
    0x0623: (0xFEF7, 0xFEF8),
    0x0625: (0xFEF9, 0xFEFA),
    0x0627: (0xFEFB, 0xFEFC),
}

_TASHKEEL = set(range(0x064B, 0x0653)) | {0x0640, 0x0670, 0x0653, 0x0654, 0x0655}
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFEFF]")

_ISOL, _FINA, _INIT, _MEDI = 0, 1, 2, 3


def has_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text or ""))


def _joins_right(cp: int) -> bool:
    """الحرف ده ممكن ياخد شكل آخر/وسط؟ (يعني بيوصل باللي قبله)"""
    return cp in _FORMS


def _joins_left(cp: int) -> bool:
    """الحرف ده ممكن يوصّل باللي بعده؟"""
    return cp in _DUAL


def shape_arabic(text: str) -> str:
    """بيحوّل الحروف العربية لأشكالها السياقية (Presentation Forms)."""
    if not text:
        return ""

    # التشكيل بيتشال - الخط مش بيركّبه صح في الـ PDF على أي حال
    chars = [c for c in text if ord(c) not in _TASHKEEL]

    out = []
    i = 0
    n = len(chars)
    while i < n:
        cp = ord(chars[i])

        # لام + ألف
        if cp == 0x0644 and i + 1 < n and ord(chars[i + 1]) in _LAM_ALEF:
            prev_cp = ord(chars[i - 1]) if i > 0 else None
            attached = prev_cp is not None and _joins_left(prev_cp)
            isol, fina = _LAM_ALEF[ord(chars[i + 1])]
            out.append(chr(fina if attached else isol))
            i += 2
            continue

        if cp not in _FORMS:
            out.append(chars[i])
            i += 1
            continue

        prev_cp = ord(chars[i - 1]) if i > 0 else None
        nxt_cp = ord(chars[i + 1]) if i + 1 < n else None

        prev_links = prev_cp is not None and _joins_left(prev_cp)
        next_links = nxt_cp is not None and _joins_right(nxt_cp)

        if prev_links and next_links and _joins_left(cp):
            form = _MEDI
        elif prev_links:
            form = _FINA
        elif next_links and _joins_left(cp):
            form = _INIT
        else:
            form = _ISOL

        glyph = _FORMS[cp][form] or _FORMS[cp][_ISOL]
        out.append(chr(glyph))
        i += 1

    return "".join(out)


# ------------------------------------------------------------
# 2) قلب الاتجاه - bidi مبسّط
# ------------------------------------------------------------

_MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{",
           "<": ">", ">": "<"}

_LTR_RUN = re.compile(r"[A-Za-z0-9\u0660-\u0669@._+\-/#%]+")


def rtl_reorder(text: str) -> str:
    """
    ترتيب بصري للنص العربي: يتقلب من اليمين، مع الحفاظ على
    مقاطع الإنجليزي والأرقام زي ما هي جوه.

    ده مش الخوارزمية الكاملة (UBA) - بس كفاية لأسماء العملاء
    والأطباء، وده الاستخدام الوحيد للعربي في الفاتورة.
    """
    if not text:
        return ""

    tokens, pos = [], 0
    for m in _LTR_RUN.finditer(text):
        if m.start() > pos:
            tokens.extend(("R", ch) for ch in text[pos:m.start()])
        tokens.append(("L", m.group()))
        pos = m.end()
    if pos < len(text):
        tokens.extend(("R", ch) for ch in text[pos:])

    out = []
    for kind, val in reversed(tokens):
        out.append(_MIRROR.get(val, val) if kind == "R" else val)
    return "".join(out)


def to_pdf_text(text: str) -> str:
    """shape + reorder. لو مفيش عربي بيرجّع النص زي ما هو."""
    if not text or not has_arabic(text):
        return text or ""
    try:                                    # المكتبات الجاهزة لو موجودة
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return rtl_reorder(shape_arabic(text))


# ------------------------------------------------------------
# 3) إيجاد خط يدعم يونيكود
# ------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))

FONT_CANDIDATES = [
    # 1) خط مرفوع مع المشروع - الأفضل: نفس الشكل في كل مكان
    os.path.join(_HERE, "fonts", "Amiri-Regular.ttf"),
    os.path.join(_HERE, "fonts", "NotoNaskhArabic-Regular.ttf"),
    os.path.join(_HERE, "fonts", "Cairo-Regular.ttf"),
    os.path.join(_HERE, "fonts", "DejaVuSans.ttf"),
    # 2) Streamlit Cloud / Debian / Ubuntu
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    # 3) Termux / Android
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/system/fonts/NotoNaskhArabic-Regular.ttf",
    "/system/fonts/DroidSansArabic.ttf",
    # 4) Windows / macOS
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def _local_ttfs(bold: bool = False):
    """
    أي .ttf مرفوع جوه مجلد الخطوط - بيدوّر على fonts و Fonts
    (لينكس case-sensitive، والمجلد في الريبو اسمه Fonts بحرف كبير).
    """
    found = []
    for folder in ("fonts", "Fonts", "FONTS"):
        d = os.path.join(_HERE, folder)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith((".ttf", ".otf")):
                continue
            is_bold = "bold" in f.lower()
            if is_bold == bool(bold):
                found.append(os.path.join(d, f))
    return found


def find_font(bold: bool = False):
    """بيرجّع مسار أول خط متاح يدعم يونيكود، أو None."""
    cands = _local_ttfs(bold) + list(FONT_CANDIDATES)
    if bold:
        bolds = []
        for p in cands:
            for a, b in ((".ttf", "-Bold.ttf"), ("Regular", "Bold")):
                if a in p:
                    bolds.append(p.replace(a, b))
        cands = bolds + cands
    for p in cands:
        if os.path.isfile(p):
            return p
    return None
