import streamlit as st
import re
from typing import Dict, List, Tuple
from fpdf import FPDF
import pandas as pd
from io import BytesIO
import qrcode
import urllib.parse
from datetime import date

# ========================
# Helper Function for PDF Safety
# ========================

def safe_pdf_text(text: str) -> str:
    """تصفية النصوص لمنع انهيار الـ PDF عند إدخال حروف عربية أو رموز غير مدعومة في الخط الأساسي"""
    if text is None:
        return "N/A"
    # تحويل النص لترميز latin-1 الآمن واستبدال الحروف غير المدعومة بعلامات استفهام لمنع الـ Exception
    return str(text).encode('latin-1', errors='replace').decode('latin-1')

# ========================
# 1. Parse text price list
# ========================

@st.cache_data
def parse_price_list_from_text(file_path: str) -> Tuple[Dict[str, int], Dict[str, str]]:
    """
    Read the text file and return:
    - price_dict: {test_name_lower: price}
    - original_names: {test_name_lower: original_name}
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    price_dict = {}  
    original_names = {}  
    price_pattern = re.compile(r'(\d{1,5}(?:,\d{3})?)\s*L\.E\.?')  

    for line in content.splitlines():  
        line = line.strip()  
        if not line:  
            continue  
        if any(header in line for header in ["Result date", "Collection notes", "Price", "Page"]):  
            continue  

        match = price_pattern.search(line)  
        if match:  
            price_str = match.group(1).replace(',', '')  
            try:  
                price = int(price_str)  
            except ValueError:  
                continue  

            test_name_original = line[:match.start()].strip()  
            if test_name_original and price > 0:  
                key = test_name_original.lower()  
                if key not in price_dict:  
                    price_dict[key] = price  
                    original_names[key] = test_name_original  

    return price_dict, original_names

def find_tests(partial: str, price_dict: Dict[str, int], original_names: Dict[str, str]) -> List[Tuple[str, int]]:
    """Return list of (original_name, price) for tests whose name contains partial (case-insensitive)."""
    partial_lower = partial.lower()
    results = []
    for key, price in price_dict.items():
        if partial_lower in key:
            original = original_names.get(key, key)
            results.append((original, price))
    return results

# ========================
# 2. PDF Invoice Generation
# ========================

class ReceiptPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.location_url = "https://maps.app.goo.gl/vLdtTk9KctLXtpE4A?g_st=ac"
        qr_img = qrcode.make(self.location_url)
        buf = BytesIO()
        qr_img.save(buf, format='PNG')
        buf.seek(0)
        self.qr_image_bytes = buf.read()

    def header(self):  
        self.set_font("Arial", "B", 16)  
        self.cell(0, 10, "Orange Lab", ln=True, align="C")  
        self.set_font("Arial", "", 10)  
        self.cell(0, 5, "Medical Test Invoice", ln=True, align="C")  
        self.ln(10)  

    def footer(self):  
        self.set_y(-20)  
        self.set_font("Arial", "I", 8)  
        self.cell(0, 10, f"Page {self.page_no()}", align="C")  
        self.image(BytesIO(self.qr_image_bytes), x=10, y=self.get_y()-5, w=15, h=15)  
        self.set_xy(25, self.get_y()-2)  
        self.set_font("Arial", "", 7)  
        self.cell(30, 4, "Scan for location", align="L")  

    def patient_info(self, name: str, phone: str, doctor: str, invoice_date: str):  
        """إضافة بيانات المريض داخل الـ PDF بعد تنقيتها بشكل آمن"""  
        self.set_font("Arial", "B", 10)  
        self.cell(0, 7, "Patient Information", ln=True)  
        self.set_font("Arial", "", 10)  
          
        col_width = (self.w - 20) / 2  
          
        # حماية النصوص المكتوبة قبل تمريرها للخلايا  
        clean_name = safe_pdf_text(name if name else 'N/A')  
        clean_phone = safe_pdf_text(phone if phone else 'N/A')  
        clean_doctor = safe_pdf_text(doctor if doctor else 'N/A')  
        clean_date = safe_pdf_text(invoice_date)  
          
        self.cell(col_width, 6, f"Name: {clean_name}")  
        self.cell(col_width, 6, f"Date: {clean_date}", ln=True, align="R")  
          
        self.cell(col_width, 6, f"Phone: {clean_phone}")  
        self.cell(col_width, 6, f"Referring Dr: {clean_doctor}", ln=True, align="R")  
          
        self.ln(5)  

    def receipt_body(self, tests: List[Tuple[str, int]], total: int, discount_value: float, discount_type: str):  
        """طباعة جدول التحاليل والأسعار والخصومات في الـ PDF بأمان"""  
        self.set_font("Arial", "", 12)  
        self.set_fill_color(200, 200, 200)  
        self.cell(100, 8, "Test", border=1, fill=True)  
        self.cell(40, 8, "Price (L.E.)", border=1, fill=True, align="R")  
        self.ln()  
          
        self.set_font("Arial", "", 11)  
        for name, price in tests:  
            clean_test_name = safe_pdf_text(name)  
            x_before = self.get_x()  
            y_before = self.get_y()  
            self.multi_cell(100, 7, clean_test_name, border=1)  
            y_after = self.get_y()  
            height = y_after - y_before  
              
            self.set_xy(x_before + 100, y_before)  
            self.cell(40, height, f"{price:,}", border=1, align="R", ln=True)  
              
        self.ln(5)  
        self.set_font("Arial", "", 12)  
        self.cell(100, 8, "Subtotal:", border=0)  
        self.cell(40, 8, f"{total:,} L.E.", border=0, align="R")  
        self.ln()  
          
        discount_amount = 0  
        if discount_value > 0:  
            if discount_type == "Percentage":  
                discount_amount = total * discount_value / 100  
                label = f"Discount ({discount_value:.0f}%):"  
            else:  
                discount_amount = discount_value  
                label = "Discount:"  
                  
            self.cell(100, 8, label, border=0)  
            self.cell(40, 8, f"- {discount_amount:,.0f} L.E.", border=0, align="R")  
            self.ln()  
              
            final_total = total - discount_amount  
            self.set_font("Arial", "B", 12)  
            self.cell(100, 8, "TOTAL AFTER DISCOUNT:", border=0)  
            self.cell(40, 8, f"{final_total:,.0f} L.E.", border=0, align="R")  
        else:  
            self.set_font("Arial", "B", 12)  
            self.cell(100, 8, "TOTAL:", border=0)  
            self.cell(40, 8, f"{total:,} L.E.", border=0, align="R")  
              
        self.ln(10)  
        self.set_font("Arial", "I", 10)  
        self.cell(0, 5, "Thank you for choosing Orange Lab", ln=True, align="C")

def generate_pdf_invoice(tests: List[Tuple[str, int]], total: int, discount_value: float, discount_type: str, p_name: str, p_phone: str, p_doctor: str, p_date: str) -> bytes:
    pdf = ReceiptPDF()
    pdf.add_page()
    pdf.patient_info(p_name, p_phone, p_doctor, p_date)
    pdf.receipt_body(tests, total, discount_value, discount_type)
    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()

def generate_whatsapp_link(tests: List[Tuple[str, int]], total: int, discount_value: float, discount_type: str, p_name: str) -> str:
    """إنشاء نص رسالة الواتساب المجهزة (تدعم الحروف العربية والانجليزية بدون مشاكل)"""
    discount_amount = total * discount_value / 100 if discount_type == "Percentage" else discount_value
    final_total = total - discount_amount

    message = "🍊 *Orange Lab*\n"  
    message += "Medical Test Invoice\n"  
    message += "-------------------\n"  
    if p_name:  
        message += f"Patient: *{p_name}*\n\n"  
          
    for name, price in tests:  
        message += f"• {name} ...... {price:,} L.E.\n"  
          
    message += "-------------------\n"  
    message += f"Subtotal: {total:,} L.E.\n"  
    
    if discount_value > 0:  
        if discount_type == "Percentage":  
            message += f"Discount ({discount_value:.0f}%): -{discount_amount:,.0f} L.E.\n"  
        else:  
            message += f"Discount: -{discount_amount:,.0f} L.E.\n"  
              
    message += f"*Total = {final_total:,.0f} L.E.*"  
    
    encoded_message = urllib.parse.quote(message)  
    return f"https://wa.me/?text={encoded_message}"

# ========================
# 3. Streamlit UI
# ========================

st.set_page_config(page_title="Orange Lab - Medical Test Invoice", layout="wide")
st.title("🧾 Orange Lab Invoice Generator")

PRICE_FILE = "Orange lab Price list 2026.txt"

# Load price list with error handling

try:
    price_dict, original_names = parse_price_list_from_text(PRICE_FILE)
    st.sidebar.success(f"✅ Loaded {len(price_dict)} tests from {PRICE_FILE}")

    st.sidebar.subheader("🔍 Sample of loaded tests (first 30)")  
    if price_dict:  
        sample_items = list(price_dict.items())[:30]  
        for key, price in sample_items:  
            display_name = original_names.get(key, key)  
            st.sidebar.write(f"{display_name[:40]:40} : {price} L.E.")  
    else:  
        st.sidebar.error("No tests were extracted. Check the file format.")  
        st.stop()

except FileNotFoundError:
    st.error(f"❌ File '{PRICE_FILE}' not found. Please ensure it is in the same directory as the app.")
    st.stop()
except Exception as e:
    st.error(f"Error parsing price file: {e}")
    st.stop()

# Initialize session state

if "selected_tests" not in st.session_state:
    st.session_state.selected_tests = []
if "discount_value" not in st.session_state:
    st.session_state.discount_value = 0.0
if "discount_type" not in st.session_state:
    st.session_state.discount_type = "Percentage"
if "matches_list" not in st.session_state:
    st.session_state.matches_list = []
if "show_download" not in st.session_state:
    st.session_state.show_download = False

# Patient Information States

if "patient_name" not in st.session_state: st.session_state.patient_name = ""
if "patient_phone" not in st.session_state: st.session_state.patient_phone = ""
if "patient_doctor" not in st.session_state: st.session_state.patient_doctor = ""
if "invoice_date" not in st.session_state: st.session_state.invoice_date = date.today()

# ---- Patient Information Section ----

st.subheader("👤 Patient Information")
st.info("💡 نصيحة: يُفضل كتابة الأسماء باللغة الإنجليزية لتظهر منسقة وبشكل صحيح تماماً داخل ملف الـ PDF.")
p_col1, p_col2 = st.columns(2)
with p_col1:
    st.session_state.patient_name = st.text_input("Patient Name", value=st.session_state.patient_name, placeholder="e.g., Ahmed Ali")
    st.session_state.patient_phone = st.text_input("Phone Number", value=st.session_state.patient_phone, placeholder="Optional")
with p_col2:
    st.session_state.patient_doctor = st.text_input("Referring Doctor", value=st.session_state.patient_doctor, placeholder="e.g., Dr. Sameh")
    st.session_state.invoice_date = st.date_input("Date", value=st.session_state.invoice_date)

st.markdown("---")

# ---- Add test section ----

st.subheader("➕ Add a test")
col1, col2 = st.columns([3, 1])
with col1:
    search_term = st.text_input("Enter test name (or part of it)", placeholder="e.g., ft4, cbc, ferritin", key="search_input")
with col2:
    search_button = st.button("Search Tests")

if search_button and search_term:
    matches = find_tests(search_term, price_dict, original_names)
    if not matches:
        st.warning("No tests found matching your query.")
        st.session_state.matches_list = []
    else:
        st.session_state.matches_list = matches
    st.rerun()

if st.session_state.matches_list:
    matches = st.session_state.matches_list
    options = [f"{name}  –  {price} L.E." for name, price in matches]

    selected_option = st.selectbox(  
        "Choose the exact test you want to add:",  
        options,  
        key="test_choice"  
    )  

    if st.button("✅ Add selected test"):  
        idx = options.index(selected_option)  
        name, price = matches[idx]  
        st.session_state.selected_tests.append((name, price))  
        st.success(f"Added: {name} – {price} L.E.")  
        st.session_state.matches_list = []  
        st.rerun()

# ---- Invoice display ----

st.subheader("📋 Current invoice")
if not st.session_state.selected_tests:
    st.info("No tests added yet.")
else:
    # عرض التحليل والسعر وعلامة الحذف في نفس السطر
    h_col1, h_col2, h_col3 = st.columns([5, 2, 1])
    h_col1.markdown("**Test**")
    h_col2.markdown("**Price (L.E.)**")
    h_col3.markdown("**Delete**")

    idx_to_remove = None

    for i, (name, price) in enumerate(st.session_state.selected_tests):
        c1, c2, c3 = st.columns([5, 2, 1])
        c1.markdown(name)
        c2.markdown(f"**{price:,} L.E.**")
        if c3.button("❌", key=f"del_{i}"):
            idx_to_remove = i

    # تنفيذ عملية الحذف وإعادة تحديث الصفحة فوراً
    if idx_to_remove is not None:
        st.session_state.selected_tests.pop(idx_to_remove)
        st.rerun()

    st.markdown("---")

    # حساب الإجمالي المبدئي بعد أي عمليات حذف
    total = sum(price for _, price in st.session_state.selected_tests)

    # قسم الخصم الذكي والآمن من الأخطاء
    st.markdown("**Discount**")
    d_col1, d_col2 = st.columns([1, 2])
    with d_col1:
        new_type = st.radio(
            "Type",
            ["Percentage", "Fixed Amount"],
            index=["Percentage", "Fixed Amount"].index(st.session_state.discount_type),
            label_visibility="collapsed",
            horizontal=True
        )
    with d_col2:
        max_v = 100.0 if new_type == "Percentage" else float(total)
        step_v = 1.0 if new_type == "Percentage" else 10.0
        label_text = "Discount (%)" if new_type == "Percentage" else "Discount (L.E.)"

        if new_type != st.session_state.discount_type:
            st.session_state.discount_value = 0.0
            st.session_state.discount_type = new_type
            st.rerun()

        new_value = st.number_input(
            label_text,
            min_value=0.0,
            max_value=max_v,
            value=float(st.session_state.discount_value),
            step=step_v,
            format="%.0f"
        )

    if new_value != st.session_state.discount_value:
        st.session_state.discount_value = new_value
        st.rerun()

    # حسابات الخصم النهائية
    discount_amount = total * st.session_state.discount_value / 100 if st.session_state.discount_type == "Percentage" else st.session_state.discount_value
    final_total = total - discount_amount

    t_col1, t_col2 = st.columns(2)
    with t_col2:
        st.write(f"**Subtotal:** {total:,} L.E.")
        if st.session_state.discount_value > 0:
            label = f"Discount ({st.session_state.discount_value:.0f}%)" if st.session_state.discount_type == "Percentage" else "Discount"
            st.write(f"**{label}:** -{discount_amount:,.0f} L.E.")
            st.metric("Total after discount", f"{final_total:,.0f} L.E.")
        else:
            st.metric("Total", f"{total:,} L.E.")

    st.markdown("---")

    # أزرار التحكم والإرسال والطباعة
    col_clear, col_download, col_whatsapp = st.columns(3)
    with col_clear:
        if st.button("🗑️ Clear invoice", use_container_width=True):
            st.session_state.selected_tests.clear()
            st.session_state.discount_value = 0.0
            st.session_state.show_download = False
            st.session_state.patient_name = ""
            st.session_state.patient_phone = ""
            st.session_state.patient_doctor = ""
            st.session_state.invoice_date = date.today()
            st.rerun()

    with col_download:
        if st.button("📄 Prepare PDF Invoice", use_container_width=True):
            st.session_state.show_download = True
            st.rerun()

    with col_whatsapp:
        wa_link = generate_whatsapp_link(
            st.session_state.selected_tests,
            total,
            st.session_state.discount_value,
            st.session_state.discount_type,
            st.session_state.patient_name
        )
        st.markdown(f'<a href="{wa_link}" target="_blank" style="text-decoration:none;"><button style="width:100%; height:38px; background-color:#25D366; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:500;">📲 Send to WhatsApp</button></a>', unsafe_allow_html=True)

    if st.session_state.show_download:
        pdf_bytes = generate_pdf_invoice(
            st.session_state.selected_tests,
            total,
            st.session_state.discount_value,
            st.session_state.discount_type,
            st.session_state.patient_name,
            st.session_state.patient_phone,
            st.session_state.patient_doctor,
            st.session_state.invoice_date.strftime("%Y-%m-%d")
        )
        st.download_button(
            label="⬇️ Click to download PDF",
            data=pdf_bytes,
            file_name="orange_lab_invoice.pdf",
            mime="application/pdf",
            key="pdf_download_button",
            use_container_width=True
        )

# ========================
# 4. App Footer / Signature
# ========================

st.sidebar.markdown("---")
st.sidebar.markdown("<p style='text-align: center; font-weight: bold; color: #FF4B4B;'>Developed by Dr/Hussein Ali</p>", unsafe_allow_html=True)

st.markdown("---")
st.markdown("<p style='text-align: center; color: #FF4B4B; font-size: 20px; font-weight: bold; letter-spacing: 1px;'>👨‍💻 Developed by Dr/Hussein Ali</p>", unsafe_allow_html=True)
