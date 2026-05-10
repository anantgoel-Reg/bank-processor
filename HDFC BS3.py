import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="HDFC Fixed 16", layout="wide")
st.title("🏦 HDFC Bank Statement - Full 16 Transaction Fix")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(val):
    if val is None: return 0.0
    # Keep only numbers and decimals
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc(file):
    all_transactions = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Using 'lattice' settings to ensure columns stay separated
            table = page.extract_table({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines"
            })
            if not table: continue
            
            # 1. Locate Headers
            h_idx = -1
            for i, row in enumerate(table):
                row_str = " ".join(str(c) for c in row if c).upper()
                if "WITHDRAWAL" in row_str and "DEPOSIT" in row_str:
                    headers = [str(c).replace('\n', ' ').strip().upper() for c in row]
                    h_idx = i
                    break
            
            if h_idx == -1: continue
            
            # 2. Get Column Positions
            try:
                d_idx = next(i for i, h in enumerate(headers) if 'DATE' in h)
                n_idx = next(i for i, h in enumerate(headers) if 'NARRATION' in h)
                w_idx = next(i for i, h in enumerate(headers) if 'WITHDRAWAL' in h)
                c_idx = next(i for i, h in enumerate(headers) if 'DEPOSIT' in h)
            except: continue

            # 3. Extract Every Line
            for row in table[h_idx + 1:]:
                # Skip if row is empty or malformed
                if len(row) < 4: continue
                
                date_cell = str(row[d_idx] or "").strip()
                narration = str(row[n_idx] or "").replace('\n', ' ').strip()
                
                # GET THE NUMBERS
                w_amt = clean_amt(row[w_idx])
                d_amt = clean_amt(row[c_idx])
                
                # SIMPLE BIFURCATION
                amount = 0.0
                nature = ""

                if w_amt > 0:
                    nature = "Payment"
                    amount = w_amt
                elif d_amt > 0:
                    nature = "Receipt"
                    amount = d_amt

                # Only add if we found a valid amount and a date exists
                if amount > 0 and re.search(r'\d', date_cell):
                    all_transactions.append({
                        "Date": date_cell.split('\n')[0],
                        "Description": narration,
                        "Nature": nature,
                        "Amount": amount
                    })

    return pd.DataFrame(all_transactions)

if uploaded_file:
    try:
        df = process_hdfc(uploaded_file)
        if not df.empty:
            # Totals for validation against your screenshot
            t_rec = df[df['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = df[df['Nature'] == 'Payment']['Amount'].sum()
            
            st.success(f"✅ Successfully extracted {len(df)} transactions.")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Transactions", len(df)) # Should show 16
            c2.metric("Total Receipts (Cr)", f"₹{t_rec:,.2f}") # Should be 60,002.00
            c3.metric("Total Payments (Dr)", f"₹{t_pay:,.2f}") # Should be 31,245.02
            
            st.dataframe(df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", out.getvalue(), "HDFC_Final_16.xlsx")
        else:
            st.warning("No transactions found.")
    except Exception as e:
        st.error(f"Error: {e}")