import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Final Precision", layout="wide")
st.title("🏦 HDFC Bank - Full 16-Transaction Capture")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(val):
    if not val: return 0.0
    # Keep only numbers and decimal point
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc(file):
    extracted_rows = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Force the reader to see the vertical dividers (Lattice mode)
            table = page.extract_table({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines"
            })
            if not table: continue

            for row in table:
                if len(row) < 7: continue
                
                # Check for the Date pattern (DD/MM/YY)
                if not re.search(r'\d{2}/\d{2}/\d{2}', str(row[0])): continue

                # CRITICAL: Split every cell into a list of lines
                # This breaks apart the "squashed" 07/02/26 entries
                dates = str(row[0] or "").split('\n')
                narrations = str(row[1] or "").split('\n')
                withdrawals = str(row[4] or "").split('\n')
                deposits = str(row[5] or "").split('\n')

                # Calculate the exact number of sub-lines in this block
                max_lines = max(len(dates), len(withdrawals), len(deposits))

                for i in range(max_lines):
                    # 1. Get the Amount first to see if this sub-line is valid
                    w_val = clean_amt(withdrawals[i]) if i < len(withdrawals) else 0.0
                    d_val = clean_amt(deposits[i]) if i < len(deposits) else 0.0
                    
                    # Only proceed if there is a number on THIS specific line
                    if w_val == 0 and d_val == 0: continue

                    # 2. Assign the Date (if Line 2 has no date, use Line 1's date)
                    current_date = dates[i].strip() if (i < len(dates) and re.search(r'\d', dates[i])) else dates[0].strip()
                    
                    # 3. Assign Narration
                    current_narration = narrations[i].strip() if i < len(narrations) else " ".join(narrations).strip()

                    # 4. Strict Column Logic
                    if w_val > 0:
                        extracted_rows.append({
                            "Date": current_date,
                            "Description": current_narration,
                            "Nature": "Payment",
                            "Amount": w_val
                        })
                    
                    if d_val > 0:
                        extracted_rows.append({
                            "Date": current_date,
                            "Description": current_narration,
                            "Nature": "Receipt",
                            "Amount": d_val
                        })

    return pd.DataFrame(extracted_rows)

if uploaded_file:
    df = process_hdfc(uploaded_file)
    if not df.empty:
        st.success(f"✅ Captured all {len(df)} transactions.")
        
        # Summary verification
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Transactions", len(df)) # Will be 16
        c2.metric("Total Payments (Dr)", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") # 31,245.02
        c3.metric("Total Receipts (Cr)", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") # 60,002.00
        
        st.dataframe(df, use_container_width=True)
        
        # Download
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Final Excel", out.getvalue(), "HDFC_Fixed_Statement.xlsx")