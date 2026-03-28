import streamlit as st
import pdfplumber
import re
from typing import Dict, List, Tuple
from fpdf import FPDF
import io
import pandas as pd

# ========================
# 1. Parse PDF price list
# ========================

@st.cache_data
def parse_price_list_from_pdf(pdf_path: str) -> Dict[str, int]:
    """Extract test names and prices from a multi-page PDF."""
    price_dict = {}
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Skip obvious header/footer lines
                if any(header in line for header in ["Result date", "Collection notes", "Price", "Page", "L.E."]):
                    continue
                
                # Look for a price pattern: number followed by "L.E." (may be separated by a space)
                matches = re.findall(r'(\d{1,5}(?:,\d{3})*)\s*L\.E\.', line)
                if matches:
                    # Take the last price found (most reliable)
                    price_str = matches[-1].replace(',', '')
                    try:
                        price = int(price_str)
                    except ValueError:
                        continue
                    
                    # Find the position of that price in the line
                    last_price_pos = line.rfind(matches[-1] + " L.E.")
                    if last_price_pos == -1:
                        last_price_pos = line.rfind(matches[-1] + "L.E.")
                    if last_price_pos != -1:
                        test_name = line[:last_price_pos].strip()
                        # Clean up test name: remove leading numbers, trailing digits, extra spaces
                        test_name = re.sub(r'^\d+\.\s*', '', test_name)
                        test_name = re.sub(r'\d+$', '', test_name).strip()
                        if test_name and price > 0:
                            # Use lowercase as key for case-insensitive matching
                            price_dict[test_name.lower()] = price
    return price_dict

def find_tests(partial: str, price_dict: Dict[str, int]) -> List[Tuple[str, int]]:
    """Return all tests whose name contains partial (case-insensitive)."""
    partial_lower = partial.lower()
    return [(name, price) for name, price in price_dict.items() if partial_lower in name]

# ========================
# 2. PDF Invoice Generation (Receipt Style)
# ========================

class ReceiptPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 16)
        self.cell(0, 10, "Orange Lab", ln=True, align="C")
        self.set_font("Arial", "", 10)
        self.cell(0, 5, "Medical Test Invoice", ln=True, align="C")
        self.ln(10)
    
    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")
    
    def receipt_body(self, tests: List[Tuple[str, int]], total: int):
        self.set_font("Arial", "", 12)
        # Table header
        self.set_fill_color(200, 200, 200)
        self.cell(100, 8, "Test", border=1, fill=True)
        self.cell(40, 8, "Price (L.E.)", border=1, fill=True, align="R")
        self.ln()
        # Table rows
        for name, price in tests:
            self.cell(100, 8, name.title(), border=1)
            self.cell(40, 8, f"{price:,}", border=1, align="R")
            self.ln()
        # Total row
        self.ln(5)
        self.set_font("Arial", "B", 12)
        self.cell(100, 8, "TOTAL", border=0)
        self.cell(40, 8, f"{total:,} L.E.", border=0, align="R")
        self.ln(10)
        self.set_font("Arial", "I", 10)
        self.cell(0, 5, "Thank you for choosing Orange Lab", ln=True, align="C")

def generate_pdf_invoice(tests: List[Tuple[str, int]], total: int) -> bytes:
    """Generate a PDF invoice and return as bytes."""
    pdf = ReceiptPDF()
    pdf.add_page()
    pdf.receipt_body(tests, total)
    return pdf.output(dest='S').encode('latin1')  # BytesIO compatible

# ========================
# 3. Streamlit UI
# ========================

st.set_page_config(page_title="Orange Lab - Medical Test Invoice", layout="wide")
st.title("🧾 Orange Lab Invoice Generator")

# Load price list
PRICE_FILE = "Diamond Price List 2026.pdf"
try:
    price_dict = parse_price_list_from_pdf(PRICE_FILE)
    st.sidebar.success(f"✅ Loaded {len(price_dict)} tests from PDF")
except Exception as e:
    st.error(f"❌ Could not load PDF: {e}")
    st.stop()

# Initialize session state
if "selected_tests" not in st.session_state:
    st.session_state.selected_tests = []  # list of (name, price)

# ---- Add test section ----
st.subheader("➕ Add a test")
col1, col2 = st.columns([3, 1])
with col1:
    search_term = st.text_input("Enter test name (or part of it)", placeholder="e.g., cbc, ferritin, vitamin")
with col2:
    add_button = st.button("Add Test")

if add_button and search_term:
    # Exact match first
    key = search_term.lower()
    if key in price_dict:
        st.session_state.selected_tests.append((key, price_dict[key]))
        st.success(f"Added: {key.title()} – {price_dict[key]} L.E.")
        st.rerun()
    else:
        matches = find_tests(search_term, price_dict)
        if not matches:
            st.warning("No tests found.")
        elif len(matches) == 1:
            name, price = matches[0]
            st.session_state.selected_tests.append((name, price))
            st.success(f"Added: {name.title()} – {price} L.E.")
            st.rerun()
        else:
            st.info(f"Found {len(matches)} tests. Select one:")
            options = [f"{name.title()} – {price} L.E." for name, price in matches]
            selected_idx = st.selectbox("Choose a test", options, index=0, key="match_select")
            if st.button("Add selected test", key="add_selected"):
                idx = options.index(selected_idx)
                name, price = matches[idx]
                st.session_state.selected_tests.append((name, price))
                st.success(f"Added: {name.title()} – {price} L.E.")
                st.rerun()

# ---- Invoice display ----
st.subheader("📋 Current invoice")
if not st.session_state.selected_tests:
    st.info("No tests added yet.")
else:
    # Display table
    data = []
    total = 0
    for name, price in st.session_state.selected_tests:
        data.append({"Test": name.title(), "Price (L.E.)": price})
        total += price
    df = pd.DataFrame(data)
    st.table(df)
    st.metric("Total", f"{total} L.E.")
    
    # Buttons
    col_clear, col_download = st.columns(2)
    with col_clear:
        if st.button("🗑️ Clear invoice"):
            st.session_state.selected_tests.clear()
            st.rerun()
    with col_download:
        if st.button("📄 Download PDF Invoice"):
            pdf_bytes = generate_pdf_invoice(st.session_state.selected_tests, total)
            st.download_button(
                label="Click to download",
                data=pdf_bytes,
                file_name="orange_lab_invoice.pdf",
                mime="application/pdf"
            )
