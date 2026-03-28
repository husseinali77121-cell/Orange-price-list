import streamlit as st
import re
from typing import Dict, List, Tuple
from fpdf import FPDF
import pandas as pd
import io

# ========================
# 1. Parse text price list (improved + debug)
# ========================

def parse_price_list_from_text(text_content: str) -> Dict[str, int]:
    """Parse the text content and return a dict {test_name_lowercase: price}."""
    price_dict = {}
    price_pattern = re.compile(r'(\d{1,5}(?:,\d{3})?)\s*L\.E\.?')
    
    lines = text_content.splitlines()
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        # Skip lines that are likely headers/footers
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
            test_name = re.sub(r'\d+$', '', test_name).strip()  # remove trailing numbers
            if test_name and price > 0:
                # Keep original test name for display, but store lowercase for search
                price_dict[test_name.lower()] = price
        else:
            # Debug: optionally show lines without price
            # Uncomment to see skipped lines
            # st.sidebar.write(f"Skipped line {line_num}: {line}")
            pass

    return price_dict

def find_tests(partial: str, price_dict: Dict[str, int]) -> List[Tuple[str, int]]:
    """Return all tests whose name contains partial (case-insensitive)."""
    partial_lower = partial.lower()
    return [(name, price) for name, price in price_dict.items() if partial_lower in name]

# ========================
# 2. PDF Invoice Generation (unchanged)
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
        self.set_fill_color(200, 200, 200)
        self.cell(100, 8, "Test", border=1, fill=True)
        self.cell(40, 8, "Price (L.E.)", border=1, fill=True, align="R")
        self.ln()
        for name, price in tests:
            self.cell(100, 8, name.title(), border=1)
            self.cell(40, 8, f"{price:,}", border=1, align="R")
            self.ln()
        self.ln(5)
        self.set_font("Arial", "B", 12)
        self.cell(100, 8, "TOTAL", border=0)
        self.cell(40, 8, f"{total:,} L.E.", border=0, align="R")
        self.ln(10)
        self.set_font("Arial", "I", 10)
        self.cell(0, 5, "Thank you for choosing Orange Lab", ln=True, align="C")

def generate_pdf_invoice(tests: List[Tuple[str, int]], total: int) -> bytes:
    pdf = ReceiptPDF()
    pdf.add_page()
    pdf.receipt_body(tests, total)
    return pdf.output(dest='S').encode('latin1')

# ========================
# 3. Streamlit UI
# ========================

st.set_page_config(page_title="Orange Lab - Medical Test Invoice", layout="wide")
st.title("🧾 Orange Lab Invoice Generator")

# ---- File uploader ----
st.sidebar.subheader("📁 Upload Price List")
uploaded_file = st.sidebar.file_uploader("Choose the text file (Diamond Price List 2026.txt)", type=["txt"])

if uploaded_file is not None:
    try:
        # Read file content (handle potential encoding issues)
        content = uploaded_file.getvalue().decode("utf-8")
        price_dict = parse_price_list_from_text(content)
        st.sidebar.success(f"✅ Loaded {len(price_dict)} tests")
        
        # Debug: show sample of extracted tests
        st.sidebar.subheader("🔍 Sample of loaded tests")
        if price_dict:
            sample_items = list(price_dict.items())[:20]
            for name, price in sample_items:
                st.sidebar.write(f"{name[:35]:35} : {price} L.E.")
        else:
            st.sidebar.error("No tests were extracted. Check file format.")
            # Show first few lines to help debug
            st.sidebar.subheader("First 10 lines of file:")
            for i, line in enumerate(content.splitlines()[:10], 1):
                st.sidebar.write(f"{i}: {line}")
    except Exception as e:
        st.sidebar.error(f"Error reading file: {e}")
        st.stop()
else:
    st.sidebar.info("Please upload the price list text file.")
    price_dict = {}  # empty until file is uploaded

# Initialize session state
if "selected_tests" not in st.session_state:
    st.session_state.selected_tests = []

# Only allow adding tests if we have a price_dict
if price_dict:
    # ---- Add test section ----
    st.subheader("➕ Add a test")
    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("Enter test name (or part of it)", placeholder="e.g., cbc, ferritin, vitamin")
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

    # ---- Invoice display ----
    st.subheader("📋 Current invoice")
    if not st.session_state.selected_tests:
        st.info("No tests added yet.")
    else:
        data = []
        total = 0
        for name, price in st.session_state.selected_tests:
            data.append({"Test": name.title(), "Price (L.E.)": price})
            total += price
        df = pd.DataFrame(data)
        st.table(df)
        st.metric("Total", f"{total} L.E.")
        
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
else:
    st.info("Please upload the price list text file to begin.")
