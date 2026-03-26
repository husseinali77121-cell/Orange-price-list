import streamlit as st
import re
from typing import Dict, List, Tuple

# ========================
# 1. Load and parse price list
# ========================

@st.cache_data
def parse_price_list(file_path: str) -> Dict[str, int]:
    """Read the text file and return a dict {test_name_lowercase: price}."""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    price_dict = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        # Skip lines that are likely headers or footers
        if any(header in line for header in ["Result date", "Collection notes", "Price", "Page"]):
            continue
        
        # Look for a number followed by "L.E."
        matches = re.findall(r'(\d+)\s*L\.E\.', line)
        if matches:
            # Assume the last occurrence is the actual price
            price = int(matches[-1])
            # Find the position of that price in the line
            last_price_pos = line.rfind(matches[-1] + " L.E.")
            if last_price_pos == -1:
                last_price_pos = line.rfind(matches[-1] + "L.E.")
            if last_price_pos != -1:
                test_name = line[:last_price_pos].strip()
                # Clean up the name: remove leading numbers, trailing digits, extra spaces
                test_name = re.sub(r'^\d+\.\s*', '', test_name)
                test_name = re.sub(r'\d+$', '', test_name).strip()
                if test_name and price > 0:
                    price_dict[test_name.lower()] = price
    return price_dict

def find_tests(partial: str, price_dict: Dict[str, int]) -> List[Tuple[str, int]]:
    """Return all tests whose name contains partial (case-insensitive)."""
    partial_lower = partial.lower()
    return [(name, price) for name, price in price_dict.items() if partial_lower in name]

# ========================
# 2. Streamlit UI
# ========================

st.set_page_config(page_title="Medical Test Invoice", layout="wide")
st.title("🧾 Medical Test Invoice Generator")

# Load price list (update the path if needed)
PRICE_FILE = "Diamond Price List 2026.txt"
try:
    price_dict = parse_price_list(PRICE_FILE)
    st.sidebar.success(f"✅ Loaded {len(price_dict)} tests")
except FileNotFoundError:
    st.error(f"❌ File '{PRICE_FILE}' not found. Please ensure it is in the same directory.")
    st.stop()

# Initialize session state
if "selected_tests" not in st.session_state:
    st.session_state.selected_tests = []  # list of (name, price)

# ---- Add test section ----
st.subheader("Add a test")
col1, col2 = st.columns([3, 1])
with col1:
    search_term = st.text_input("Enter test name (or part of it)", placeholder="e.g., cbc, ferritin, vitamin")
with col2:
    add_button = st.button("➕ Add Test")

if add_button and search_term:
    # Try exact match first
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
            # Show multiple matches
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

# ---- Optional download ----
if st.session_state.selected_tests:
    invoice_text = "MEDICAL TEST INVOICE\n" + "-"*30 + "\n"
    for name, price in st.session_state.selected_tests:
        invoice_text += f"{name.title()}: {price} L.E.\n"
    invoice_text += "-"*30 + f"\nTOTAL: {total} L.E."
    st.download_button("📄 Download invoice", invoice_text, file_name="invoice.txt")
