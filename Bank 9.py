import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Master Bank AI v3", layout="wide")
st.title("🏦 Universal Bank Statement AI (Fixed for HDFC/IDBI/Indian)")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    if val is None: return 0.0
    s = str(val).upper().replace(',', '')
    # Specific fix for Indian Bank & IDBI: Remove 'INR' and 'CR'/'DR'
    s = s.replace('INR', '').replace('CR', '').replace('DR', '').strip()
    if s in ["", "-", "0", "0.00"]: return 0.0
    # Extract only numbers and decimal point
    clean = "".join(re.findall(r"[-+]?\d*\.\d+|\d+", s))
    try: return float(clean)
    except: return 0.0

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Try Lattice for HDFC, then Stream for others
            table = page.extract_table() or page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            if table: all_rows.extend(table)
    
    if not all_rows: return None
    df = pd.DataFrame(all_rows)

    # Smart Header Search
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join(map(str, row)).upper()
        if any(k in row_str for k in ['DATE', 'PARTICULARS', 'TRANSACTION DETAILS', 'NARRATION']):
            header_idx = i
            break
    
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    df = df[header_idx + 1:].reset_index(drop=True)

    # Mapping for the specific banks that were failing
    pay_keys = ['WITHDRAWAL AMT.', 'WITHDRAWALS', 'DEBITS', 'DEBIT', 'WITHDRAWAL', 'DEBIT AMOUNT']
    rec_keys = ['DEPOSIT AMT.', 'DEPOSITS', 'CREDITS', 'CREDIT', 'DEPOSIT', 'CREDIT AMOUNT']
    desc_keys = ['NARRATION', 'PARTICULARS', 'TRANSACTION DETAILS', 'DESCRIPTION', 'REMARKS']

    extracted = []
    for _, row in df.iterrows():
        nature, amount = "", 0.0
        
        # Check for Payments (Dr)
        for k in pay_keys:
            if k in df.columns:
                v = clean_val(row[k])
                if v > 0: nature, amount = "Payment", v
        
        # Check for Receipts (Cr) - Overwrites if both exist, but usually exclusive
        for k in rec_keys:
            if k in df.columns:
                v = clean_val(row[k])
                if v > 0: nature, amount = "Receipt", v

        # Extract Description
        desc = "N/A"
        for k in desc_keys:
            if k in df.columns and row[k]:
                desc = str(row[k]).replace('\n', ' ').strip()
                break

        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")

        if amount > 0 and desc != "N/A":
            extracted.append({'Date': date, 'Description': desc, 'Nature': nature, 'Amount': amount})

    return pd.DataFrame(extracted)

if uploaded_file:
    try:
        res = process_pdf(uploaded_file)
        if res is not None and not res.empty:
            t_rec = res[res['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = res[res['Nature'] == 'Payment']['Amount'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Transactions", len(res))
            c2.metric("Total Receipts", f"₹{t_rec:,.2f}")
            c3.metric("Total Payments", f"₹{t_pay:,.2f}")
            
            st.dataframe(res, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                res.to_excel(writer, index=False)
            st.download_button("📥 Download Standardized Excel", out.getvalue(), "Bank_Report.xlsx")
        else:
            st.warning("No transactions found. Check if the PDF is a scanned image.")
    except Exception as e:
        st.error(f"Error processing: {e}")