import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="AI Bank Statement Master", layout="wide")
st.title("🏦 Universal Bank Statement Processor")

uploaded_file = st.file_uploader("Upload Bank PDF (Axis, HDFC, ICICI, SBI, etc.)", type="pdf")

def clean_val(val):
    if val is None: return 0.0
    s = str(val).replace(',', '').replace('INR', '').strip()
    if not s or s.lower() in ["none", "-", "0.00", "0"]: return 0.0
    # Guard: if it's a date or timestamp, it's not money
    if re.search(r'\d{1,2}[/-]\d{1,2}', s) and len(s) > 5: return 0.0
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    try: return float(nums[0]) if nums else 0.0
    except: return 0.0

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Axis/HDFC Fix: Try multiple table settings per page
            table = page.extract_table(table_settings={
                "vertical_strategy": "lines", 
                "horizontal_strategy": "lines"
            })
            if not table or len(table) < 2:
                table = page.extract_table()
            
            if table:
                # Clean nested newlines that cause column shifts
                cleaned_table = [[str(cell).replace('\n', ' ') if cell else "" for cell in row] for row in table]
                all_rows.extend(cleaned_table)
    
    if not all_rows: return None

    # 1. DYNAMIC HEADER SEARCH
    header_idx = None
    for i, row in enumerate(all_rows[:30]): # Look deeper for HDFC/Axis
        row_str = " ".join(row).upper()
        if any(k in row_str for k in ['PARTICULARS', 'DESCRIPTION', 'NARRATION']):
            if any(k in row_str for k in ['DEBIT', 'WITHDRAWAL', 'CREDIT', 'DEPOSIT', 'AMOUNT']):
                header_idx = i
                break
                
    if header_idx is None: return None

    headers = all_rows[header_idx]
    data_rows = all_rows[header_idx + 1:]

    # 2. COLUMN MAPPING
    col_map = {
        'date': next((i for i, h in enumerate(headers) if 'DATE' in h.upper() and 'VALUE' not in h.upper()), 0),
        'desc': next((i for i, h in enumerate(headers) if any(k in h.upper() for k in ['PARTICULARS', 'DESCRIPTION', 'NARRATION'])), 1),
        'pay': next((i for i, h in enumerate(headers) if any(k in h.upper() for k in ['WITHDRAWAL', 'DEBIT'])), None),
        'rec': next((i for i, h in enumerate(headers) if any(k in h.upper() for k in ['DEPOSIT', 'CREDIT'])), None),
        'ind': next((i for i, h in enumerate(headers) if any(k in h.upper() for k in ['CR/DR', 'DEBIT/CREDIT'])), None),
        'amt': next((i for i, h in enumerate(headers) if 'AMOUNT' in h.upper() and i not in [0, 1]), None)
    }

    extracted = []
    current_txn = None

    # 3. EXTRACTION
    for row in data_rows:
        if not any(row): continue
        
        # Date Check
        date_match = re.search(r'\d{1,2}[-\s/]\w{2,9}[-\s/]\d{2,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', str(row[col_map['date']]))
        
        nature, amt = None, 0.0

        # Dual Column Logic (SBI, HDFC, Kotak, Axis Dual)
        if col_map['pay'] is not None and col_map['rec'] is not None:
            p_val = clean_val(row[col_map['pay']])
            r_val = clean_val(row[col_map['rec']])
            if p_val > 0: nature, amt = "Payment", p_val
            elif r_val > 0: nature, amt = "Receipt", r_val
            
        # Single Column Logic (ICICI, Axis 1)
        elif col_map['ind'] is not None and col_map['amt'] is not None:
            amt = clean_val(row[col_map['amt']])
            indicator = str(row[col_map['ind']]).upper()
            if 'CR' in indicator: nature = "Receipt"
            elif 'DR' in indicator: nature = "Payment"

        if date_match and amt > 0:
            if current_txn: extracted.append(current_txn)
            current_txn = {
                'Date': date_match.group(),
                'Description': row[col_map['desc']],
                'Nature': nature,
                'Amount': amt
            }
        elif current_txn and not date_match and row[col_map['desc']]:
            # Multi-line description merger
            current_txn['Description'] += " " + str(row[col_map['desc']])

    if current_txn: extracted.append(current_txn)
    return pd.DataFrame(extracted)

if uploaded_file:
    df = process_pdf(uploaded_file)
    if df is not None and not df.empty:
        # SUMMARY METRICS
        total_receipts = df[df['Nature'] == 'Receipt']['Amount'].sum()
        total_payments = df[df['Nature'] == 'Payment']['Amount'].sum()

        st.subheader("Statement Summary")
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Transactions", len(df))
        m2.metric("Total Receipts (CR)", f"₹{total_receipts:,.2f}", delta_color="normal")
        m3.metric("Total Payments (DR)", f"₹{total_payments:,.2f}", delta="-")

        st.divider()
        st.dataframe(df, use_container_width=True)
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel Report", output.getvalue(), "Bank_Report.xlsx")
    else:
        st.error("Table detection failed. This happens if the bank header keywords weren't found.")