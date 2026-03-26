import streamlit as st
import re
from typing import Dict, List, Tuple

# ========================
# 1. Price list (embedded from your PDF)
# ========================

# I've copied the content of "Diamond Price List 2026.pdf" as a single string.
# You can also read it from a file if you prefer.
open("Diamond Price List 2026.txt").read()
===== Page 1 =====

 Printed In 28-Jan-2026  Current Page 1 from 13

## قائمة أسعار التحاليل الخاصة بالمرضى

Allergy Screen	Price	Result date	Collection notes	
IgE (immunoglobulin E specific food	2500 L.E.	5 Days	1 ml serum, refrigerated	
IgE (immunoglobulin E Specific	2000 L.E.	5 Days	1 ml serum, refrigerated	
Mixed Allergy Panel	3700 L.E.	3 Days	2 ml serum, refrigerated	
Pediatric Panel	2500 L.E.	5 Days	2 ml serum, refrigerated	
Antiphospholipid antibody syndrome	Price	Result date	Collection notes	
ACL IgG (Anti Cardiolipin IgG)	650 L.E.	1 Days	2 ml serum, refrigerated	
...
(Include the entire text from your PDF here. For brevity I've truncated, but you must insert the full text.)
...
"""

# ========================
# 2. Parse function
# ========================

@st.cache_data
def parse_price_list(text: str) -> Dict[str, int]:
    price_list = {}
    for line in text.splitlines():
        if not line.strip() or "Result date" in line or "Collection notes" in line or "Price" in line:
            continue
        matches = re.findall(r'(\d+)\s*L\.E\.', line)
        if matches:
            price = int(matches[-1])
            last_price_pos = line.rfind(matches[-1] + " L.E.")
            if last_price_pos == -1:
                last_price_pos = line.rfind(matches[-1] + "L.E.")
            if last_price_pos != -1:
                test_name = line[:last_price_pos].strip()
                test_name = re.sub(r'^\d+\.\s*', '', test_name)
                test_name = re.sub(r'\d+$', '', test_name).strip()
                if test_name and price > 0:
                    price_list[test_name.lower()] = price
    return price_list

def find_tests(partial: str, price_dict: Dict[str, int]) -> List[Tuple[str, int]]:
    partial_lower = partial.lower()
    return [(name, price) for name, price in price_dict.items() if partial_lower in name]

# ========================
# 3. Streamlit UI
# ========================

st.set_page_config(page_title="Medical Test Invoice", layout="wide")
st.title("🧾 Medical Test Invoice Generator")

# Load price list
price_dict = parse_price_list(PRICE_LIST_TEXT)
st.sidebar.success(f"✅ Loaded {len(price_dict)} tests")

# Initialize session state
if "selected_tests" not in st.session_state:
    st.session_state.selected_tests = []  # list of (name, price)

# ---- Main area: add test ----
st.subheader("Add a test")
col1, col2 = st.columns([3, 1])
with col1:
    search_term = st.text_input("Enter test name (or part of it)", placeholder="e.g., cbc, ferritin, vitamin")
with col2:
    add_button = st.button("➕ Add Test")

if add_button and search_term:
    # exact match first
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
            # show multiple matches
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
st.subheader("Current invoice")
if not st.session_state.selected_tests:
    st.info("No tests added yet.")
else:
    # Build table
    data = []
    total = 0
    for name, price in st.session_state.selected_tests:
        data.append({"Test": name.title(), "Price (L.E.)": price})
        total += price
    st.table(data)
    st.metric("Total", f"{total} L.E.")
    
    # Clear button
    if st.button("🗑️ Clear invoice"):
        st.session_state.selected_tests.clear()
        st.rerun()

# Optional: download invoice as text
if st.session_state.selected_tests:
    invoice_text = "MEDICAL TEST INVOICE\n" + "-"*30 + "\n"
    for name, price in st.session_state.selected_tests:
        invoice_text += f"{name.title()}: {price} L.E.\n"
    invoice_text += "-"*30 + f"\nTOTAL: {total} L.E."
    st.download_button("📄 Download invoice", invoice_text, file_name="invoice.txt")
