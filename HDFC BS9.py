import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Precision Fix", layout="wide")
st.title("🏦 HDFC Bank - Line-by-Line Alignment")

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
                
                # Identify if this row contains a date
                if not re.search(r'\d', str(row[0])): continue
                if "Date" in str(row[0]): continue

                # THE FIX: Split every cell by newline to handle "squashed" rows
                dates = str(row[0]).split('\n')
                narrations = str(row[1]).split('\n')
                withdrawals = str(row[4]).split('\n')
                deposits = str(row[5]).split('\n')

                # Find how many lines are in this visual row
                max_lines = max(len(dates), len(withdrawals), len(deposits))

                for i in range(max_lines):
                    # Get specific data for THIS line only
                    d_val = dates[i].strip() if i < len(dates) else dates[0].strip()
                    n_val = narrations[i].strip() if i < len(narrations) else " ".join(narrations).strip()
                    w_val = clean_amt(withdrawals[i]) if i < len(withdrawals) else 0.0
                    dep_val = clean_amt(deposits[i]) if i < len(deposits) else 0.0

                    # Apply your exact column logic
                    amount = 0.0
                    nature = ""

                    if w_val > 0:
                        nature = "Payment"
                        amount = w_val
                    elif dep_val > 0:
                        nature = "Receipt"
                        amount = dep_val

                    # Only add if an amount is found on this specific line
                    if amount > 0:
                        final_data.append({
                            "Date": d_val,
                            "Description": n_val,
                            "Nature": nature,
                            "Amount": amount
                        })

    return pd.DataFrame(final_data)

if uploaded_file:
    df = process_hdfc(uploaded_file)
    if not df.empty:
        st.success(f"Captured {len(df)} transactions with unique details.")
        
        # Summary for validation against your statement [cite: 42, 43, 44, 45]
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Count", len(df)) # Should be 16
        c2.metric("Total Payments", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") # Target: 31,245.02
        c3.metric("Total Receipts", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") # Target: 60,002.00
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Corrected Excel", out.getvalue(), "HDFC_Line_Corrected.xlsx")