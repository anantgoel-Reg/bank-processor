import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="HDFC Fixed 16", layout="wide")
st.title("🏦 HDFC Bank - Strict Column Logic")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(val):
    if val is None: return 0.0
    # Direct cleanup: remove commas and whitespace
    clean = str(val).replace(',', '').strip()
    try: 
        return float(clean) if clean else 0.0
    except: 
        return 0.0

def process_hdfc(file):
    all_rows = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Force the PDF to be split into 7 specific columns
            # This prevents Withdrawal and Deposit from merging
            table = page.extract_table({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines"
            })
            
            if not table: continue

            for row in table:
                # 1. HDFC always has 7 columns. If it's not 7, it's not a transaction row.
                if len(row) != 7: continue
                
                # 2. Extract columns by index
                raw_date = str(row[0] or "").strip()
                narration = str(row[1] or "").replace('\n', ' ').strip()
                raw_withdrawal = row[4] # Column 5
                raw_deposit = row[5]    # Column 6
                
                # 3. Apply your Logic
                w_amt = clean_amt(raw_withdrawal)
                d_amt = clean_amt(raw_deposit)
                
                amount = 0.0
                nature = ""

                # IF COLUMN 4 (Withdrawal) HAS A VALUE -> PAYMENT
                if w_amt > 0:
                    nature = "Payment"
                    amount = w_amt
                # IF COLUMN 5 (Deposit) HAS A VALUE -> RECEIPT
                elif d_amt > 0:
                    nature = "Receipt"
                    amount = d_amt

                # 4. Filter for actual transactions (Must have amount and a date)
                if amount > 0 and re.search(r'\d{2}/\d{2}/\d{2}', raw_date):
                    all_rows.append({
                        "Date": raw_date.split('\n')[0],
                        "Description": narration,
                        "Nature": nature,
                        "Amount": amount
                    })
    
    return pd.DataFrame(all_rows)

if uploaded_file:
    try:
        final_df = process_hdfc(uploaded_file)
        
        if not final_df.empty:
            st.success(f"Successfully captured {len(final_df)} transactions.")
            
            # Summary validation
            t_rec = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Transactions", len(final_df)) # Should show 16
            c2.metric("Total Receipts", f"₹{t_rec:,.2f}")
            c3.metric("Total Payments", f"₹{t_pay:,.2f}")
            
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", out.getvalue(), "HDFC_Statement.xlsx")
        else:
            st.error("Could not find transactions. Is the PDF password protected?")
    except Exception as e:
        st.error(f"Error: {e}")