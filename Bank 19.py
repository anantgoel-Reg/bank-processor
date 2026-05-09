import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Master Bank AI", layout="wide")
st.title("🏦 Universal Bank Statement AI (Fixed Mapping)")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    """Ensures only actual money values are captured, ignoring dates."""
    if val is None or str(val).strip() == "": return 0.0
    s = str(val).strip()
    
    # 1. DATE DETECTOR: If the cell has a date format (DD/MM), it's NOT money.
    if re.search(r'\d{1,2}[/-]\d{1,2}', s): return 0.0
    
    # 2. Extract digits and decimals only
    clean = "".join(c for c in s if c.isdigit() or c == '.')
    try:
        return float(clean) if clean else 0.0
    except:
        return 0.0

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Try Lattice for HDFC/Kotak, otherwise default
            table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            if not table or len(table) < 3:
                table = page.extract_table()
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    # Find Header Row
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join([str(x) for x in row if x]).upper()
        if 'DATE' in row_str and any(k in row_str for k in ['PARTICULARS', 'DESCRIPTION', 'REMARKS']):
            header_idx = i
            break
    
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    # --- THE FIXED UNIVERSAL MAPPING ---
    # We explicitly exclude any column that has 'DATE' or 'VALUE' in its name from being the 'Amount'
    col_map = {
        'date': next((i for i, h in enumerate(headers) if 'DATE' in h and 'VALUE' not in h), 
                     next((i for i, h in enumerate(headers) if 'DATE' in h), 0)),
        
        'desc': next((i for i, h in enumerate(headers) if any(k in h for k in ['DESC', 'PARTICULARS', 'REMARK', 'NARRATION'])), 1),
        
        # 'amt' MUST NOT contain 'DATE' or 'VALUE' or 'BALANCE'
        'amt': next((i for i, h in enumerate(headers) if 'AMOUNT' in h and not any(x in h for x in ['DATE', 'VALUE', 'BALANCE', 'CHQ'])), None),
        
        'ind': next((i for i, h in enumerate(headers) if any(k in h for k in ['CR/DR', 'DEBIT/CREDIT', 'TYPE'])), None),
        
        # Separate columns logic for HDFC/IDBI/Indian Bank
        'pay_cols': [i for i, h in enumerate(headers) if any(k in h for k in ['WITHDRAWAL', 'DEBIT', 'DR']) 
                     and not any(x in h for x in ['DATE', 'VALUE', 'BALANCE', 'CR/DR'])],
        
        'rec_cols': [i for i, h in enumerate(headers) if any(k in h for k in ['DEPOSIT', 'CREDIT', 'CR']) 
                     and not any(x in h for x in ['DATE', 'VALUE', 'BALANCE', 'CR/DR'])]
    }

    final_extracted = []
    current_txn = None

    for row in data_rows:
        row = [str(x).replace('\n', ' ').strip() if x else "" for x in row]
        if not any(row): continue
        
        has_date = len(re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', row[col_map['date']])) > 0
        
        # Calculate Row Amount
        row_amt = 0.0
        if col_map['amt'] is not None:
            row_amt = clean_val(row[col_map['amt']])
        else:
            vals = [clean_val(row[i]) for i in (col_map['pay_cols'] + col_map['rec_cols'])]
            row_amt = max(vals) if vals else 0.0

        if has_date and row_amt > 0:
            if current_txn: final_extracted.append(current_txn)
            
            # Determine Nature
            nature = "Payment"
            if col_map['ind'] is not None:
                ind = row[col_map['ind']].upper()
                nature = "Receipt" if any(k in ind for k in ['CR', 'CREDIT']) else "Payment"
            else:
                if any(clean_val(row[i]) > 0 for i in col_map['rec_cols']):
                    nature = "Receipt"

            current_txn = {
                'Date': row[col_map['date']].split()[-1], # Handles ID+Date cells
                'Description': row[col_map['desc']],
                'Nature': nature,
                'Amount': row_amt
            }
        elif current_txn and row[col_map['desc']] and not has_date:
            current_txn['Description'] += " " + row[col_map['desc']]

    if current_txn: final_extracted.append(current_txn)
    return pd.DataFrame(final_extracted)

if uploaded_file:
    try:
        df = process_pdf(uploaded_file)
        if df is not None and not df.empty:
            st.success(f"Captured {len(df)} transactions")
            st.dataframe(df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 Download Final Excel", out.getvalue(), "Statement_Fixed.xlsx")
    except Exception as e:
        st.error(f"Error: {e}")