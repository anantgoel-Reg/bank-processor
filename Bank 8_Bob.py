import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Master Bank AI", layout="wide")
st.title("🏦 Universal Bank Statement AI")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    """
    Advanced cleaner: Extracts the first numeric sequence it finds, 
    ignoring 'Cr', 'Dr', commas, or extra text.
    """
    if val is None: return 0.0
    s = str(val).replace(',', '').strip()
    # Regex finds numbers like 123, 123.45, -123.45
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    try:
        return float(match.group()) if match else 0.0
    except:
        return 0.0

def get_bank_type(text):
    text = text.upper()
    if "BANK OF BARODA" in text or "BOB" in text: return "BOB"
    if "HDFC BANK" in text: return "HDFC"
    if "ICICI BANK" in text: return "ICICI"
    if "AXIS BANK" in text: return "AXIS"
    if "KOTAK" in text: return "KOTAK"
    if "BANDHAN" in text: return "BANDHAN"
    if "IDFC" in text: return "IDFC"
    return "UNKNOWN"

def process_pdf(file):
    all_rows = []
    bank_type = "UNKNOWN"
    
    with pdfplumber.open(file) as pdf:
        bank_type = get_bank_type(pdf.pages[0].extract_text() or "")
        
        for page in pdf.pages:
            # BoB and HDFC MUST use 'lines' strategy
            if bank_type in ["BOB", "HDFC", "KOTAK", "BANDHAN"]:
                table = page.extract_table(table_settings={
                    "vertical_strategy": "lines", 
                    "horizontal_strategy": "lines"
                })
            else:
                table = page.extract_table()
            
            if not table:
                table = page.extract_table() # Default fallback
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    # Step 1: Find the Header row
    header_idx = 0
    for i, row in enumerate(all_rows[:40]):
        row_str = " ".join([str(x) for x in row if x]).upper()
        if any(k in row_str for k in ['TRAN DATE', 'DATE', 'NARRATION', 'WITHDRAWAL']):
            header_idx = i
            break
            
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    # Step 2: Flexible Column Mapping
    mapping = {
        'date': ['TRAN DATE', 'DATE', 'TRANSACTION DATE'],
        'desc': ['CHO.NO. NARRATION', 'NARRATION', 'PARTICULARS', 'DESCRIPTION'],
        'dr': ['WITHDRAWAL DR)', 'WITHDRAWAL (DR)', 'DEBIT AMOUNT', 'DEBIT', 'WITHDRAWAL'],
        'cr': ['DEPOSIT(CR)', 'DEPOSIT (CR)', 'CREDIT AMOUNT', 'CREDIT', 'DEPOSIT']
    }

    def find_col(keys):
        for k in keys:
            if k in headers: return k
        return None

    c_date, c_desc, c_dr, c_cr = find_col(mapping['date']), find_col(mapping['desc']), find_col(mapping['dr']), find_col(mapping['cr'])

    # Step 3: Extract and Structure
    extracted = []
    for row in data_rows:
        row_dict = dict(zip(headers, row))
        
        # Check for date (BoB format is usually DD/MM/YYYY)
        raw_date = str(row_dict.get(c_date, "")).strip()
        if not re.search(r'\d', raw_date): continue

        dr_val = clean_val(row_dict.get(c_dr))
        cr_val = clean_val(row_dict.get(c_cr))
        
        nature, amount = None, 0.0
        if dr_val > 0:
            nature, amount = "Payment", dr_val
        elif cr_val > 0:
            nature, amount = "Receipt", cr_val

        if amount > 0:
            extracted.append({
                'Date': raw_date.split('\n')[0].strip(),
                'Description': str(row_dict.get(c_desc, "")).replace('\n', ' ').strip(),
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(extracted), bank_type

if uploaded_file:
    try:
        df, b_type = process_pdf(uploaded_file)
        if df is not None and not df.empty:
            st.info(f"Detected Bank: {b_type}")
            
            t_rec = df[df['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = df[df['Nature'] == 'Payment']['Amount'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Transactions", len(df))
            c2.metric("Total Receipts", f"₹{t_rec:,.2f}")
            c3.metric("Total Payments", f"₹{t_pay:,.2f}")
            
            st.dataframe(df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", out.getvalue(), "Bank_Statement_Final.xlsx")
        else:
            st.error("Table detected but no valid transactions found. Check headers.")
    except Exception as e:
        st.error(f"Error: {e}")