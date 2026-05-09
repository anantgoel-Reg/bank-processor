import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Master Bank AI", layout="wide")
st.title("🏦 Stabilized Bank Statement AI")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    s = str(val).replace(',', '').strip()
    # PREVENT DATE LEAK: If the cell contains a date slash or hyphen, it's not money
    if "/" in s or "-" in s and len(s) > 5: return 0.0
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    try: return float(nums[0]) if nums else 0.0
    except: return 0.0

def get_bank_type(text):
    text = text.upper()
    if "HDFC BANK" in text: return "HDFC"
    if "ICICI BANK" in text or "DETAILED STATEMENT" in text: return "ICICI"
    if "AXIS BANK" in text: return "AXIS"
    if "IDBI" in text: return "IDBI"
    if "INDIAN BANK" in text: return "INDIAN"
    return "UNKNOWN"

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        bank_text = (pdf.pages[0].extract_text() or "").upper()
        bank_type = get_bank_type(bank_text)
        
        for page in pdf.pages:
            # HDFC/Kotak require lines; Axis/ICICI History requires text-flow
            if bank_type in ["HDFC", "KOTAK"]:
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            if not table or len(table) < 2:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    df_raw = pd.DataFrame(all_rows)
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join([str(x) for x in row if x]).upper()
        if 'DATE' in row_str and any(k in row_str for k in ['PARTICULARS', 'DESCRIPTION', 'CR/DR']):
            header_idx = i
            break
    
    df_raw.columns = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    df = df_raw[header_idx + 1:].reset_index(drop=True)

    extracted = []
    current_txn = None

    for _, row in df.iterrows():
        nature, amount = "Check", 0.0
        
        # 1. AXIS / ICICI HISTORY (Single Amount Column + CR/DR Indicator)
        # Note: We look for the exact Axis/ICICI Header names
        amt_col = next((c for c in df.columns if 'AMOUNT(INR)' in c or 'TRANSACTION AVAILABLE AMOUNT' in c), None)
        ind_col = next((c for c in df.columns if 'DEBIT/CREDIT' in c or 'CR/DR' in c), None)

        if amt_col and ind_col:
            v = clean_val(row[amt_col])
            indicator = str(row[ind_col]).upper()
            if 'CR' in indicator: nature, amount = "Receipt", v
            elif 'DR' in indicator: nature, amount = "Payment", v

        # 2. HDFC / IDBI / INDIAN (Two-Column Layout)
        else:
            pay_cols = ['WITHDRAWAL AMT.', 'WITHDRAWALS', 'DEBITS', 'WITHDRAWAL', 'DEBIT']
            rec_cols = ['DEPOSIT AMT.', 'DEPOSITS', 'CREDITS', 'DEPOSIT', 'CREDIT']
            
            for col in pay_cols:
                if col in df.columns:
                    v = clean_val(row[col])
                    if v > 0: nature, amount = "Payment", v
            
            for col in rec_cols:
                if col in df.columns:
                    v = clean_val(row[col])
                    if v > 0: nature, amount = "Receipt", v

        # Date & Description Logic
        # Explicitly ignore "VALUE DATE" to prevent HDFC mapping errors
        date_col = next((c for c in df.columns if 'DATE' in c and 'VALUE' not in c), 
                        next((c for c in df.columns if 'DATE' in c), None))
        
        date_val = str(row[date_col]) if date_col else ""
        has_date = len(re.findall(r'\d{1,2}[/-]\d{1,2}', date_val)) > 0
        
        if has_date and amount > 0:
            if current_txn: extracted.append(current_txn)
            
            # Clean date (strips Transaction IDs if joined)
            clean_date = date_val.split()[-1] if len(date_val) > 15 else date_val
            
            desc = "N/A"
            for d_col in ['DESCRIPTION', 'PARTICULARS', 'REMARKS', 'NARRATION']:
                if d_col in df.columns and row[d_col]:
                    desc = str(row[d_col]).replace('\n', ' ').strip()
                    break

            current_txn = {'Date': clean_date, 'Description': desc, 'Nature': nature, 'Amount': amount}
        
        elif current_txn and not has_date:
            # Append multi-line descriptions to the buffer
            for d_col in ['DESCRIPTION', 'PARTICULARS', 'REMARKS', 'NARRATION']:
                if d_col in df.columns and row[d_col]:
                    current_txn['Description'] += " " + str(row[d_col]).replace('\n', ' ').strip()
                    break

    if current_txn: extracted.append(current_txn)
    return pd.DataFrame(extracted)

if uploaded_file:
    try:
        final_df = process_pdf(uploaded_file)
        if final_df is not None and not final_df.empty:
            # --- SUMMARY METRICS ---
            t_rec = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
            
            st.success(f"Successfully Extracted {len(final_df)} Transactions")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Transactions", len(final_df))
            m2.metric("Total Receipts (CR)", f"₹{t_rec:,.2f}")
            m3.metric("Total Payments (DR)", f"₹{t_pay:,.2f}")
            
            st.dataframe(final_df, use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Download Standardized Excel", output.getvalue(), "Statement_Final.xlsx")
        else:
            st.error("No transactions found. Check if the PDF is a scanned image or has a different layout.")
    except Exception as e:
        st.error(f"System Error: {e}")