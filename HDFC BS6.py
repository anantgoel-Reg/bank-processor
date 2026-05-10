import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="HDFC Simple Logic", layout="wide")
st.title("🏦 HDFC Bank Statement - Simple Logic")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(val):
    if val is None: return 0.0
    # Keep only digits and decimal point
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc(file):
    all_rows = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # We use 'lattice' mode to ensure the grid stays in 7 columns
            table = page.extract_table({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines"
            })
            
            if not table: continue

            for row in table:
                # 1. HDFC Statements have 7 columns. We skip rows that aren't table data.
                if len(row) < 7: continue
                
                # 2. Skip the header row itself
                if "Narration" in str(row[1]): continue
                
                date_val = str(row[0] or "").strip()
                narration = str(row[1] or "").replace('\n', ' ').strip()
                
                # 3. APPLY YOUR LOGIC DIRECTLY
                # Index 4 = Withdrawal Amt. | Index 5 = Deposit Amt.
                withdrawal = clean_amt(row[4])
                deposit = clean_amt(row[5])
                
                amount = 0.0
                nature = ""

                if withdrawal > 0:
                    nature = "Payment"
                    amount = withdrawal
                elif deposit > 0:
                    nature = "Receipt"
                    amount = deposit

                # 4. Only save if an amount was found and the row has a date
                if amount > 0 and re.search(r'\d', date_val):
                    all_rows.append({
                        "Date": date_val.split('\n')[0],
                        "Description": narration,
                        "Nature": nature,
                        "Amount": amount
                    })
    
    return pd.DataFrame(all_rows)

if uploaded_file:
    try:
        final_df = process_hdfc(uploaded_file)
        
        if not final_df.empty:
            st.success(f"Done! Found {len(final_df)} transactions.")
            
            # This should now show 16 (11 Payments + 5 Receipts)
            c1, c2, c3 = st.columns(3)
            c1.metric("Transactions", len(final_df))
            c2.metric("Total Receipts", f"₹{final_df[final_df['Nature'] == 'Receipt']['Amount'].sum():,.2f}")
            c3.metric("Total Payments", f"₹{final_df[final_df['Nature'] == 'Payment']['Amount'].sum():,.2f}")
            
            st.dataframe(final_df, use_container_width=True)
            
            # Export to Excel
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", out.getvalue(), "HDFC_Simple_Logic.xlsx")
        else:
            st.error("No transactions found. Please check the PDF.")
    except Exception as e:
        st.error(f"System Error: {e}")