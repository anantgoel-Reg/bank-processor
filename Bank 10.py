import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Universal Bank AI", layout="wide")
st.title("🏦 Universal Bank Statement AI")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def deep_clean_amount(val):
    """Extreme cleaning for Indian Bank (INR), IDBI (Cr/Dr), and HDFC (commas)"""
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: 
        return 0.0
    
    # Remove text like 'INR', 'Cr', 'Dr', and commas
    text = str(val).upper()
    text = text.replace('INR', '').replace('CR', '').replace('DR', '').replace(',', '').strip()
    
    # Extract only the numbers and decimal
    clean = "".join(re.findall(r"[-+]?\d*\.\d+|\d+", text))
    try:
        return float(clean)
    except:
        return 0.0

def get_table_data(pdf):
    """Tries 3 different ways to find a table so no bank is missed"""
    for page in pdf.pages:
        # Strategy 1: Default
        table = page.extract_table()
        if table and len(table) > 1: return table
        
        # Strategy 2: Lattice (For HDFC/Kotak lines)
        table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
        if table and len(table) > 1: return table
        
        # Strategy 3: Stream (For IDBI/Indian/Bandhan text alignment)
        table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
        if table and len(table) > 1: return table
    return None

def process_pdf(file):
    with pdfplumber.open(file) as pdf:
        all_rows = []
        for page in pdf.pages:
            # Try combined strategies per page
            table = page.extract_table() or \
                    page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            if table:
                all_rows.extend(table)
        
        if not all_rows: return None

        df = pd.DataFrame(all_rows)
        
        # Find Header Row
        header_idx = 0
        for i, row in enumerate(all_rows):
            row_str = " ".join(map(str, row)).upper()
            if any(k in row_str for k in ['DATE', 'PARTICULARS', 'DESCRIPTION', 'WITHDRAWAL', 'DEBIT']):
                header_idx = i
                break
        
        df.columns = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
        df = df[header_idx + 1:].reset_index(drop=True)

        # COMPREHENSIVE KEY MAPPING
        pay_keys = ['WITHDRAWAL', 'WITHDRAWAL (DR.)', 'WITHDRAWAL (DR)', 'WITHDRAWAL AMT.', 'WITHDRAWALS', 'DEBIT', 'DEBITS', 'DEBIT AMOUNT']
        rec_keys = ['DEPOSIT', 'DEPOSIT (CR.)', 'DEPOSIT (CR)', 'DEPOSIT AMT.', 'DEPOSITS', 'CREDIT', 'CREDITS', 'CREDIT AMOUNT']
        desc_keys = ['PARTICULARS', 'DESCRIPTION', 'REMARKS', 'NARRATION', 'TRANSACTION DETAILS']

        final_data = []
        for _, row in df.iterrows():
            nature, amount = "", 0.0
            
            # Check Payments
            for k in pay_keys:
                if k in df.columns:
                    v = deep_clean_amount(row[k])
                    if v > 0: nature, amount = "Payment", v
            
            # Check Receipts
            for k in rec_keys:
                if k in df.columns:
                    v = deep_clean_amount(row[k])
                    if v > 0: nature, amount = "Receipt", v

            # Date & Description
            date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
            desc = "N/A"
            for k in desc_keys:
                if k in df.columns and row[k]:
                    desc = str(row[k]).replace('\n', ' ').strip()
                    break

            if amount > 0:
                final_data.append({'Date': str(date), 'Description': desc, 'Nature': nature, 'Amount': amount})

        return pd.DataFrame(final_data)

if uploaded_file:
    try:
        res = process_pdf(uploaded_file)
        if res is not None and not res.empty:
            # Dashboard Metrics
            t_rec = res[res['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = res[res['Nature'] == 'Payment']['Amount'].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Transactions", len(res))
            c2.metric("Total Receipts", f"₹{t_rec:,.2f}")
            c3.metric("Total Payments", f"₹{t_pay:,.2f}")

            st.dataframe(res, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                res.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", out.getvalue(), "Statement_Final.xlsx")
        else:
            st.warning("Could not extract data. Ensure the PDF is not a scanned image.")
    except Exception as e:
        st.error(f"Error: {e}")