# pdf_invoice.py
# ============================================================
#  توليد فاتورة PDF (إنجليزي - fpdf2 بيدعم latin-1 بس)
# ============================================================

from io import BytesIO
from typing import List

from fpdf import FPDF
from fpdf.enums import WrapMode

from arabic_pdf import find_font, has_arabic, to_pdf_text

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False


# اسم العائلة المستخدم في الـ PDF: يونيكود لو لقينا خط، وإلا Helvetica
UNI_FONT = "OLUni"
_FONT_PATH = find_font()
_FONT_PATH_B = find_font(bold=True)


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
        self.qr_bytes = None
        if HAS_QR and maps_url:
            try:
                buf = BytesIO()
                qrcode.make(maps_url).save(buf, format="PNG")
                self.qr_bytes = buf.getvalue()
            except Exception:
                # الـ QR ميزة إضافية؛ فشل توليده لا يمنع إنشاء الفاتورة.
                self.qr_bytes = None

    def set_font(self, family=None, style="", size=0):
        """
        أي نداء لـ Helvetica بيتحوّل للخط اليونيكود لو متاح -
        فمفيش سطر واحد في الفاتورة محتاج يتغيّر.
        """
        if self.uni and (family or "").lower() in ("helvetica", "arial", ""):
            family = UNI_FONT
            style = style.replace("I", "")     # مفيش مائل في الخط ده
        return super().set_font(family, style, size)

    def header(self):
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(214, 84, 26)
        self.cell(0, 9, "Orange Lab", ln=True, align="C")
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, "Medical Test Invoice", ln=True, align="C")
        self.ln(6)

    def footer(self):
        self.set_y(-22)
        if self.qr_bytes:
            self.image(BytesIO(self.qr_bytes), x=10, y=self.get_y(), w=14, h=14)
            self.set_xy(26, self.get_y() + 4)
            self.set_font("Helvetica", "", 7)
            self.cell(40, 4, "Scan for location", align="L")
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")

    def patient_block(self, name, phone, doctor, inv_date):
        w = (self.w - 20) / 2
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, "Patient Information", ln=True)
        self.set_draw_color(220, 220, 220)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.ln(2)
        self.set_font("Helvetica", "", 10)
        self.cell(w, 6, "Name: " + _safe(name))
        self.cell(w, 6, _safe(f"Date: {inv_date}"), ln=True, align="R")
        self.cell(w, 6, _safe(f"Phone: {'+' + phone if phone else 'N/A'}"))
        self.cell(w, 6, "Referring Dr: " + _safe(doctor or "N/A"),
                  ln=True, align="R")
        self.ln(5)

    def body(self, items: List[dict], totals: dict):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(245, 235, 228)
        self.cell(12, 8, "#", border=1, fill=True, align="C")
        self.cell(108, 8, "Test", border=1, fill=True)
        self.cell(28, 8, "TAT", border=1, fill=True, align="C")
        self.cell(42, 8, "Price (L.E.)", border=1, fill=True, align="R")
        self.ln()

        self.set_font("Helvetica", "", 9)
        for n, it in enumerate(items, 1):
            x0, y0 = self.get_x(), self.get_y()
            self.cell(12, 7, str(n), border=1, align="C")
            self.multi_cell(108, 7, _safe(it["name"]), border=1, wrapmode=WrapMode.CHAR)
            h = self.get_y() - y0
            self.set_xy(x0 + 120, y0)
            days = it.get("result_days")
            self.cell(28, h, f"{days}d" if days else "-", border=1, align="C")
            price = int(it["price"])
            self.cell(42, h, f"{price:,}" if price else "TBD", border=1,
                      align="R", ln=True)

        self.ln(4)
        self.set_font("Helvetica", "", 11)
        self.cell(148, 7, "Subtotal:", align="R")
        self.cell(42, 7, f"{totals['subtotal']:,}", align="R", ln=True)
        if totals["discount"]:
            self.cell(148, 7, "Discount:", align="R")
            self.cell(42, 7, f"-{totals['discount']:,}", align="R", ln=True)
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(245, 235, 228)
        self.cell(148, 10, "TOTAL:", align="R", fill=True)
        self.cell(42, 10, f"{totals['total']:,} L.E.", align="R", ln=True, fill=True)

        if totals.get("max_days"):
            self.ln(3)
            self.set_font("Helvetica", "", 9)
            self.cell(0, 5, f"Results ready in up to {totals['max_days']} day(s)",
                      ln=True)

        notes = []
        for it in items:
            n = (it.get("collection_notes") or "").strip()
            if n and n not in notes:
                notes.append(n)
        if notes:
            self.ln(3)
            self.set_font("Helvetica", "B", 9)
            self.cell(0, 5, "Collection notes:", ln=True)
            self.set_font("Helvetica", "", 8)
            for n in notes[:8]:
                self.multi_cell(0, 4.5, _safe("- " + n), wrapmode=WrapMode.CHAR)

        self.ln(6)
        self.set_font("Helvetica", "I", 9)
        self.cell(0, 5, "Thank you for choosing Orange Lab", ln=True, align="C")


def build_pdf(items, totals, name, phone, doctor, inv_date,
              maps_url="") -> bytes:
    pdf = ReceiptPDF(maps_url=maps_url)
    pdf.add_page()
    pdf.patient_block(name, phone, doctor, inv_date)
    pdf.body(items, totals)
    out = pdf.output()
    return bytes(out) if not isinstance(out, (bytes, bytearray)) else bytes(out)
