# marketing_templates.py
# ============================================================
#  Orange Lab — Marketing Studio (قوالب التصميم)
#  بيرسم صور إعلانية بهوية Orange من نص بسيط: بدون streamlit ولا شبكة
#  -> قابل للاختبار من الترمكس (test_marketing_templates.py)
#
#  القوالب (الثلاثة مأخوذة من تصميمات المعمل):
#    offer     عرض / خصم / باقة   (badge خصم % أو سعر + قائمة محتويات)
#    awareness توعية بصورة كاملة   (شرائط مائلة + عنوان + شرح)
#    tip       نصيحة طبية بشريط صورة مائل
#
#  المقاسات: post 1080x1080 · portrait 1080x1350 · story 1080x1920
#
#  النص العربي: لو Pillow معاه raqm+fribidi بيتشكّل تلقائي، وإلا بنستخدم
#  arabic_pdf (نفس تشكيل الـ PDF). الخط: Cairo/Tajawal لو حطّيتهم في
#  مجلد Fonts/، وإلا DejaVu Bold (شغّال بس شكله أبسط).
# ============================================================

from __future__ import annotations

import io
import os
import random
import re
import string
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, features

from arabic_pdf import has_arabic, to_pdf_text

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

# ------------------------------------------------------------
# الهوية
# ------------------------------------------------------------
ORANGE = (233, 109, 35)
ORANGE_DARK = (150, 58, 12)
BG = (12, 12, 12)
WHITE = (255, 255, 255)
GRAY = (205, 205, 205)

from brand import DEFAULT_PHONE  # noqa: E402  (رقم التواصل الافتراضي)

DEFAULT_TAGLINE_AR = "ببساطة في التحليل، دقة في النتائج"

SIZES: Dict[str, Tuple[int, int]] = {
    "post": (1080, 1080),
    "portrait": (1080, 1350),
    "story": (1080, 1920),
}
SIZE_LABELS = {
    "post": "منشور مربّع 1080×1080",
    "portrait": "Instagram / Facebook 1080×1350",
    "story": "Story / Reels 1080×1920",
}

TEMPLATES = {
    "offer": "🏷️ عرض / خصم / باقة",
    "awareness": "📢 توعية (صورة كاملة)",
    "tip": "💡 نصيحة طبية",
}

# صور جاهزة (مقصوصة من تصميمات المعمل) — الموظف يقدر يرفع صورته بدلها
SAMPLE_PHOTOS = {
    "sugar": ("🩸 سكر", "photos/sugar.jpg"),
    "hair": ("🥚 شعر", "photos/hair.jpg"),
    "sun": ("☀️ شمس", "photos/sun.jpg"),
}

# ------------------------------------------------------------
# الخطوط
# ------------------------------------------------------------
_BOLD_NAMES = ["Cairo-Black", "Cairo-Bold", "Tajawal-ExtraBold", "Tajawal-Bold",
               "Almarai-ExtraBold", "Almarai-Bold", "IBMPlexSansArabic-Bold",
               "NotoKufiArabic-Bold", "NotoSansArabic-Bold", "Amiri-Bold",
               "DejaVuSans-Bold"]
_REG_NAMES = ["Cairo-Regular", "Tajawal-Regular", "Almarai-Regular",
              "IBMPlexSansArabic-Regular", "NotoKufiArabic-Regular",
              "NotoSansArabic-Regular", "Amiri-Regular", "DejaVuSans"]
_FONT_DIRS = [os.path.join(HERE, d) for d in ("Fonts", "fonts", "assets/fonts")] + [
    "/usr/share/fonts", "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts"),
    "/system/fonts", "/data/data/com.termux/files/usr/share/fonts",
]

_font_index: Optional[Dict[str, str]] = None
_font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
RAQM = features.check("raqm")


def _scan_fonts() -> Dict[str, str]:
    global _font_index
    if _font_index is None:
        idx: Dict[str, str] = {}
        for d in _FONT_DIRS:
            if not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".ttf", ".otf")):
                        idx.setdefault(os.path.splitext(f)[0].lower(),
                                       os.path.join(root, f))
        _font_index = idx
    return _font_index


def find_font_path(bold: bool = True) -> Optional[str]:
    idx = _scan_fonts()
    for n in (_BOLD_NAMES if bold else _REG_NAMES):
        if n.lower() in idx:
            return idx[n.lower()]
    return None


def active_font_name(bold: bool = True) -> str:
    p = find_font_path(bold)
    return os.path.basename(p) if p else "(none)"


def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = find_font_path(bold) or find_font_path(not bold)
    if not path:
        raise RuntimeError("مفيش خط عربي — حط Cairo-Bold.ttf في مجلد Fonts/")
    key = (path, int(size))
    if key not in _font_cache:
        kw = {"layout_engine": ImageFont.Layout.RAQM} if RAQM else {}
        _font_cache[key] = ImageFont.truetype(path, int(size), **kw)
    return _font_cache[key]


# ------------------------------------------------------------
# كتابة النص (عربي/إنجليزي) — قياس ورسم
# ------------------------------------------------------------

def _prep(text: str) -> Tuple[str, dict]:
    if not has_arabic(text):
        return text, {}
    if RAQM:
        return text, {"direction": "rtl", "language": "ar"}
    return to_pdf_text(text), {}


def text_w(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    t, kw = _prep(text)
    return draw.textlength(t, font=font, **kw)


def put(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, anchor="ra"):
    t, kw = _prep(text)
    draw.text(xy, t, font=font, fill=fill, anchor=anchor, **kw)


_RICH_SPLIT = re.compile(r"(\[\[|\]\])")


def parse_rich(s: str) -> List[Tuple[str, bool]]:
    """'نص [[مهم]] عادي' -> [(كلمة, مميّزة?)] — [[ ]] بتلوّن الكلمات."""
    out, hl = [], False
    for part in _RICH_SPLIT.split(s or ""):
        if part == "[[":
            hl = True
        elif part == "]]":
            hl = False
        else:
            out.extend((w, hl) for w in part.split())
    return out


def _space(draw, font) -> float:
    return max(draw.textlength(" ", font=font), font.size * 0.25)


def wrap_words(draw, words: List[Tuple[str, bool]], font_n, font_h,
               max_w: float) -> List[List[Tuple[str, bool]]]:
    lines: List[List[Tuple[str, bool]]] = [[]]
    cur = 0.0
    for w, hl in words:
        f = font_h if hl else font_n
        ww = text_w(draw, w, f)
        sp = _space(draw, f)
        add = ww if not lines[-1] else ww + sp
        if lines[-1] and cur + add > max_w:
            lines.append([])
            cur = 0.0
            add = ww
        lines[-1].append((w, hl))
        cur += add
    return [ln for ln in lines if ln]


def line_width(draw, line, font_n, font_h) -> float:
    total = 0.0
    for i, (w, hl) in enumerate(line):
        f = font_h if hl else font_n
        total += text_w(draw, w, f) + (_space(draw, f) if i else 0)
    return total


def draw_line(draw, line, x, y, font_n, font_h, fill_n, fill_h, align="right"):
    """يرسم سطر كلمات من اليمين لليسار. x = الحافة (يمين/وسط/يسار حسب align)."""
    width = line_width(draw, line, font_n, font_h)
    if align == "right":
        cursor = x
    elif align == "center":
        cursor = x + width / 2
    else:
        cursor = x + width
    for w, hl in line:
        f = font_h if hl else font_n
        put(draw, (cursor, y), w, f, fill_h if hl else fill_n, "ra")
        cursor -= text_w(draw, w, f) + _space(draw, f)


def paragraph_height(n_lines: int, size: int, lead: float = 1.32) -> int:
    return int(n_lines * size * lead)


def _balance(draw, words, fn, fh, max_w: float, lines):
    """نفس عدد الأسطر بس بعرض أقل — عشان مايفضلش سطر أخير بكلمة واحدة."""
    n = len(lines)
    if n < 2:
        return lines
    lo, hi = max_w * 0.45, max_w
    best = lines
    for _ in range(12):
        mid = (lo + hi) / 2
        cand = wrap_words(draw, words, fn, fh, mid)
        if len(cand) <= n and all(line_width(draw, ln, fn, fh) <= mid + 1 for ln in cand):
            best, hi = cand, mid
        else:
            lo = mid
    return best


def fit_paragraph(draw, text: str, max_w: float, max_h: float, start: int,
                  min_size: int = 22, lead: float = 1.32, bold_all: bool = True,
                  max_lines: int = 9):
    """أكبر حجم خط يخلّي الفقرة تدخل في (max_w × max_h). بيرجّع (size, lines, fn, fh)."""
    words = parse_rich(text)
    size = start
    while True:
        fn = get_font(size, bold=bold_all)
        fh = get_font(size, bold=True)
        lines = wrap_words(draw, words, fn, fh, max_w)
        lines = _balance(draw, words, fn, fh, max_w, lines)
        h = paragraph_height(len(lines), size, lead)
        if (h <= max_h and len(lines) <= max_lines) or size <= min_size:
            return size, lines, fn, fh
        size -= 2


def draw_block(draw, lines, x, y, size, fn, fh, fill_n, fill_h, align="right",
               lead: float = 1.32) -> int:
    for ln in lines:
        draw_line(draw, ln, x, y, fn, fh, fill_n, fill_h, align)
        y += int(size * lead)
    return y


def fit_single(draw, text: str, max_w: float, start: int, min_size: int = 20,
               bold: bool = True):
    size = start
    while size > min_size:
        f = get_font(size, bold)
        if text_w(draw, text, f) <= max_w:
            break
        size -= 2
    return get_font(size, bold), size


# ------------------------------------------------------------
# أدوات رسم
# ------------------------------------------------------------

def _asset(name: str) -> Optional[Image.Image]:
    p = os.path.join(ASSETS, name)
    if os.path.exists(p):
        return Image.open(p).convert("RGBA")
    return None


def _paste_scaled(img: Image.Image, asset: Optional[Image.Image], x: int, y: int,
                  width: int, anchor: str = "l") -> Tuple[int, int]:
    """anchor l: x = الحافة اليسرى · r: x = الحافة اليمنى. بيرجّع (w, h)."""
    if asset is None:
        return 0, 0
    h = int(asset.height * width / asset.width)
    a = asset.resize((width, h), Image.LANCZOS)
    px = x if anchor == "l" else x - width
    img.paste(a, (px, y), a)
    return width, h


def dots(draw, x, y, cols, rows, gap, r, fill):
    for i in range(cols):
        for j in range(rows):
            cx, cy = x + i * gap, y + j * gap
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)


def cover(photo: Image.Image, w: int, h: int, focus=(0.5, 0.5)) -> Image.Image:
    """يملا (w×h) بالصورة من غير تشويه (قصّ من الحواف)."""
    photo = photo.convert("RGB")
    s = max(w / photo.width, h / photo.height)
    nw, nh = max(w, int(photo.width * s + 0.5)), max(h, int(photo.height * s + 0.5))
    p = photo.resize((nw, nh), Image.LANCZOS)
    if s > 1.25:                      # صورة صغيرة اتكبّرت: وضّحها شوية
        p = p.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    left = int((nw - w) * focus[0])
    top = int((nh - h) * focus[1])
    return p.crop((left, top, left + w, top + h))


def fallback_photo(w: int, h: int) -> Image.Image:
    """خلفية بديلة لو مفيش صورة: تدرّج برتقالي غامق + دوائر."""
    base = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(base, "RGBA")
    for i, a in enumerate((70, 55, 40, 28)):
        r = int(min(w, h) * (0.95 - i * 0.2))
        d.ellipse((w * 0.62 - r, h * 0.42 - r, w * 0.62 + r, h * 0.42 + r),
                  fill=ORANGE + (a,))
    return base


def load_photo(photo) -> Optional[Image.Image]:
    """photo: PIL.Image | bytes | مفتاح من SAMPLE_PHOTOS | None."""
    if photo is None or photo == "":
        return None
    if isinstance(photo, Image.Image):
        return photo
    if isinstance(photo, (bytes, bytearray)):
        im = Image.open(io.BytesIO(photo))
        if im.width * im.height > 60_000_000:
            raise ValueError("الصورة كبيرة قوي — صغّرها وجرّب تاني")
        im = ImageOps.exif_transpose(im)          # صور الموبايل بتيجي مقلوبة أحياناً
        im.thumbnail((3200, 3200))
        return im.convert("RGB")
    if isinstance(photo, str) and photo in SAMPLE_PHOTOS:
        p = os.path.join(ASSETS, SAMPLE_PHOTOS[photo][1])
        return Image.open(p) if os.path.exists(p) else None
    return None


def vgradient(w: int, h: int, top_alpha: int, bottom_alpha: int,
              color=BG) -> Image.Image:
    g = Image.new("RGBA", (w, h), color + (0,))
    px = g.load()
    for y in range(h):
        a = int(top_alpha + (bottom_alpha - top_alpha) * y / max(h - 1, 1))
        for x in range(w):
            px[x, y] = color + (a,)
    return g


def _safe_pads(H: int) -> Tuple[int, int]:
    """هوامش علوية/سفلية — الـ Story بتحتاج مساحة آمنة لواجهة التطبيق."""
    return (40, 40) if H < 1700 else (150, 190)


def draw_header(img: Image.Image, pad_top: int, phone: str,
                show_logo: bool = True) -> int:
    """لوجو يسار + (تليفون · أيقونات · ببساطة) يمين. بيرجّع y أسفل الهيدر."""
    W = img.width
    d = ImageDraw.Draw(img)
    bottom = pad_top
    if show_logo:
        _, lh = _paste_scaled(img, _asset("logo.png"), 40, pad_top + 8, 300, "l")
        bottom = max(bottom, pad_top + 8 + lh)
    rw = 186
    rx = W - 40
    y = pad_top
    if phone:
        f, _ = fit_single(d, phone, rw, 24)
        put(d, (rx, y), phone, f, ORANGE, "ra")
        y += 36
    _, ih = _paste_scaled(img, _asset("social_icons.png"), rx, y, rw, "r")
    y += ih + 8
    _, th = _paste_scaled(img, _asset("tagline.png"), rx, y, int(rw * 0.9), "r")
    bottom = max(bottom, y + th)
    return bottom


def _rounded_photo(img: Image.Image, photo: Optional[Image.Image], box,
                   radius_left: int, edge_orange: bool = True):
    """صورة بحافة يسار مقوّسة (زي تصميم السكر) — بتتمدّ لآخر الكانفاس يمين."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pic = cover(photo, w, h) if photo is not None else fallback_photo(w, h)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, w + radius_left, h), radius=radius_left,
                         fill=255, corners=(True, False, False, True))
    img.paste(pic, (x0, y0), mask)
    if edge_orange:
        d = ImageDraw.Draw(img)
        r = radius_left
        d.arc((x0 - 16, y0 - 16, x0 + 2 * r + 16, y0 + 2 * r + 16), 180, 270,
              fill=ORANGE, width=7)


# ------------------------------------------------------------
# القالب 1 — عرض / خصم / باقة
# ------------------------------------------------------------

def _draw_badge(img: Image.Image, cx: int, cy: int, dia: int, f: dict):
    d = ImageDraw.Draw(img)
    r = dia // 2
    d.ellipse((cx - r - 12, cy - r - 12, cx + r + 12, cy + r + 12), fill=BG)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ORANGE)
    d.ellipse((cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14),
              outline=(255, 150, 80), width=2)

    mode = f.get("badge_mode", "percent")
    top = (f.get("badge_top") or "").strip()
    val = (f.get("badge_value") or "").strip()
    sub = (f.get("badge_sub") or "").strip()
    pill = (f.get("badge_pill") or "").strip()
    old = (f.get("old_price") or "").strip()

    y = cy - r + int(dia * 0.115)
    if top:
        ft, _ = fit_single(d, top, dia * 0.34, int(dia * 0.105))
        tw = text_w(d, top, ft) + 40
        ph_ = int(dia * 0.15)
        d.rounded_rectangle((cx - tw / 2, y, cx + tw / 2, y + ph_), radius=ph_ // 2,
                            fill=WHITE)
        put(d, (cx, y + ph_ // 2), top, ft, BG, "mm")
        y += ph_ + int(dia * 0.03)

    unit, big = "", val
    if mode == "price" and val:
        unit = f.get("currency") or "ج.م"
    if val.endswith("%"):
        big, unit = val[:-1], "%"
    if val:
        fb, _ = fit_single(d, big, dia * 0.62 - (46 if unit else 0), int(dia * 0.29), 36)
        uf = get_font(max(int(fb.size * (0.5 if unit == "%" else 0.28)), 20))
        bw = text_w(d, big, fb)
        uw = text_w(d, unit, uf) if unit else 0
        total = bw + (uw + 8 if unit else 0)
        left = cx - total / 2
        put(d, (left + (uw + 8 if unit else 0) + bw, y), big, fb, WHITE, "ra")
        if unit:
            uy = y + (int(fb.size * 0.10) if unit == "%" else int(fb.size * 0.55))
            put(d, (left + uw, uy), unit, uf, WHITE, "ra")
        y += int(fb.size * 1.12)

    if mode == "price" and old:
        sf = get_font(int(dia * 0.082))
        lab = "بدلاً من"
        ow, lw = text_w(d, old, sf), text_w(d, lab, sf)
        x_r = cx + (ow + lw + 14) / 2
        put(d, (x_r, y), lab, sf, WHITE, "ra")
        ox = x_r - lw - 14
        put(d, (ox, y), old, sf, WHITE, "ra")
        d.line((ox - ow - 4, y + sf.size * 0.58, ox + 4, y + sf.size * 0.58),
               fill=(20, 20, 20), width=4)
    elif sub:
        sf, _ = fit_single(d, sub, dia * 0.60, int(dia * 0.085), 18)
        put(d, (cx, y), sub, sf, WHITE, "ma")

    if pill:
        pf, _ = fit_single(d, pill, dia * 0.62 - 30, int(dia * 0.088), 18)
        ph = int(pf.size * 1.65)
        pw = min(text_w(d, pill, pf) + 36, dia * 0.74)
        py = cy + r - int(dia * 0.075) - ph
        d.rounded_rectangle((cx - pw / 2, py, cx + pw / 2, py + ph), radius=ph // 2,
                            fill=(14, 14, 14))
        put(d, (cx, py + ph // 2), pill, pf, WHITE, "mm")


def render_offer(W: int, H: int, f: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    pad_top, pad_bot = _safe_pads(H)
    hdr_bottom = draw_header(img, pad_top, f.get("phone", DEFAULT_PHONE))

    k = 1.0 if H < 1200 else (1.2 if H < 1700 else 1.5)   # تكبير العناصر في المقاسات الطولية
    col_r, col_l = 438, 58            # عمود النص
    col_w = col_r - col_l
    foot_h = 230
    foot_top = H - pad_bot - foot_h

    _rounded_photo(img, load_photo(f.get("photo")),
                   (505, hdr_bottom + 66, W, foot_top + 150), radius_left=230)
    dots(d, 14, hdr_bottom + 120, 2, 5, 24, 5, ORANGE_DARK)

    y = hdr_bottom + 44
    small = (f.get("title_small") or "").strip()
    big = (f.get("title_big") or "").strip()
    if small:
        fs, _ = fit_single(d, small, col_w, int(50 * k))
        put(d, (col_r, y), small, fs, WHITE, "ra")
        y += int(fs.size * 1.3)
    if big:
        fb, _ = fit_single(d, big, col_w, int(124 * k), 46)
        put(d, (col_r, y), big, fb, ORANGE, "ra")
        y += int(fb.size * 1.3)
    sub = (f.get("subtitle") or "").strip()
    if sub:
        size, lines, fn, fh = fit_paragraph(d, sub, col_w, int(110 * k), int(34 * k), 22, 1.3,
                                            bold_all=False)
        y = draw_block(d, lines, col_r, y, size, fn, fh, WHITE, ORANGE, "right", 1.3)
    d.rectangle((col_r - 230, y + 6, col_r, y + 10), fill=ORANGE)
    y += 28

    # القائمة: بتاخد المساحة اللي فاضلة فوق الفوتر وتصغّر الصفوف لو كتير
    items = [s.strip() for s in (f.get("items") or "").splitlines() if s.strip()][:8]
    if items:
        title_h, gap = int(58 * k), int(8 * k)
        avail = foot_top - 6 - y - title_h - 16
        row_h = max(34, min(int(50 * k), int(avail / len(items)) - gap))
        used = title_h + 16 + len(items) * (row_h + gap)
        y += max(0, (foot_top - 6 - y - used) // 2)      # القائمة في نص المساحة الفاضية
        title = (f.get("list_title") or "الباقة تشمل").strip()
        tf, _ = fit_single(d, title, col_w - 110, int(30 * k))
        pw = text_w(d, title, tf) + 110
        d.rounded_rectangle((col_r - pw, y, col_r, y + title_h), radius=title_h // 2, fill=ORANGE)
        put(d, (col_r - 24, y + title_h // 2), title, tf, WHITE, "rm")
        y += title_h + 16
        for it in items:
            d.rounded_rectangle((col_l, y, col_r, y + row_h), radius=14, fill=(28, 28, 28))
            d.ellipse((col_r - 32, y + row_h / 2 - 7, col_r - 18, y + row_h / 2 + 7), fill=ORANGE)
            itf, _ = fit_single(d, it, col_w - 80, int(24 * k), 14, bold=False)
            put(d, (col_r - 48, y + row_h / 2), it, itf, WHITE, "rm")
            y += row_h + gap

    if f.get("badge_mode", "percent") != "none":
        _draw_badge(img, 622, hdr_bottom + 250, 300, f)

    # الفوتر: مزايا (يسار) + CTA (يمين)
    fy = foot_top + 40
    if f.get("show_trust", True):
        cols = [("icon_quality.png", "دقة عالية", "نتائج موثوقة"),
                ("icon_speed.png", "نتائج سريعة", "في أسرع وقت"),
                ("icon_care.png", "رعاية متكاملة", "نهتم بصحتك")]
        cw = (col_r - col_l) / 3
        for i, (ic, t1, t2) in enumerate(cols):
            cx = col_r - i * cw - cw / 2
            icon = _asset(ic)
            if icon:
                iw = 40
                ih = int(icon.height * iw / icon.width)
                a = icon.resize((iw, ih), Image.LANCZOS)
                img.paste(a, (int(cx - iw / 2), fy), a)
            f1, _ = fit_single(d, t1, cw - 10, 20, 12)
            f2, _ = fit_single(d, t2, cw - 10, 16, 11, bold=False)
            put(d, (cx, fy + 52), t1, f1, ORANGE, "ma")
            put(d, (cx, fy + 82), t2, f2, WHITE, "ma")
            if i < 2:
                d.line((cx - cw / 2, fy + 6, cx - cw / 2, fy + 104), fill=(60, 60, 60), width=2)

    cta = (f.get("cta") or "").strip()
    tag_y = H - pad_bot - 30
    if cta:
        cf, _ = fit_single(d, cta, 280, 32)
        cw_ = min(max(text_w(d, cta, cf) + 110, 280), 440)
        cx1, cx0 = W - 36, W - 36 - cw_
        cy0 = H - pad_bot - 128
        d.rounded_rectangle((cx0, cy0, cx1, cy0 + 72), radius=36, fill=ORANGE)
        d.ellipse((cx1 - 62, cy0 + 8, cx1 - 8, cy0 + 64), fill=WHITE)
        d.rounded_rectangle((cx1 - 48, cy0 + 20, cx1 - 22, cy0 + 48), radius=5, outline=ORANGE, width=3)
        d.line((cx1 - 48, cy0 + 28, cx1 - 22, cy0 + 28), fill=ORANGE, width=3)
        put(d, (cx1 - 76, cy0 + 36), cta, cf, WHITE, "rm")
        valid = (f.get("valid_until") or "").strip()
        if valid:
            vf, _ = fit_single(d, valid, 400, 26, 16)
            vw = text_w(d, valid, vf) + 36
            d.rounded_rectangle((W - 36 - vw, cy0 - 12 - vf.size - 18, W - 36, cy0 - 12),
                                radius=(vf.size + 18) // 2, fill=BG)
            put(d, (W - 36 - vw / 2, cy0 - 12 - (vf.size + 18) / 2), valid, vf, WHITE, "mm")
    else:
        valid = (f.get("valid_until") or "").strip()
        if valid:
            vf, _ = fit_single(d, valid, 430, 26, 16)
            put(d, (W - 40, tag_y - 44), valid, vf, WHITE, "rb")
    line = parse_rich("[[ببساطة]] في التحليل، دقة في النتائج")
    draw_line(d, line, W - 40, tag_y, get_font(24, False), get_font(24, True), WHITE, ORANGE)
    return img


# ------------------------------------------------------------
# القالب 2 — توعية بصورة كاملة + شرائط مائلة
# ------------------------------------------------------------

def _poly_layer(W, H, pts, rgba):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(pts, fill=rgba)
    return layer


def _watermark(img: Image.Image, text: str, x: int, y: int, size: int, alpha: int,
               rotate: int = 90):
    d0 = ImageDraw.Draw(img)
    f = get_font(size)
    w = int(d0.textlength(text, font=f)) + 20
    layer = Image.new("RGBA", (w, size + 40), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((10, 5), text, font=f, fill=ORANGE + (alpha,))
    layer = layer.rotate(rotate, expand=True)
    img.paste(layer, (x, y), layer)


def render_awareness(W: int, H: int, f: dict) -> Image.Image:
    pad_top, pad_bot = _safe_pads(H)
    photo = load_photo(f.get("photo"))
    # الصورة بتغطّي الجزء الشمال بس (الباقي لوحة سودا) — أقل تكبير = أوضح
    pw = int(W * 0.76)
    img = Image.new("RGBA", (W, H), BG + (255,))
    pic = cover(photo, pw, H, focus=(0.5, 0.4)) if photo is not None else fallback_photo(pw, H)
    img.paste(pic.convert("RGBA"), (0, 0))

    dx = int(0.14 * H)
    def band(x0, x1, rgba):
        return _poly_layer(W, H, [(x0, 0), (x1, 0), (x1 - dx, H), (x0 - dx, H)], rgba)
    a, b, c, e = int(.50 * W), int(.575 * W), int(.665 * W), int(.705 * W)
    img = Image.alpha_composite(img, band(a, b, ORANGE + (175,)))
    img = Image.alpha_composite(img, band(b, c, (140, 58, 14, 235)))
    img = Image.alpha_composite(img, band(c, e, (104, 44, 14, 245)))
    img = Image.alpha_composite(img, _poly_layer(
        W, H, [(e, 0), (W, 0), (W, H), (e - dx, H)], BG + (255,)))
    # تعتيم تحت للنص + فوق للهيدر
    gh = int(H * 0.46)
    g = vgradient(W, gh, 0, 235)
    img.paste(g, (0, H - gh), g)
    gt = vgradient(W, 230, 150, 0)
    img.paste(gt, (0, 0), gt)
    img = img.convert("RGB")

    _watermark(img, "orange", int(W * 0.86), int(H * 0.12), 190, 26)
    draw_header(img, pad_top, f.get("phone", DEFAULT_PHONE))
    d = ImageDraw.Draw(img)

    right = W - 96
    width = W - 150
    bottom = H - pad_bot - 30
    body = (f.get("body") or "").strip()
    head = (f.get("headline") or "").strip()
    max_block = int(H * 0.36)
    hs, hlines, hfn, hfh = fit_paragraph(d, head, width, max_block * 0.5, 104, 40, 1.18)
    h_h = paragraph_height(len(hlines), hs, 1.18)
    bs, blines, bfn, bfh = fit_paragraph(d, body, width, max_block - h_h, 46, 26, 1.42,
                                         bold_all=False) if body else (0, [], None, None)
    b_h = paragraph_height(len(blines), bs, 1.42) if body else 0
    y = bottom - b_h - h_h
    y = draw_block(d, hlines, right, y, hs, hfn, hfh, WHITE, ORANGE, "right", 1.18)
    if body:
        draw_block(d, blines, right, y + 8, bs, bfn, bfh, GRAY, WHITE, "right", 1.42)
    return img


# ------------------------------------------------------------
# القالب 3 — نصيحة بشريط صورة مائل
# ------------------------------------------------------------

def render_tip(W: int, H: int, f: dict) -> Image.Image:
    img = Image.new("RGBA", (W, H), BG + (255,))
    pad_top, pad_bot = _safe_pads(H)
    hdr_bottom = draw_header(img, pad_top, f.get("phone", DEFAULT_PHONE))

    d_ = int(0.115 * W)                    # ميل الشريط
    y0 = max(hdr_bottom + 70, int(0.235 * H))
    thick = int(0.40 * H) if H < 1700 else int(0.36 * H)
    y1 = y0 + thick

    photo = load_photo(f.get("photo"))
    pic = cover(photo, W, thick + d_ + 4) if photo is not None else fallback_photo(W, thick + d_ + 4)
    mask = Image.new("L", (W, thick + d_ + 4), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (W, d_), (W, d_ + thick), (0, thick)], fill=255)
    # شريط برتقالي فوق الصورة + فاصل أسود
    ob = 46
    img = Image.alpha_composite(img, _poly_layer(
        W, H, [(0, y0 - ob - 16), (W, y0 - ob - 16 + d_), (W, y0 + d_ - 16), (0, y0 - 16)],
        ORANGE + (255,)))
    img.paste(pic.convert("RGBA"), (0, y0), mask)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)

    dots(d, 14, int(H * 0.60), 3, 3, 62, 11, (120, 120, 120))
    dots(d, W - 190, 6, 3, 1, 62, 11, (60, 40, 25))
    _watermark(img, "orange", 36, int(H * 0.80), 220, 14, rotate=0)

    text_top = y1 + d_ + 24
    right = W - 90
    width = W - 150
    max_h = H - pad_bot - text_top
    head = (f.get("headline") or "").strip()
    body = (f.get("body") or "").strip()
    hs, hlines, hfn, hfh = fit_paragraph(d, head, width, max_h * 0.42, 84, 38, 1.2)
    h_h = paragraph_height(len(hlines), hs, 1.2)
    bs, blines, bfn, bfh = fit_paragraph(d, body, width, max_h - h_h, 46, 24, 1.5,
                                         bold_all=False) if body else (0, [], None, None)
    y = draw_block(d, hlines, right, text_top, hs, hfn, hfh, ORANGE, WHITE, "right", 1.2)
    if body:
        draw_block(d, blines, right + 40, y + 4, bs, bfn, bfh, WHITE, ORANGE, "right", 1.5)
    return img


# ------------------------------------------------------------
# واجهة موحّدة
# ------------------------------------------------------------

_RENDERERS = {"offer": render_offer, "awareness": render_awareness, "tip": render_tip}


def render_template(kind: str, size: str, fields: dict) -> Image.Image:
    if kind not in _RENDERERS:
        raise ValueError(f"unknown template: {kind}")
    if size not in SIZES:
        raise ValueError(f"unknown size: {size}")
    W, H = SIZES[size]
    return _RENDERERS[kind](W, H, dict(fields or {})).convert("RGB")


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def to_jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------
# كود الحملة + نص المنشور
# ------------------------------------------------------------

def make_campaign_id(now: Optional[datetime] = None, rng=random) -> str:
    """OL-YYMMDD-XXXX — بيتحط في الحدث (وممكن في النص) لتتبّع النتيجة."""
    now = now or datetime.now()
    tail = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"OL-{now:%y%m%d}-{tail}"


def build_caption(kind: str, f: dict, *, lab: str, phone: str = "",
                  maps_url: str = "", campaign_id: str = "",
                  include_code: bool = False, currency: str = "ج.م") -> str:
    """نص منشور (فيسبوك/واتساب) جاهز للتعديل — بيتبني من نفس حقول التصميم."""
    lines: List[str] = []
    if kind == "offer":
        title = " ".join(x for x in [(f.get("title_small") or "").strip(),
                                     (f.get("title_big") or "").strip()] if x)
        lines.append(f"🍊 {title}" if title else f"🍊 عرض من {lab}")
        sub = " ".join((f.get("subtitle") or "").split())
        if sub:
            lines.append(sub)
        mode = f.get("badge_mode", "percent")
        val = (f.get("badge_value") or "").strip()
        if mode == "percent" and val:
            tgt = (f.get("badge_pill") or "").strip()
            lines.append(f"🏷️ خصم {val}" + (f" على {tgt}" if tgt else ""))
        elif mode == "price" and val:
            old = (f.get("old_price") or "").strip()
            lines.append(f"🏷️ بسعر {val} {currency}" + (f" بدلاً من {old} {currency}" if old else ""))
        items = [s.strip() for s in (f.get("items") or "").splitlines() if s.strip()]
        if items:
            lines.append("")
            lines.append((f.get("list_title") or "الباقة تشمل") + ":")
            lines.extend(f"✅ {it}" for it in items)
        valid = (f.get("valid_until") or "").strip()
        if valid:
            lines.append("")
            lines.append(f"⏰ {valid}")
    else:
        head = " ".join((f.get("headline") or "").replace("[[", "").replace("]]", "").split())
        body = " ".join((f.get("body") or "").replace("[[", "").replace("]]", "").split())
        lines.append(f"🍊 {head}" if head else f"🍊 {lab}")
        if body:
            lines.append(body)
    lines.append("")
    cta = "📍 للحجز والاستفسار"
    if phone:
        cta += f": {phone}"
    lines.append(cta)
    if maps_url:
        lines.append(f"🗺️ {maps_url}")
    lines.append(f"{lab} — ببساطة في التحليل، دقة في النتائج")
    if include_code and campaign_id:
        lines.append(f"كود العرض: {campaign_id}")
    return "\n".join(lines).strip()


# أمثلة جاهزة تفتح بيها الصفحة (وبتتستخدم في الاختبارات)
PRESETS: Dict[str, dict] = {
    "sugar_offer": {
        "template": "offer",
        "photo": "sugar",
        "title_small": "تحاليل",
        "title_big": "السكر",
        "subtitle": "شاملة ودقيقة لعناية أفضل بصحتك",
        "badge_mode": "percent",
        "badge_top": "خصم",
        "badge_value": "20%",
        "badge_sub": "على باقات",
        "badge_pill": "تحاليل السكر",
        "list_title": "الباقة تشمل",
        "items": "سكر صائم (FBS)\nسكر بعد الأكل بساعتين (PP)\nالسكر التراكمي (HbA1c)\nالأنسولين (Insulin)\nمقاومة الأنسولين (Insulin Resistance)",
        "cta": "احجز تحاليلك الآن",
        "show_trust": True,
    },
    "hair_awareness": {
        "template": "awareness",
        "photo": "hair",
        "headline": "تساقط الشعر بكثافة",
        "body": "بسبب [[نقص الحديد و البروتين]] وسوء الحالة النفسية\nالغذاء الصحى [[وقلة التوتر]] طريقك لشعر قوى وجذاب",
    },
    "sun_tip": {
        "template": "tip",
        "photo": "sun",
        "headline": "الكريمات الواقية من الشمس",
        "body": "يجب الا تحتوي علي اي كحوليات او مواد حافظة\nو توضع قبل التعرض للشمس ب ١٥ دقيقة علي الاقل",
    },
}
