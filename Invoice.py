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
                # Keep first occurrence in case of duplicates
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
            original = original_names.get(key, key)  # fallback
            results.append((original, price))
    return results

# ========================
# 2. PDF Invoice Generation
# ========================

class ReceiptPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.location_url = "https://maps.app.goo.gl/vLdtTk9KctLXtpE4A?g_st=ac"
        # Generate QR code image once and store in memory
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

        # Add QR code on the left side of footer
        # Position: x=10, y from bottom, width=15, height=15
        self.image(BytesIO(self.qr_image_bytes), x=10, y=self.get_y()-5, w=15, h=15)

        # Optional: Add a small label near QR code
        self.set_xy(25, self.get_y()-2)
        self.set_font("Arial", "", 7)
        self.cell(30, 4, "Scan for location", align="L")

    def patient_info(self, name: str, phone: str, doctor: str, invoice_date: str):
        """[MODIFICATION ✅] Add patient information section to PDF."""
        self.set_font("Arial", "B", 10)
        self.cell(0, 7, "Patient Information", ln=True)
        self.set_font("Arial", "", 10)
        
        col_width = self.w / 2 - 15
        
        self.cell(col_width, 6, f"Name: {name}")
        self.cell(col_width, 6, f"Date: {invoice_date}", ln=True, align="R")
        
        self.cell(col_width, 6, f"Phone: {phone}")
        self.cell(col_width, 6, f"Referring Dr: {doctor}", ln=True, align="R")
        
        self.ln(5)

    def receipt_body(self, tests: List[Tuple[str, int]], total: int, discount_value: float, discount_type: str):
        """[MODIFICATION ✅] Body updated to support both fixed and percentage discount."""
        self.set_font("Arial", "", 12)
        self.set_fill_color(200, 200, 200)
        self.cell(100, 8, "Test", border=1, fill=True)
        self.cell(40, 8, "Price (L.E.)", border=1, fill=True, align="R")
        self.ln()
        
        self.set_font("Arial", "", 11)
        for name, price in tests:
            # Multi-line cell support for long names
            x_before = self.get_x()
            y_before = self.get_y()
            self.multi_cell(100, 7, name, border=1)
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
            else: # Fixed Amount
                discount_amount = discount_value
                label = f"Discount:"
                
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
        self.ln(5)  # extra space before footer

def generate_pdf_invoice(tests: List[Tuple[str, int]], total: int, discount_value: float, discount_type: str, p_name: str, p_phone: str, p_doctor: str, p_date: str) -> bytes:
    """[MODIFICATION ✅] Arguments updated to pass patient data and discount type."""
    pdf = ReceiptPDF()
    pdf.add_page()
    pdf.patient_info(p_name, p_phone, p_doctor, p_date) # Add info
    pdf.receipt_body(tests, total, discount_value, discount_type) # Updated body
    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()

def generate_whatsapp_link(tests: List[Tuple[str, int]], total: int, discount_value: float, discount_type: str, p_name: str) -> str:
    """[MODIFICATION ✅] New function to generate ready-made WhatsApp message link."""
    
    discount_amount = 0
    if discount_type == "Percentage":
        discount_amount = total * discount_value / 100
    else:
        discount_amount = discount_value
        
    final_total = total - discount_amount
    
    # Base message structure
    message =  "🍊 *Orange Lab*\n"
    message += "Medical Test Invoice\n"
    message += "-------------------\n"
    if p_name:
        message += f"Patient: *{p_name}*\n\n"
        
    # List tests
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
    
    # Encode for URL
    encoded_message = urllib.parse.quote(message)
    return f"https://wa.me/?text={encoded_message}"

# ========================
# 3. Streamlit UI
# ========================

st.set_page_config(page_title="Orange Lab - Medical Test Invoice", layout="wide")
st.title("🧾 Orange Lab Invoice Generator")

PRICE_FILE = "Diamond Price List 2026.txt"

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
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[:10]
        st.sidebar.subheader("First 10 lines of the file:")
        for i, line in enumerate(lines, 1):
            st.sidebar.write(f"{i}: {line.strip()}")
        st.stop()
except FileNotFoundError:
    st.error(f"❌ File '{PRICE_FILE}' not found. Please ensure it is in the same directory as the app.")
    st.stop()
except Exception as e:
    st.error(f"Error parsing price file: {e}")
    st.stop()

# Initialize session state
if "selected_tests" not in st.session_state:
    st.session_state.selected_tests = []          # list of (original_name, price)
if "discount_value" not in st.session_state:
    """[MODIFICATION ✅] Renamed from 'discount_percent' to generic value."""
    st.session_state.discount_value = 0.0
if "discount_type" not in st.session_state:
    """[MODIFICATION ✅] New state for discount type."""
    st.session_state.discount_type = "Percentage" # Default
if "matches_list" not in st.session_state:
    st.session_state.matches_list = []            # list of (original_name, price)
if "show_download" not in st.session_state:
    st.session_state.show_download = False
    
# Patient Info state
"""[MODIFICATION ✅] New states for patient data."""
if "patient_name" not in st.session_state: st.session_state.patient_name = ""
if "patient_phone" not in st.session_state: st.session_state.patient_phone = ""
if "patient_doctor" not in st.session_state: st.session_state.patient_doctor = ""
if "invoice_date" not in st.session_state: st.session_state.invoice_date = date.today()

# ---- Patient Information Section [MODIFICATION ✅] ----
st.subheader("👤 Patient Information")
p_col1, p_col2 = st.columns(2)
with p_col1:
    st.session_state.patient_name = st.text_input("Patient Name", value=st.session_state.patient_name, placeholder="Optional")
    st.session_state.patient_phone = st.text_input("Phone Number", value=st.session_state.patient_phone, placeholder="Optional")
with p_col2:
    st.session_state.patient_doctor = st.text_input("Referring Doctor", value=st.session_state.patient_doctor, placeholder="Optional")
    st.session_state.invoice_date = st.date_input("Date", value=st.session_state.invoice_date)
    
st.markdown("---")

# ---- Add test section ----
st.subheader("➕ Add a test")
col1, col2 = st.columns([3, 1])
with col1:
    search_term = st.text_input("Enter test name (or part of it)", placeholder="e.g., ft4, cbc, ferritin", key="search_input")
with col2:
    search_button = st.button("Search Tests")

# Process search button
if search_button and search_term:
    matches = find_tests(search_term, price_dict, original_names)
    if not matches:
        st.warning("No tests found matching your query.")
        st.session_state.matches_list = []        # clear any previous list
    else:
        st.session_state.matches_list = matches   # store matches, will show dropdown
    st.rerun()

# ---- Show selection dropdown when matches are available ----
if st.session_state.matches_list:
    matches = st.session_state.matches_list
    # Build display strings for each match
    options = [f"{name}  –  {price} L.E." for name, price in matches]

    selected_option = st.selectbox(
        "Choose the exact test you want to add:",
        options,
        key="test_choice"
    )

    # "Add chosen test" button
    if st.button("✅ Add selected test"):
        idx = options.index(selected_option)
        name, price = matches[idx]
        st.session_state.selected_tests.append((name, price))
        st.success(f"Added: {name} – {price} L.E.")
        st.session_state.matches_list = []   # hide the dropdown after adding
        st.rerun()

# ---- Invoice display ----
st.subheader("📋 Current invoice")
if not st.session_state.selected_tests:
    st.info("No tests added yet.")
else:
    # Build table data with 'Remove' button logic [MODIFICATION ✅]
    invoice_data = []
    total = 0
    for i, (name, price) in enumerate(st.session_state.selected_tests):
        total += price
        invoice_data.append({
            "index": i,
            "Test": name,
            "Price (L.E.)": price
        })
        
    # Render table manually with remove buttons to save space/complexity
    st.markdown("""
        <style>
        .invoice-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
        .invoice-table th, .invoice-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        .invoice-table th { background-color: #f2f2f2; }
        .invoice-table td:nth-child(2) { text-align: right; width: 150px;}
        .invoice-table td:nth-child(3) { text-align: center; width: 100px;}
        </style>
    """, unsafe_allow_html=True)
    
    table_html = "<table class='invoice-table'><tr><th>Test Name</th><th>Price (L.E.)</th><th>Action</th></tr>"
    for item in invoice_data:
        table_html += f"<tr><td>{item['Test']}</td><td>{item['Price (L.E.)']:,}</td><td></td></tr>"
    table_html += "</table>"
    # st.markdown(table_html, unsafe_allow_html=True) 
    
    # Using experimental data editor for native removal feature (requires Streamlit >= 1.23)
    df = pd.DataFrame(invoice_data).set_index('index')
    # Use key to detect changes
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={
        "Test": st.column_config.TextColumn(width="large", disabled=True),
        "Price (L.E.)": st.column_config.NumberColumn(format="%d L.E.", disabled=True)
    })
    
    # Sync removal if any row deleted [MODIFICATION ✅]
    if len(edited_df) < len(df):
        # Identify indices that remain
        remaining_indices = edited_df.index.tolist()
        # Filter original list based on original tuple indexing
        new_tests = [st.session_state.selected_tests[i] for i in remaining_indices]
        st.session_state.selected_tests = new_tests
        st.rerun()

    # Discount Section [MODIFICATION ✅]
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
        format_v = "%.0f%%" if new_type == "Percentage" else "%d L.E."
        
        # Reset value if type changes to prevent massive fixed discounts
        if new_type != st.session_state.discount_type:
            st.session_state.discount_value = 0.0
            st.session_state.discount_type = new_type
            st.rerun()
            
        new_value = st.number_input(
            "Amount",
            min_value=0.0,
            max_value=max_v,
            value=st.session_state.discount_value,
            step=step_v,
            format=format_v,
            label_visibility="collapsed"
        )
        
    if new_value != st.session_state.discount_value:
        st.session_state.discount_value = new_value
        st.rerun()

    # Calculate Totals [MODIFICATION ✅] Updated logic
    discount_amount = 0
    if st.session_state.discount_value > 0:
        if st.session_state.discount_type == "Percentage":
            discount_amount = total * st.session_state.discount_value / 100
        else:
            discount_amount = st.session_state.discount_value
            
    final_total = total - discount_amount

    # Totals display
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
    
    # Action Buttons Section [MODIFICATION ✅] Added WhatsApp
    col_clear, col_download, col_whatsapp = st.columns(3)
    with col_clear:
        if st.button("🗑️ Clear invoice", use_container_width=True):
            st.session_state.selected_tests.clear()
            st.session_state.discount_value = 0.0
            st.session_state.show_download = False
            # Clear patient info too
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
        # Using markdown with target="_blank" opens link in new tab
        st.markdown(f'<a href="{wa_link}" target="_blank" class="wa-btn-link" style="text-decoration:none;"><button class="wa-btn" style="width:100%; height:38px; background-color:#25D366; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:500;">📲 Send to WhatsApp</button></a>', unsafe_allow_html=True)
        # Add slight spacer below for alignment
        st.write("")

    if st.session_state.show_download:
        pdf_bytes = generate_pdf_invoice(
            st.session_state.selected_tests,
            total,
            st.session_state.discount_value,
            st.session_state.discount_type,
            st.session_state.patient_name,
            st.session_state.patient_phone,
            st.session_state.patient_doctor,
            st.session_state.invoice_date.strftime("%Y-%m-%d") # Format date
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
st.sidebar.caption("Developed by Dr/Hussein Ali")

st.markdown("---")
st.markdown("<p style='text-align: center; color: #888888; font-size: 14px;'>Developed by Dr/Hussein Ali</p>", unsafe_allow_html=True)
