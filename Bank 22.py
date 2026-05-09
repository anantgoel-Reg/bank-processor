import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="AI Bank Statement Master", layout="wide")
st.title("🏦 Universal Bank Statement Processor")
st.markdown("Supports: **Axis, ICICI, HDFC, Kotak, IDFC, Bandhan, Yes Bank, SBI**")

uploaded_file = st.file_uploader("Upload Bank PDF Statement", type="pdf")

def clean_val(val):
    """Cleans currency strings and prevents dates from being treated as amounts."""
    if val is None or str(val).strip() in ["", "None", "-", "0.00", "0"]: return 0.0
    s = str(val).replace(',', '').strip()
    # Guard: If it looks like a date/time (e.g. 25-06-2025), it's not money
    if re.search(r'\d{1,2}[/-]\d{1,2}', s) and len(s) > 5: return 0.0
    # Extract only numbers and decimal
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    try: return float(nums[0]) if nums else 0.0
    except: return 0.0

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        # Check first page to help identify the bank
        first_page_text = (pdf.pages[0].extract_text() or "").upper()
        
        for page in pdf.pages:
            # Use 'Lattice' strategy for grid-heavy banks (SBI, HDFC, Kotak, IDFC, Bandhan, Yes)
            if any(bank in first_page_text for bank in ["SBI", "STATE BANK", "BANDHAN", "HDFC", "KOTAK", "IDFC", "YES BANK"]):
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            if not table or len(table) < 2:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    # 1. VARIANT IDENTIFICATION
    header_idx = 0
    variant = "UNKNOWN"
    for i, row in enumerate(all_rows):
        row_str = " ".join([str(x) for x in row if x]).upper()
        
        if 'TXN DATE' in row_str and 'DEBIT' in row_str and 'CREDIT' in row_str:
            header_idx, variant = i, "SBI_STANDARD"
            break
        elif 'DEBIT AMOUNT' in row_str and 'CREDIT AMOUNT' in row_str:
            header_idx, variant = i, "YES_BANK"
            break
        elif 'REMARKS' in row_str and 'DEBIT' in row_str and 'BANDHAN' in first_page_text:
            header_idx, variant = i, "BANDHAN_STANDARD"
            break
        elif 'DEBIT' in row_str and 'CREDIT' in row_str:
            header_idx, variant = i, "IDFC_DUAL"
            break
        elif 'WITHDRAWAL (DR.)' in row_str:
            header_idx, variant = i, "KOTAK_DUAL"
            break
        elif 'WITHDRAWAL AMT.' in row_str:
            header_idx, variant = i, "HDFC_DUAL"
            break
        elif 'TRANSACTION AVAILABLE AMOUNT' in row_str:
            header_idx, variant = i, "ICICI_INDICATOR"
            break
        elif 'TRANSACTION DATE' in row_str:
            header_idx = i
            variant = "AXIS_INDICATOR" if 'DEBIT/CREDIT' in row_str else "AXIS_DUAL"
            break
    
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    extracted = []
    current_txn = None

    # 2. DATA EXTRACTION LOOP
    for row_raw in data_rows:
        row = [str(x).replace('\n', ' ').strip() if x else "" for x in row_raw]
        if not any(row): continue
        
        nature, amount, date_found, desc = None, 0.0, None, ""

        # Find Date in first 2 columns
        combined_row_start = " ".join(row[:2])
        date_match = re.search(r'\d{1,2}[-\s/]\w{3,9}[-\s/]\d{2,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', combined_row_start)
        if date_match: date_found = date_match.group()

        # Dynamic Column Identification
        pay_col = next((i for i,h in enumerate(headers) if any(k in h for k in ['WITHDRAWAL', 'DEBIT'])), None)
        rec_col = next((i for i,h in enumerate(headers) if any(k in h for k in ['DEPOSIT', 'CREDIT'])), None)
        desc_col = next((i for i,h in enumerate(headers) if any(k in h for k in ['DESCRIPTION', 'PARTICULARS', 'NARRATION', 'REMARKS'])), 2)

        # Logic for Dual Column Banks (SBI, HDFC, Kotak, IDFC, Yes, Bandhan, Axis Dual)
        if pay_col is not None and rec_col is not None:
            desc = row[desc_col]
            p_val, r_val = clean_val(row[pay_col]), clean_val(row[rec_col])
            if p_val > 0: nature, amount = "Payment", p_val
            elif r_val > 0: nature, amount = "Receipt", r_val

        # Logic for Single Column + Indicator Banks (ICICI, Axis Indicator)
        elif variant in ["ICICI_INDICATOR", "AXIS_INDICATOR"]:
            desc = row[desc_col]
            amount = clean_val(row[next(i for i,h in enumerate(headers) if 'AMOUNT' in h)])
            ind_col = next(i for i,h in enumerate(headers) if any(k in h for k in ['CR/DR', 'DEBIT/CREDIT', 'INDICATOR']))
            nature = "Receipt" if "CR" in row[ind_col].upper() else "Payment"

        # 3. MULTI-LINE DESCRIPTION MERGING
        if date_found and amount > 0:
            if current_txn: extracted.append(current_txn)
            current_txn = {'Date': date_found, 'Description': desc, 'Nature': nature, 'Amount': amount}
        elif current_txn and desc and not date_found:
            current_txn['Description'] += " " + desc

    if current_txn: extracted.append(current_txn)
    return pd.DataFrame(extracted)

if uploaded_file:
    try:
        with st.spinner("Analyzing Statement..."):
            df = process_pdf(uploaded_file)
        
        if df is not None and not df.empty:
            st.success("Analysis Complete!")
            col1, col2 = st.columns(2)
            col1.metric("Total Transactions", len(df))
            col2.metric("Total Volume", f"₹{df['Amount'].sum():,.2f}")
            
            st.dataframe(df, use_container_width=True)
            
            # Excel Download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Transactions')
            st.download_button(label="📥 Download Excel Report", data=output.getvalue(), file_name="Bank_Statement_Parsed.xlsx")
        else:
            st.warning("No transactions found. Please ensure the PDF is not password protected.")
    except Exception as e:
        st.error(f"Critical Error: {e}")