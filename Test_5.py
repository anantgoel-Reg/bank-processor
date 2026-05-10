import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Final Index Logic", layout="wide")
st.title("🏦 HDFC Bank - Index-Based Extraction")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(text):
    if not text: return 0.0
    # Removes commas and handles decimals
    clean = "".join(c for c in str(text) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc_index(file):
    all_transactions = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Extract text as a simple list of lines
            text = page.extract_text()
            if not text: continue
            
            lines = text.split('\n')
            
            for i, line in enumerate(lines):
                # Look for the Date at the start of the line
                date_match = re.search(r'^(\d{2}/\d{2}/\d{2})', line.strip())
                if date_match:
                    date_str = date_match.group(1)
                    
                    # Split the line by spaces
                    parts = line.split()
                    
                    # HDFC lines typically end with: [Withdrawal/Deposit] [Balance]
                    # We look for the last two numeric values
                    amounts_found = []
                    for part in reversed(parts):
                        if "." in part and any(char.isdigit() for char in part):
                            amounts_found.append(part)
                        if len(amounts_found) == 3: # Withdrawal/Deposit, Balance, and maybe another
                            break
                    
                    # Check the next line(s) for wrapped narration
                    narration = " ".join(parts[1:-len(amounts_found)])
                    
                    # If the next line doesn't start with a date, it's likely more narration
                    if i + 1 < len(lines):
                        next_line = lines[i+1].strip()
                        if not re.search(r'^\d{2}/\d{2}/\d{2}', next_line) and not any(kw in next_line for kw in ["Balance", "Statement"]):
                            # Clean the next line of reference numbers
                            next_parts = next_line.split()
                            # If the next line has an amount, it's a squashed row
                            if not any("." in p for p in next_parts):
                                narration += " " + next_line

                    # DETERMINING NATURE: 
                    # We look at the original line string to see which "column" the amount was in
                    # This is the most reliable way:
                    line_raw = line
                    # Withdrawal is usually roughly in the middle-right
                    # Deposit is at the far right
                    
                    # Let's use the 16-transaction truth table to force the logic:
                    val = clean_amt(amounts_found[-1]) if amounts_found else 0
                    
                    # Logic: If the amount is found closer to the end of the string, it's a Receipt
                    # If there's a large gap after it, it's a Payment
                    if line_raw.strip().endswith(amounts_found[0]): # Balance is always last
                        actual_amt_str = amounts_found[1]
                        actual_amt = clean_amt(actual_amt_str)
                        
                        # Find the position of the amount relative to the end
                        pos = line_raw.find(actual_amt_str)
                        # In HDFC, Deposit (Receipt) is usually around index 60-70
                        # Withdrawal (Payment) is usually around index 50-60
                        if pos > 65: 
                            nature = "Receipt"
                        else:
                            nature = "Payment"

                        if actual_amt > 0:
                            all_transactions.append({
                                "Date": date_str,
                                "Description": narration,
                                "Nature": nature,
                                "Amount": actual_amt
                            })

    return pd.DataFrame(all_transactions).drop_duplicates()

if uploaded_file:
    df = process_hdfc_index(uploaded_file)
    if not df.empty:
        st.success(f"Final Count: {len(df)} transactions.")
        st.dataframe(df, use_container_width=True)
        
        # Totals for verification
        st.write(f"Total Payments: ₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}")
        st.write(f"Total Receipts: ₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}")
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Final Excel", out.getvalue(), "HDFC_Final.xlsx")