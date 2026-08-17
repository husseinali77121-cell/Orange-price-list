# pdf_invoice.py
# ============================================================
#  توليد فاتورة PDF - Orange Lab
#
#  ملاحظات مهمة عن fpdf2 (سبب باج "Not enough horizontal space"):
#    * multi_cell() الافتراضي بتاعه new_x=RIGHT -> بعد النداء الـ x
#      بيقف على يمين الخلية. لو ناديته تاني بـ w=0 من نفس المكان،
#      العرض المتاح بيبقى صفر أو سالب -> fpdf2 بيرمي FPDFException.
#    * عشان كده الملف ده مابيستخدمش multi_cell خالص. بنلف السطور
#      بنفسنا بـ get_string_width() وبنرسم كل سطر بـ cell() مع
#      set_xy() صريح. كل إحداثي متحدد يدوي = مافيش انزلاق.
# ============================================================

from io import BytesIO
from typing import List

from fpdf import FPDF

from arabic_pdf import find_font, has_arabic, to_pdf_text

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

# --- توافق مع كل إصدارات fpdf2 (ln اتشال في الإصدارات الجديدة) ---
try:
    from fpdf.enums import XPos, YPos
    NEWLINE = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}   # = ln=1
    SAMELINE = {"new_x": XPos.RIGHT, "new_y": YPos.TOP}     # = ln=0
except ImportError:                                          # fpdf2 قديم
    NEWLINE = {"ln": 1}
    SAMELINE = {"ln": 0}


# اسم العائلة المستخدم في الـ PDF: يونيكود لو لقينا خط، وإلا Helvetica
UNI_FONT = "OLUni"
_FONT_PATH = find_font()
_FONT_PATH_B = find_font(bold=True)

# أوزان الأعمدة (بتتقسم على العرض الفعلي للصفحة، مش أرقام ثابتة)
_COL_WEIGHTS = (12, 108, 28, 42)


def unicode_ready() -> bool:
    """هل الـ PDF يقدر يكتب عربي؟"""
    return _FONT_PATH is not None


def _safe(t) -> str:
    """
    تجهيز النص للطباعة.
    مع خط يونيكود: العربي بيتوصّل ويتقلب صح.
    من غيره: بيرجع للسلوك القديم (latin-1) عشان مايكسرش.
    """
    if t is None:
        return "N/A"
    t = str(t)
    if unicode_ready():
        return to_pdf_text(t)
    return t.encode("latin-1", errors="replace").decode("latin-1")


class ReceiptPDF(FPDF):
    def __init__(self, maps_url: str = ""):
        super().__init__()
        self.uni = False
        if unicode_ready():
            try:
                self.add_font(UNI_FONT, "", _FONT_PATH)
                self.add_font(UNI_FONT, "B", _FONT_PATH_B or _FONT_PATH)
                self.add_font(UNI_FONT, "I", _FONT_PATH)
                self.uni = True
            except Exception:
                self.uni = False

        # الـ QR كان جوه set_font بعد return - يعني كود ميت ومكانش بيشتغل أبداً
        self.qr_bytes = None
        if HAS_QR and maps_url:
            try:
                buf = BytesIO()
                qrcode.make(maps_url).save(buf, format="PNG")
                self.qr_bytes = buf.getvalue()
            except Exception:
                self.qr_bytes = None

    # ------------------------------------------------------------
    # الخط
    # ------------------------------------------------------------
    def set_font(self, family=None, style="", size=0):
        """
        أي نداء لـ Helvetica بيتحوّل للخط اليونيكود لو متاح -
        فمفيش سطر واحد في الفاتورة محتاج يتغيّر.
        """
        if self.uni and (family or "").lower() in ("helvetica", "arial", ""):
            family = UNI_FONT
            style = style.replace("I", "")     # مفيش مائل في الخط ده
        return super().set_font(family, style, size)

    # ------------------------------------------------------------
    # لف السطور يدوي - بديل multi_cell
    # ------------------------------------------------------------
    def _fit_word(self, word: str, max_w: float) -> List[str]:
        """كلمة أعرض من العمود -> بتتقطّع حروف. بترجّع دايماً قطعة واحدة على الأقل."""
        if self.get_string_width(word) <= max_w:
            return [word]
        pieces, cur = [], ""
        for ch in word:
            if cur and self.get_string_width(cur + ch) > max_w:
                pieces.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            pieces.append(cur)
        return pieces or [word[:1]]

    def wrap(self, text, max_w: float) -> List[str]:
        """بترجّع النص متقسّم لسطور تدخل في max_w. مابترميش استثناء أبداً."""
        max_w = max(float(max_w), 1.0)
        out: List[str] = []
        for para in str(text).split("\n"):
            cur = ""
            for word in para.split():
                for piece in self._fit_word(word, max_w):
                    trial = f"{cur} {piece}".strip()
                    if cur and self.get_string_width(trial) > max_w:
                        out.append(cur)
                        cur = piece
                    else:
                        cur = trial
            out.append(cur)
        return out or [""]

    def text_block(self, text, w: float, line_h: float, align: str = "L"):
        """بديل آمن لـ multi_cell: بيلف بنفسه وبيرجّع x للهامش بعد كل سطر."""
        avail = (w or self.epw) - 2 * self.c_margin
        for line in self.wrap(text, avail):
            self.set_x(self.l_margin)
            self.cell(w or 0, line_h, line, align=align, **NEWLINE)

    # ------------------------------------------------------------
    # Header / Footer
    # ------------------------------------------------------------
    def header(self):
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(214, 84, 26)
        self.cell(0, 9, "Orange Lab", align="C", **NEWLINE)
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, "Medical Test Invoice", align="C", **NEWLINE)
        self.ln(6)

    def footer(self):
        self.set_y(-22)
        if self.qr_bytes:
            y = self.get_y()
            self.image(BytesIO(self.qr_bytes), x=self.l_margin, y=y, w=14, h=14)
            self.set_xy(self.l_margin + 16, y + 4)
            self.set_font("Helvetica", "", 7)
            self.cell(40, 4, "Scan for location", align="L", **SAMELINE)
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 6, f"Page {self.page_no()}", align="C", **NEWLINE)

    # ------------------------------------------------------------
    # الأقسام
    # ------------------------------------------------------------
    def _cols(self):
        """عرض الأعمدة محسوب من العرض الفعلي للصفحة - مش أرقام ثابتة."""
        total = float(sum(_COL_WEIGHTS))
        return tuple(self.epw * wgt / total for wgt in _COL_WEIGHTS)

    def _pair(self, left_txt, right_txt, h=6):
        """سطرين جنب بعض بنص العرض لكل واحد - مضمون مايعديش الهامش."""
        w = self.epw / 2
        self.set_x(self.l_margin)
        self.cell(w, h, self._clip(left_txt, w), align="L", **SAMELINE)
        self.cell(w, h, self._clip(right_txt, w), align="R", **NEWLINE)

    def _clip(self, text, w: float) -> str:
        """بيقص النص لو أعرض من الخلية (بدل ما يطلع بره ويكسر الشكل)."""
        lines = self.wrap(text, w - 2 * self.c_margin)
        if len(lines) == 1:
            return lines[0]
        return (lines[0][:-1] + "…") if len(lines[0]) > 1 else lines[0]

    def patient_block(self, name, phone, doctor, inv_date):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, "Patient Information", **NEWLINE)
        self.set_draw_color(220, 220, 220)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(2)
        self.set_font("Helvetica", "", 10)
        self._pair("Name: " + _safe(name), _safe(f"Date: {inv_date}"))
        self._pair(_safe(f"Phone: {'+' + phone if phone else 'N/A'}"),
                   "Referring Dr: " + _safe(doctor or "N/A"))
        self.ln(5)

    def _table_head(self):
        w_no, w_name, w_tat, w_price = self._cols()
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(245, 235, 228)
        self.set_x(self.l_margin)
        self.cell(w_no, 8, "#", border=1, fill=True, align="C", **SAMELINE)
        self.cell(w_name, 8, "Test", border=1, fill=True, **SAMELINE)
        self.cell(w_tat, 8, "TAT", border=1, fill=True, align="C", **SAMELINE)
        self.cell(w_price, 8, "Price (L.E.)", border=1, fill=True,
                  align="R", **NEWLINE)
        self.set_font("Helvetica", "", 9)

    def _row(self, idx: int, it: dict, line_h: float = 7):
        w_no, w_name, w_tat, w_price = self._cols()
        name = _safe(it.get("name", ""))
        lines = self.wrap(name, w_name - 2 * self.c_margin)
        h = line_h * len(lines)

        # كسر الصفحة قبل ما نرسم أي حاجة - مش في النص (اللي كان بيخلي h سالب)
        if self.get_y() + h > self.page_break_trigger:
            self.add_page(same=True)
            self._table_head()

        x0, y0 = self.l_margin, self.get_y()

        self.set_xy(x0, y0)
        self.cell(w_no, h, str(idx), border=1, align="C", **SAMELINE)

        # عمود الاسم: إطار مرسوم يدوي + سطور - مافيش multi_cell
        x_name = x0 + w_no
        self.rect(x_name, y0, w_name, h)
        align = "R" if has_arabic(it.get("name", "")) else "L"
        for i, line in enumerate(lines):
            self.set_xy(x_name + self.c_margin, y0 + i * line_h)
            self.cell(w_name - 2 * self.c_margin, line_h, line,
                      border=0, align=align, **SAMELINE)

        days = it.get("result_days")
        price = int(it.get("price") or 0)
        self.set_xy(x_name + w_name, y0)
        self.cell(w_tat, h, f"{days}d" if days else "-", border=1,
                  align="C", **SAMELINE)
        self.cell(w_price, h, f"{price:,}" if price else "TBD", border=1,
                  align="R", **SAMELINE)
        self.set_xy(x0, y0 + h)

    def _total_line(self, label, value, h=7, bold=False, fill=False):
        w_price = self._cols()[3]
        w_label = self.epw - w_price
        self.set_x(self.l_margin)
        self.cell(w_label, h, label, align="R", fill=fill, **SAMELINE)
        self.cell(w_price, h, value, align="R", fill=fill, **NEWLINE)

    def body(self, items: List[dict], totals: dict):
        self._table_head()
        for n, it in enumerate(items, 1):
            self._row(n, it)

        self.ln(4)
        self.set_font("Helvetica", "", 11)
        self._total_line("Subtotal:", f"{totals['subtotal']:,}")
        if totals.get("discount"):
            self._total_line("Discount:", f"-{totals['discount']:,}")
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(245, 235, 228)
        self._total_line("TOTAL:", f"{totals['total']:,} L.E.",
                         h=10, fill=True)

        if totals.get("max_days"):
            self.ln(3)
            self.set_font("Helvetica", "", 9)
            self.set_x(self.l_margin)
            self.cell(0, 5,
                      f"Results ready in up to {totals['max_days']} day(s)",
                      **NEWLINE)

        notes = []
        for it in items:
            n = (it.get("collection_notes") or "").strip()
            if n and n not in notes:
                notes.append(n)
        if notes:
            self.ln(3)
            self.set_font("Helvetica", "B", 9)
            self.set_x(self.l_margin)
            self.cell(0, 5, "Collection notes:", **NEWLINE)
            self.set_font("Helvetica", "", 8)
            for n in notes[:8]:
                # ده كان مكان الباج: multi_cell(0,...) مرتين ورا بعض
                self.text_block(_safe("- " + n), 0, 4.5)

        self.ln(6)
        self.set_font("Helvetica", "I", 9)
        self.set_x(self.l_margin)
        self.cell(0, 5, "Thank you for choosing Orange Lab",
                  align="C", **NEWLINE)


def build_pdf(items, totals, name, phone, doctor, inv_date,
              maps_url="") -> bytes:
    pdf = ReceiptPDF(maps_url=maps_url)
    pdf.set_auto_page_break(True, 20)
    pdf.add_page()
    pdf.patient_block(name, phone, doctor, inv_date)
    pdf.body(items, totals)
    out = pdf.output()
    return bytes(out) if not isinstance(out, (bytes, bytearray)) else bytes(out)
