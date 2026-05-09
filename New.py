import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Master Bank AI", layout="wide")
st.title("🏦 Universal Bank Statement AI")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    # The "BoB Fix": Strip letters like Cr/Dr/INR but keep decimal points
    s = str(val).upper().replace(',', '')
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    try: return float(match.group()) if match else 0.0
    except: return 0.0

def get_bank_type(text):
    text = text.upper()
    # Identification list
    if "BANK OF BARODA" in text or "BOB" in text: return "BOB"
    if "AXIS BANK" in text: return "AXIS"
    if "KOTAK" in text: return "KOTAK"
    if "HDFC BANK" in text: return "HDFC"
    if "ICICI BANK" in text: return "ICICI"
    if "BANDHAN" in text: return "BANDHAN"
    if "IDFC" in text: return "IDFC"
    if "YES BANK" in text: return "YES"
    return "GENERIC"

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        bank_type = get_bank_type(pdf.pages[0].extract_text() or "")
        
        for page in pdf.pages:
            # FORCE LATTICE for banks with strict grid lines (HDFC, BoB, Kotak)
            if bank_type in ["BOB", "HDFC", "KOTAK", "BANDHAN"]:
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            if not table: # Fallback for all
                table = page.extract_table()
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    # UNIVERSAL HEADER SEARCH
    header_idx = 0
    header_keywords = ['DATE', 'PARTICULARS', 'DESCRIPTION', 'WITHDRAWAL', 'DEBIT', 'NARRATION', 'TRAN DATE']
    for i, row in enumerate(all_rows[:40]):
        row_str = " ".join([str(x) for x in row if x]).upper()
        if any(k in row_str for k in header_keywords):
            header_idx = i
            break
            
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    # UNIVERSAL KEYWORD MAPPING
    mapping = {
        'date': ['TRAN DATE', 'DATE', 'TXN DATE', 'TRANSACTION DATE', 'VALUE DATE'],
        'desc': ['CHO.NO. NARRATION', 'NARRATION', 'PARTICULARS', 'DESCRIPTION', 'REMARKS', 'TRANSACTION DETAILS'],
        'dr': ['WITHDRAWAL DR)', 'WITHDRAWAL (DR)', 'WITHDRAWAL AMT.', 'DEBIT AMOUNT', 'DEBIT', 'WITHDRAWAL', 'DEBITS'],
        'cr': ['DEPOSIT(CR)', 'DEPOSIT (CR)', 'DEPOSIT AMT.', 'CREDIT AMOUNT', 'CREDIT', 'DEPOSIT', 'CREDITS'],
        'ind': ['CR/DR', 'INDICATOR', 'TYPE'] # For Axis/Generic
    }

    def find_col(keys):
        for k in keys:
            if k in headers: return k
        return None

    c_date, c_desc, c_dr, c_cr, c_ind = find_col(mapping['date']), find_col(mapping['desc']), find_col(mapping['dr']), find_col(mapping['cr']), find_col(mapping['ind'])

    extracted = []
    for row in data_rows:
        row_dict = dict(zip(headers, row))
        
        # Valid Date Anchor
        date_raw = str(row_dict.get(c_date, "")).strip()
        if not re.search(r'\d', date_raw): continue

        # Amount Detection
        dr_val = clean_val(row_dict.get(c_dr))
        cr_val = clean_val(row_dict.get(c_cr))
        
        nature, amount = "Check", 0.0
        
        # Scenario A: Separate Columns (Standard)
        if dr_val > 0: nature, amount = "Payment", dr_val
        elif cr_val > 0: nature, amount = "Receipt", cr_val
        
        # Scenario B: Indicator Column (Axis/BoB Single Column style)
        elif c_ind and row_dict.get(c_ind):
            ind = str(row_dict.get(c_ind)).upper()
            nature = "Receipt" if "CR" in ind else "Payment"
            # Get amount from whatever column has a value
            amount = dr_val if dr_val > 0 else cr_val

        # Scenario C: BoB Special (Cr/Dr inside Amount column)
        if amount == 0:
            for col in [c_dr, c_cr]:
                val_str = str(row_dict.get(col, "")).upper()
                if 'CR' in val_str: nature, amount = "Receipt", clean_val(val_str)
                elif 'DR' in val_str: nature, amount = "Payment", clean_val(val_str)

        if amount > 0:
            extracted.append({
                'Date': date_raw.split('\n')[0].strip(),
                'Description': str(row_dict.get(c_desc, "N/A")).replace('\n', ' ').strip(),
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(extracted), bank_type

if uploaded_file:
    try:
        df, b_type = process_pdf(uploaded_file)
        if df is not None and not df.empty:
            st.success(f"Parsing Complete for {b_type}")
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
            st.download_button("📥 Download Excel", out.getvalue(), "Final_Statement.xlsx")
        else:
            st.error("Could not find transactions. Please ensure the PDF is not a scanned image.")
    except Exception as e:
        st.error(f"System Error: {e}")