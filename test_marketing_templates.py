#!/usr/bin/env python3
"""
اختبار Marketing Studio (محرك القوالب + نص المنشور + صفحة Streamlit بـ stub):
    python3 test_marketing_templates.py
مفيهوش شبكة، ومش محتاج streamlit متثبّت (الصفحة بتتشغّل على نسخة وهمية).
"""
import io
import json
import os
import random
import runpy
import sys
import types
from datetime import datetime

from PIL import Image

import marketing_templates as mt
from bundles import BUNDLES
from tracking import EVENT_TYPES, make_event, summarize_events

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:62} got={got}")
    if not ok:
        fails.append((label, got, want))


# ------------------------------------------------------------
# 1) الأصول والخطوط
# ------------------------------------------------------------
for a in ("logo.png", "social_icons.png", "tagline.png", "icon_quality.png",
          "icon_speed.png", "icon_care.png", "photos/sugar.jpg",
          "photos/hair.jpg", "photos/sun.jpg"):
    check(f"asset exists: {a}", os.path.exists(os.path.join(mt.ASSETS, a)), True)
check("arabic font found", mt.find_font_path(True) is not None, True)

# ------------------------------------------------------------
# 2) كل قالب × كل مقاس = الأبعاد الصح
# ------------------------------------------------------------
for key, p in mt.PRESETS.items():
    for size, (w, h) in mt.SIZES.items():
        img = mt.render_template(p["template"], size, p)
        check(f"{key} @ {size} dims", img.size, (w, h))

# الصورة مش فاضية/سودا بالكامل
img = mt.render_template("offer", "post", mt.PRESETS["sugar_offer"])
avg = img.resize((1, 1)).getpixel((0, 0))
check("offer is not blank (avg brightness)", sum(avg) / 3 > 25, True)
check("png bytes decode", Image.open(io.BytesIO(mt.to_png_bytes(img))).size, (1080, 1080))
check("jpeg smaller than png", len(mt.to_jpeg_bytes(img)) < len(mt.to_png_bytes(img)), True)

# ------------------------------------------------------------
# 3) حالات حدّية: نص فاضي / طويل جداً / صورة مرفوعة / بدون صورة / بدون شارة
# ------------------------------------------------------------
for size in mt.SIZES:
    mt.render_template("offer", size, {})
    mt.render_template("awareness", size, {})
    mt.render_template("tip", size, {})
check("empty fields render everywhere", True, True)

long_items = "\n".join(f"تحليل رقم {i} بإسم طويل جداً جداً جداً (Long Name {i})" for i in range(20))
img = mt.render_template("offer", "post", {**mt.PRESETS["sugar_offer"], "items": long_items,
                                           "title_big": "الغدة الدرقية والهرمونات الكاملة",
                                           "subtitle": "نص طويل " * 30})
check("overlong text still renders", img.size, (1080, 1080))

up = io.BytesIO()
Image.new("RGB", (3000, 2000), (30, 90, 160)).save(up, "JPEG")
img = mt.render_template("awareness", "story", {**mt.PRESETS["hair_awareness"], "photo": up.getvalue()})
check("uploaded jpeg accepted (3000x2000)", img.size, (1080, 1920))
img = mt.render_template("tip", "post", {**mt.PRESETS["sun_tip"], "photo": None})
check("no photo -> fallback", img.size, (1080, 1080))
img = mt.render_template("offer", "post", {**mt.PRESETS["sugar_offer"], "badge_mode": "none"})
check("badge none", img.size, (1080, 1080))
img = mt.render_template("offer", "post", {
    **mt.PRESETS["sugar_offer"], "badge_mode": "price", "badge_top": "بسعر",
    "badge_value": "700", "old_price": "950", "badge_pill": "Lipid Profile",
    "valid_until": "ساري حتى 30 نوفمبر"})
check("price badge with old price + validity", img.size, (1080, 1080))

try:
    mt.render_template("nope", "post", {})
    check("unknown template raises", False, True)
except ValueError:
    check("unknown template raises", True, True)
try:
    mt.render_template("offer", "huge", {})
    check("unknown size raises", False, True)
except ValueError:
    check("unknown size raises", True, True)

bomb = io.BytesIO()
Image.new("L", (9000, 9000)).save(bomb, "PNG")
try:
    mt.load_photo(bomb.getvalue())
    check("huge image rejected", False, True)
except ValueError:
    check("huge image rejected", True, True)

# ------------------------------------------------------------
# 4) مسار العربي بدون raqm (زي سيرفر من غير fribidi)
# ------------------------------------------------------------
saved = mt.RAQM
mt.RAQM = False
mt._font_cache.clear()
try:
    img = mt.render_template("offer", "post", mt.PRESETS["sugar_offer"])
    check("renders without raqm (arabic_pdf fallback)", img.size, (1080, 1080))
finally:
    mt.RAQM = saved
    mt._font_cache.clear()

# ------------------------------------------------------------
# 4b) خطوط من غير أشكال الحروف المتّصلة (زي Cairo بدون raqm) = الحروف بتطير
# ------------------------------------------------------------
import shutil
import tempfile

LIB = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
DJV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Fonts", "DejaVuSans-Bold.ttf")
check("bundled DejaVu is in Fonts/ (guaranteed on any server)", os.path.exists(DJV), True)
check("DejaVu covers presentation forms", mt.font_has_presentation_forms(DJV), True)
if os.path.exists(LIB):
    check("Latin-only font does NOT cover presentation forms", mt.font_has_presentation_forms(LIB), False)
    tmp = tempfile.mkdtemp()
    shutil.copy(LIB, os.path.join(tmp, "Cairo-Bold.ttf"))      # Cairo "مزيّف" ناقص الأشكال
    saved = (mt._FONT_DIRS, mt._font_index, mt.RAQM)
    try:
        mt._FONT_DIRS = [tmp] + list(saved[0])
        mt._font_index = None
        mt._font_cache.clear()
        mt.RAQM = False
        check("no raqm: Cairo-like font w/o forms is skipped -> DejaVu", mt.active_font_name(True), "DejaVuSans-Bold.ttf")
        check("font_status reports skipped font + fallback mode",
              (mt.font_status()["mode"], mt.font_status()["skipped"]), ("fallback", ["Cairo-Bold.ttf"]))
        mt.RAQM = True
        mt._font_cache.clear()
        check("with raqm: preferred font is used", mt.active_font_name(True), "Cairo-Bold.ttf")
        check("with raqm: nothing skipped", mt.font_status()["skipped"], [])
    finally:
        mt._FONT_DIRS, mt._font_index, mt.RAQM = saved
        mt._font_cache.clear()
        shutil.rmtree(tmp, ignore_errors=True)


def _ink_profile(text, raqm, bins=80):
    """بصمة الحبر على المحور الأفقي — عشان نكشف لو النص اتعكس."""
    from PIL import ImageDraw
    mt.RAQM = raqm
    mt._font_cache.clear()
    im = Image.new("L", (900, 130), 0)
    mt.put(ImageDraw.Draw(im), (880, 20), text, mt.get_font(60, True), 255, "ra")
    mt.RAQM = saved_raqm
    mt._font_cache.clear()
    bb = im.getbbox()
    im = im.crop(bb)
    return list(im.resize((bins, 1), Image.BOX).getdata()), im.width


def _corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0


saved_raqm = mt.RAQM
for word in ["الدهون", "دقة عالية", "احجز تحاليلك الآن", "رعاية متكاملة"]:
    a, wa = _ink_profile(word, True)
    b, wb = _ink_profile(word, False)
    same, flipped = _corr(a, b), _corr(a, b[::-1])
    check(f"fallback not mirrored vs raqm: '{word}'", same > flipped, True)
    check(f"fallback width within 8% of raqm: '{word}'", abs(wa - wb) / wa < 0.08, True)
mt.RAQM = saved_raqm

# ------------------------------------------------------------
# 5) parse_rich
# ------------------------------------------------------------
check("parse_rich marks [[ ]]", mt.parse_rich("بسبب [[نقص الحديد]] اليوم"),
      [("بسبب", False), ("نقص", True), ("الحديد", True), ("اليوم", False)])
check("parse_rich plain", mt.parse_rich("a b"), [("a", False), ("b", False)])
check("parse_rich empty", mt.parse_rich(""), [])

# ------------------------------------------------------------
# 6) كود الحملة + نص المنشور
# ------------------------------------------------------------
cid = mt.make_campaign_id(datetime(2026, 11, 5), random.Random(1))
check("campaign id shape", cid.startswith("OL-261105-") and len(cid) == 14, True)
check("campaign ids differ", mt.make_campaign_id() != mt.make_campaign_id(), True)

cap = mt.build_caption("offer", mt.PRESETS["sugar_offer"], lab="معمل", phone="+20 1",
                       maps_url="https://m", campaign_id=cid, include_code=True)
check("caption has discount line", "خصم 20%" in cap, True)
check("caption lists components", "✅ سكر صائم (FBS)" in cap, True)
check("caption has phone + maps + code", all(x in cap for x in ("+20 1", "https://m", cid)), True)
cap2 = mt.build_caption("offer", mt.PRESETS["sugar_offer"], lab="معمل", campaign_id=cid)
check("caption hides code by default", cid not in cap2, True)
cap3 = mt.build_caption("awareness", mt.PRESETS["hair_awareness"], lab="معمل")
check("awareness caption strips [[ ]]", "[[" not in cap3 and "نقص الحديد" in cap3, True)
cap4 = mt.build_caption("offer", {"badge_mode": "price", "badge_value": "700",
                                  "old_price": "950", "title_big": "الدهون"}, lab="L")
check("price caption", "بسعر 700 ج.م بدلاً من 950 ج.م" in cap4, True)

# ------------------------------------------------------------
# 7) tracking: حدث campaign مايبوظش الإحصائيات
# ------------------------------------------------------------
check("campaign is an event type", "campaign" in EVENT_TYPES, True)
ev = make_event("campaign", quote_id=cid, branch="Diamond", note="x", meta={"size": "post"})
check("campaign event meta kept", ev.get("meta"), {"size": "post"})
q = make_event("quote", quote_id="Q1", total=700, items=["Lipid Profile"])
conv = make_event("converted", quote_id="Q1", total=700)
s = summarize_events([ev, q, conv])
check("campaign event ignored by summary", (s["quotes"], s["converted"], s["pending"]), (1, 1, 0))

# ------------------------------------------------------------
# 8) صفحة Streamlit على نسخة وهمية: لازم تتنفّذ كاملة من غير أخطاء
# ------------------------------------------------------------

class _Ctx:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self._st

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)


class FakeSt(types.ModuleType):
    def __init__(self, state=None):
        super().__init__("streamlit")
        self.session_state = dict(state or {})
        self.secrets = {}
        self.calls = []
        self.sidebar = _Ctx(self)

    # --- widgets: بترجّع القيمة المخزّنة أو أول اختيار
    def _val(self, key, default):
        return self.session_state.get(key, default) if key else default

    def radio(self, label, options, key=None, **kw):
        options = list(options)
        v = self._val(key, options[0])
        if key:
            self.session_state.setdefault(key, v)
        return v

    def selectbox(self, label, options, key=None, index=0, **kw):
        options = list(options)
        v = self._val(key, options[index] if (options and index is not None) else None)
        if key and key not in self.session_state:
            self.session_state[key] = v
        return v

    def text_input(self, label, key=None, value="", **kw):
        return self._val(key, value)

    text_area = text_input

    def toggle(self, label, key=None, value=False, **kw):
        return self._val(key, value)

    def file_uploader(self, *a, **k):
        return None

    def button(self, *a, **k):
        return False

    def download_button(self, label, data, **k):
        self.calls.append(("download", label, len(data)))
        return False

    def link_button(self, label, url, **k):
        self.calls.append(("link", label, url))
        return False

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx(self) for _ in range(n)]

    def expander(self, *a, **k):
        return _Ctx(self)

    def image(self, data, **k):
        self.calls.append(("image", len(data)))

    def stop(self):
        raise SystemExit

    def rerun(self):
        pass

    def cache_data(self, *a, **k):
        return lambda fn: fn

    cache_resource = cache_data

    def __getattr__(self, name):          # markdown, caption, warning, error, ...
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: self.calls.append((name, a[:1]))


def run_page(state=None):
    fake = FakeSt(state)
    comp = types.ModuleType("streamlit.components.v1")
    html_out = []
    comp.html = lambda h, **k: html_out.append(h)
    pkg = types.ModuleType("streamlit.components")
    pkg.v1 = comp
    fake.components = pkg
    saved_mods = {k: sys.modules.get(k) for k in
                  ("streamlit", "streamlit.components", "streamlit.components.v1")}
    sys.modules.update({"streamlit": fake, "streamlit.components": pkg,
                        "streamlit.components.v1": comp})
    try:
        g = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "pages", "2_Marketing_Studio.py"))
        fake.page_globals = g
    finally:
        for k, v in saved_mods.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return fake, html_out


fake, html_out = run_page()
labels = [c[1] for c in fake.calls if c[0] in ("download", "link")]
check("page runs end-to-end (default state)", any(c[0] == "image" for c in fake.calls), True)
check("page shows PNG + JPG download", sum(1 for c in fake.calls if c[0] == "download") >= 2, True)
check("page has WhatsApp + Facebook links", any("واتساب" in str(l) for l in labels)
      and any("فيسبوك" in str(l) for l in labels), True)
wa = next(c[2] for c in fake.calls if c[0] == "link" and "واتساب" in c[1])
check("whatsapp link carries the caption", wa.startswith("https://wa.me/?text="), True)
check("share component embeds image + caption", len(html_out) == 1 and "navigator.share" in html_out[0]
      and "const B64" in html_out[0], True)
check("no script-break in share html", html_out[0].count("</script>") == 1, True)

for tpl in ("awareness", "tip"):
    for size in mt.SIZES:
        p = mt.PRESETS["hair_awareness" if tpl == "awareness" else "sun_tip"]
        st_ = {"ms_template": tpl, "ms_size": size, "ms_photo_src": "sample",
               "ms_photo_sample": p["photo"], "ms_headline": p["headline"],
               "ms_body": p["body"]}
        fk, _ = run_page(st_)
        check(f"page renders {tpl}/{size}", any(c[0] == "image" for c in fk.calls), True)

# تعبئة من باقة حقيقية: السعر على الإعلان = سعر القائمة، والتوفير صح
for b in BUNDLES:
    fk, _ = run_page()
    fk.session_state["ms_bundle_pick"] = b["name"]
    fk.page_globals["fill_from_bundle"]("Orange (La Cité)")
    ss = fk.session_state
    rec = fk.page_globals["resolve_test"](b["name"], fk.page_globals["IDX"]).best
    retail, saving = fk.page_globals["bundle_saving"](rec, fk.page_globals["IDX"])
    check(f"autofill {b['name']}: price = price list", ss["ms_badge_value"], str(rec.price))
    check(f"autofill {b['name']}: items = components", ss["ms_items"].splitlines(), list(b["components"]))
    check(f"autofill {b['name']}: old price only when real saving",
          ss["ms_old_price"], str(retail) if saving > 0 else "")
    check(f"autofill {b['name']}: ref saving stored", ss["ms_ref_saving"], saving)
    img = mt.render_template("offer", "post", {k[3:]: v for k, v in ss.items()
                                               if k.startswith("ms_") and k[3:] in
                                               fk.page_globals["FIELD_KEYS"]})
    check(f"autofill {b['name']}: renders", img.size, (1080, 1080))

print("\n" + "=" * 74)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
