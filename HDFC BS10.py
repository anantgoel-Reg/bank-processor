import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Final Fix", layout="wide")
st.title("🏦 HDFC Bank - Full Capture (Payments & Receipts)")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(val):
    if not val: return 0.0
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc(file):
    final_data = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            table = page.extract_table({"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            if not table: continue

            for row in table:
                if len(row) < 7: continue
                
                # Check if row starts with a date pattern (e.g., 19/01/26)
                if not re.search(r'\d{2}/\d{2}/\d{2}', str(row[0])): continue

                # Split squashed cells into lists
                dates = str(row[0]).split('\n')
                narrations = str(row[1]).split('\n')
                withdrawals = str(row[4]).split('\n')
                deposits = str(row[5]).split('\n')

                # Calculate the maximum number of entries in this row
                max_lines = max(len(dates), len(withdrawals), len(deposits))

                for i in range(max_lines):
                    # 1. Get the Date (use first date if sub-lines don't have their own)
                    d_val = dates[i].strip() if (i < len(dates) and dates[i].strip()) else dates[0].strip()
                    
                    # 2. Get Narration
                    n_val = narrations[i].strip() if i < len(narrations) else " ".join(narrations).strip()
                    
                    # 3. Check Withdrawal (Payment)
                    w_val = clean_amt(withdrawals[i]) if i < len(withdrawals) else 0.0
                    
                    # 4. Check Deposit (Receipt)
                    dep_val = clean_amt(deposits[i]) if i < len(deposits) else 0.0

                    # LOGIC: Record Payment if Withdrawal > 0
                    if w_val > 0:
                        final_data.append({
                            "Date": d_val,
                            "Description": n_val,
                            "Nature": "Payment",
                            "Amount": w_val
                        })
                    
                    # LOGIC: Record Receipt if Deposit > 0
                    if dep_val > 0:
                        final_data.append({
                            "Date": d_val,
                            "Description": n_val,
                            "Nature": "Receipt",
                            "Amount": dep_val
                        })

    return pd.DataFrame(final_data)

if uploaded_file:
    df = process_hdfc(uploaded_file)
    if not df.empty:
        # Match against your specific statement summary 
        st.success(f"Captured {len(df)} total transactions.")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Count", len(df)) # Target: 16 (11 Dr, 5 Cr) [cite: 42, 43]
        c2.metric("Total Payments (Dr)", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") # Target: 31,245.02 [cite: 44]
        c3.metric("Total Receipts (Cr)", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") # Target: 60,002.00 [cite: 45]
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", out.getvalue(), "HDFC_Corrected_Final.xlsx")