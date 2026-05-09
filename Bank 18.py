import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Universal Bank AI", layout="wide")
st.title("🏦 Keyword-Driven Bank Statement AI")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

# --- YOUR KEYWORD LISTS ---
KEYWORDS_PAYMENT = ['WITHDRAWAL', 'DEBIT', 'DR', 'PAYMENT']
KEYWORDS_RECEIPT = ['DEPOSIT', 'CREDIT', 'CR', 'RECEIPT']
KEYWORDS_DESC = ['PARTICULARS', 'DESCRIPTION', 'REMARKS', 'NARRATION', 'TRANSACTION DETAILS']
KEYWORDS_INDICATOR = ['CR/DR', 'DEBIT/CREDIT', 'TYPE']
KEYWORDS_AMOUNT = ['AMOUNT', 'VALUE']

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    # Strip non-numeric chars but keep the decimal point
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean)
    except: return 0.0

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Multi-strategy extraction
            table = page.extract_table()
            if not table or len(table) < 3:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    # 1. FIND HEADER ROW
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join(map(str, row)).upper()
        if 'DATE' in row_str and any(k in row_str for k in KEYWORDS_DESC):
            header_idx = i
            break
    
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    # 2. DYNAMIC MAPPING
    col_map = {
        'date': next((i for i, h in enumerate(headers) if 'DATE' in h), 0),
        'desc': next((i for i, h in enumerate(headers) if any(k in h for k in KEYWORDS_DESC)), 1),
        'amt': next((i for i, h in enumerate(headers) if any(k in h for k in KEYWORDS_AMOUNT) and 'BALANCE' not in h), None),
        'ind': next((i for i, h in enumerate(headers) if any(k in h for k in KEYWORDS_INDICATOR)), None),
        'pay_cols': [i for i, h in enumerate(headers) if any(k in h for k in KEYWORDS_PAYMENT) and 'BALANCE' not in h and 'CR/DR' not in h and 'DEBIT/CREDIT' not in h],
        'rec_cols': [i for i, h in enumerate(headers) if any(k in h for k in KEYWORDS_RECEIPT) and 'BALANCE' not in h and 'CR/DR' not in h and 'DEBIT/CREDIT' not in h]
    }

    final_extracted = []
    current_txn = None

    # 3. BUFFERED PROCESSING
    for row in data_rows:
        row = [str(x).replace('\n', ' ').strip() if x else "" for x in row]
        
        # Check if row starts a new transaction (Has a Date)
        has_date = len(re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', row[col_map['date']])) > 0
        
        # Calculate amount for this specific row
        row_amt = 0.0
        if col_map['amt'] is not None:
            row_amt = clean_val(row[col_map['amt']])
        else:
            # Check all detected Payment/Receipt columns
            row_amt = max([clean_val(row[i]) for i in (col_map['pay_cols'] + col_map['rec_cols'])] + [0.0])

        if has_date and row_amt > 0:
            if current_txn: final_extracted.append(current_txn)
            
            # Determine Nature
            nature = "Payment"
            if col_map['ind'] is not None:
                ind_val = row[col_map['ind']].upper()
                nature = "Receipt" if any(k in ind_val for k in ['CR', 'RECEIPT', 'CREDIT']) else "Payment"
            else:
                # Check if value sits in a Receipt-labeled column
                if any(clean_val(row[i]) > 0 for i in col_map['rec_cols']):
                    nature = "Receipt"

            current_txn = {
                'Date': row[col_map['date']].split()[-1], # Handles ID+Date cells
                'Description': row[col_map['desc']],
                'Nature': nature,
                'Amount': row_amt
            }
        elif current_txn and row[col_map['desc']] and not has_date:
            # Append multi-line description text to the active transaction
            current_txn['Description'] += " " + row[col_map['desc']]

    if current_txn: final_extracted.append(current_txn)
    return pd.DataFrame(final_extracted)

if uploaded_file:
    try:
        final_df = process_pdf(uploaded_file)
        if final_df is not None and not final_df.empty:
            st.success(f"Successfully extracted {len(final_df)} transactions!")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Count", len(final_df))
            c2.metric("Total Receipts", f"₹{final_df[final_df['Nature']=='Receipt']['Amount'].sum():,.2f}")
            c3.metric("Total Payments", f"₹{final_df[final_df['Nature']=='Payment']['Amount'].sum():,.2f}")
            
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Download Standardized Excel", out.getvalue(), "Processed_Statement.xlsx")
        else:
            st.warning("No transactions found. Please ensure the PDF is not a scanned image.")
    except Exception as e:
        st.error(f"Error: {e}")