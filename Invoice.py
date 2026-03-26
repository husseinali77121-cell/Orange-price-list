import re
from typing import Dict, List, Tuple

# ========================
# 1. Parse the price list
# ========================

def parse_price_list(text: str) -> Dict[str, int]:
    """
    Extract test names and prices from the given text.
    Returns a dictionary mapping test name (lowercase) to price in L.E.
    """
    price_list = {}
    for line in text.splitlines():
        if not line.strip() or "Result date" in line or "Collection notes" in line or "Price" in line:
            continue
        # Find all occurrences of a number followed by "L.E." in the line
        matches = re.findall(r'(\d+)\s*L\.E\.', line)
        if matches:
            price = int(matches[-1])
            # Extract test name: everything before the last price + "L.E." occurrence
            last_price_pos = line.rfind(matches[-1] + " L.E.")
            if last_price_pos == -1:
                last_price_pos = line.rfind(matches[-1] + "L.E.")
            if last_price_pos != -1:
                test_name = line[:last_price_pos].strip()
                # Clean up test name: remove leading numbers and trailing digits
                test_name = re.sub(r'^\d+\.\s*', '', test_name)
                test_name = re.sub(r'\d+$', '', test_name).strip()
                if test_name and price > 0:
                    price_list[test_name.lower()] = price
    return price_list

# ========================
# 2. Search functions
# ========================

def find_tests(partial: str, price_dict: Dict[str, int]) -> List[Tuple[str, int]]:
    """Return list of (test_name, price) where test_name contains partial (case-insensitive)."""
    partial_lower = partial.lower()
    return [(name, price) for name, price in price_dict.items() if partial_lower in name]

# ========================
# 3. Interactive invoice
# ========================

def show_invoice(items: List[Tuple[str, int]], total: int):
    """Print a formatted invoice."""
    print("\n" + "="*50)
    print("INVOICE".center(50))
    print("="*50)
    print(f"{'Test Name':<40} {'Price (L.E.)':>10}")
    print("-"*50)
    for name, price in items:
        display_name = name.title()
        print(f"{display_name:<40} {price:>10}")
    print("-"*50)
    print(f"{'TOTAL':<40} {total:>10}")
    print("="*50)

def main():
    # Load the price list from the provided text file
    try:
        with open("Diamond Price List 2026.txt", "r", encoding="utf-8") as f:
            raw_text = f.read()
    except FileNotFoundError:
        print("Error: 'Diamond Price List 2026.txt' not found. Please ensure the file is in the same directory.")
        return

    price_dict = parse_price_list(raw_text)
    print(f"Loaded {len(price_dict)} test entries.")

    selected = []
    while True:
        print("\nOptions:")
        print("1. Add a test")
        print("2. Show current invoice")
        print("3. Clear invoice")
        print("4. Exit")
        choice = input("Enter choice (1-4): ").strip()
        if choice == "1":
            test_input = input("Enter test name (or part of it): ").strip()
            if not test_input:
                continue
            # First try exact match
            key = test_input.lower()
            if key in price_dict:
                price = price_dict[key]
                selected.append((key, price))
                print(f"Added {test_input}: {price} L.E.")
                continue

            # Partial search
            matches = find_tests(test_input, price_dict)
            if not matches:
                print("No tests found matching that name.")
                continue

            if len(matches) == 1:
                name, price = matches[0]
                selected.append((name, price))
                print(f"Added {name.title()}: {price} L.E.")
            else:
                print(f"Multiple tests found for '{test_input}':")
                for idx, (name, price) in enumerate(matches[:20], 1):  # show up to 20
                    print(f"  {idx}. {name.title()} - {price} L.E.")
                choice_idx = input("Enter the number of the test to add (or 0 to cancel): ").strip()
                if choice_idx.isdigit():
                    idx = int(choice_idx)
                    if 1 <= idx <= len(matches):
                        name, price = matches[idx-1]
                        selected.append((name, price))
                        print(f"Added {name.title()}: {price} L.E.")
                    elif idx != 0:
                        print("Invalid number.")
                else:
                    print("Invalid input.")
        elif choice == "2":
            if not selected:
                print("No tests added yet.")
            else:
                total = sum(price for _, price in selected)
                show_invoice(selected, total)
        elif choice == "3":
            selected.clear()
            print("Invoice cleared.")
        elif choice == "4":
            print("Goodbye!")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()