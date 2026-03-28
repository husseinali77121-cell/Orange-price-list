import streamlit as st
import re
from typing import Dict, List, Tuple
from fpdf import FPDF
import pandas as pd
from io import BytesIO

# ========================
# 1. Parse text price list (direct file)
# ========================

@st.cache_data
def parse_price_list_from_text(file_path: str) -> Dict[str, int]:
    """Read the text file and return a dict {test_name_lowercase: price}."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    price_dict = {}
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

            test_name = line[:match.start()].strip()
            # No removal of trailing digits – keep them!
            if test_name and price > 0:
                price_dict[test_name.lower()] = price

    return price_dict

def find_tests(partial: str, price_dict: Dict[str, int]) -> List[Tuple[str, int]]:
    """Return all tests whose name contains partial (case-insensitive)."""
    partial_lower = partial.lower()
    return [(name, price) for name, price in price_dict.items() if partial_lower in name]

# ========================
# 2. PDF Invoice Generation (receipt style with discount)
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

    def receipt_body(self, tests: List[Tuple[str, int]], total: int, discount_percent: float = 0):
        self.set_font("Arial", "", 12)
        self.set_fill_color(200, 200, 200)
        self.cell(100, 8, "Test", border=1, fill=True)
        self.cell(40, 8, "Price (L.E.)", border=1, fill=True, align="R")
        self.ln()
        for name, price in tests:
            self.cell(100, 8, name.title(), border=1)
            self.cell(40, 8, f"{price:,}", border=1, align="R")
            self.ln()
        self.ln(5)
        self.set_font("Arial", "", 12)
        self.cell(100, 8, "Subtotal:", border=0)
        self.cell(40, 8, f"{total:,} L.E.", border=0, align="R")
        self.ln()
        if discount_percent > 0:
            discount_amount = total * discount_percent / 100
            self.cell(100, 8, f"Discount ({discount_percent:.0f}%):", border=0)
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

def generate_pdf_invoice(tests: List[Tuple[str, int]], total: int, discount_percent: float = 0) -> bytes:
    pdf = ReceiptPDF()
    pdf.add_page()
    pdf.receipt_body(tests, total, discount_percent)
    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()

# ========================
# 3. Streamlit UI
# ========================

st.set_page_config(page_title="Orange Lab - Medical Test Invoice", layout="wide")
st.title("🧾 Orange Lab Invoice Generator")

PRICE_FILE = "Diamond Price List 2026.txt"
try:
    price_dict = parse_price_list_from_text(PRICE_FILE)
    st.sidebar.success(f"✅ Loaded {len(price_dict)} tests from {PRICE_FILE}")

    st.sidebar.subheader("🔍 Sample of loaded tests (first 30)")
    if price_dict:
        sample_items = list(price_dict.items())[:30]
        for name, price in sample_items:
            st.sidebar.write(f"{name[:40]:40} : {price} L.E.")
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

if "selected_tests" not in st.session_state:
    st.session_state.selected_tests = []
if "discount_percent" not in st.session_state:
    st.session_state.discount_percent = 0.0

# ---- Add test section ----
st.subheader("➕ Add a test")
col1, col2 = st.columns([3, 1])
with col1:
    search_term = st.text_input("Enter test name (or part of it)", placeholder="e.g., ft4, cbc, ferritin")
with col2:
    add_button = st.button("Add Test")

if add_button and search_term:
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

# ---- Invoice display with discount ----
st.subheader("📋 Current invoice")
if not st.session_state.selected_tests:
    st.info("No tests added yet.")
else:
    total = sum(price for _, price in st.session_state.selected_tests)

    st.write("**Discount**")
    discount = st.number_input(
        "Discount (%)",
        min_value=0.0,
        max_value=100.0,
        value=st.session_state.discount_percent,
        step=1.0,
        format="%.0f"
    )
    if discount != st.session_state.discount_percent:
        st.session_state.discount_percent = discount
        st.rerun()

    discount_amount = total * st.session_state.discount_percent / 100
    final_total = total - discount_amount

    data = []
    for name, price in st.session_state.selected_tests:
        data.append({"Test": name.title(), "Price (L.E.)": price})
    df = pd.DataFrame(data)
    st.table(df)

    st.write(f"**Subtotal:** {total:,} L.E.")
    if st.session_state.discount_percent > 0:
        st.write(f"**Discount ({st.session_state.discount_percent:.0f}%):** -{discount_amount:,.0f} L.E.")
        st.metric("Total after discount", f"{final_total:,.0f} L.E.")
    else:
        st.metric("Total", f"{total:,} L.E.")

    col_clear, col_download = st.columns(2)
    with col_clear:
        if st.button("🗑️ Clear invoice"):
            st.session_state.selected_tests.clear()
            st.session_state.discount_percent = 0.0
            st.rerun()
    with col_download:
        if st.button("📄 Download PDF Invoice"):
            pdf_bytes = generate_pdf_invoice(
                st.session_state.selected_tests,
                total,
                st.session_state.discount_percent
            )
            st.download_button(
                label="Click to download",
                data=pdf_bytes,
                file_name="orange_lab_invoice.pdf",
                mime="application/pdf"
            )
