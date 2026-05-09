import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Master Bank AI", layout="wide")
st.title("🏦 Universal Bank Statement AI")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean)
    except: return 0.0

def get_bank_type(text):
    text = text.upper()
    if "HDFC BANK" in text: return "HDFC"
    if "ICICI BANK" in text: return "ICICI"
    if "AXIS BANK" in text: return "AXIS"
    if "KOTAK" in text: return "KOTAK"
    if "IDFC" in text: return "IDFC"
    if "INDUSIND" in text: return "INDUSIND"
    if "YES BANK" in text: return "YES"
    if "IDBI" in text: return "IDBI"
    if "INDIAN BANK" in text: return "INDIAN"
    if "UNION BANK" in text: return "UNION"
    if "BANDHAN" in text: return "BANDHAN"
    return "UNKNOWN"

def process_pdf(file):
    all_rows = []
    bank_type = "UNKNOWN"
    
    with pdfplumber.open(file) as pdf:
        # Identify Bank from the first page text
        bank_type = get_bank_type(pdf.pages[0].extract_text() or "")
        
        for page in pdf.pages:
            # HDFC and Kotak require 'Lattice' (lines)
            if bank_type in ["HDFC", "KOTAK"]:
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            # Fallback for all
            if not table:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table: all_rows.extend(table)
    
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

    extracted = []
    for _, row in df.iterrows():
        nature, amount = "Check", 0.0
        
        # --- BANK SPECIFIC RULES ---
        # 1. ICICI / KOTAK / HDFC / INDUSIND / IDBI / INDIAN
        dr_cols = ['WITHDRAWAL (DR.)', 'WITHDRAWAL (DR)', 'WITHDRAWAL AMT.', 'WITHDRAWAL', 'WITHDRAWALS', 'DEBITS']
        cr_cols = ['DEPOSIT (CR.)', 'DEPOSIT (CR)', 'DEPOSIT AMT.', 'DEPOSIT', 'DEPOSITS', 'CREDITS']
        
        # 2. AXIS / YES / IDFC / UNION
        debit_cols = ['DEBIT AMOUNT(INR)', 'DEBIT AMOUNT', 'DEBIT', 'DEBITS']
        credit_cols = ['CREDIT AMOUNT(INR)', 'CREDIT AMOUNT', 'CREDIT', 'CREDITS']

        # Logic for Payments
        for col in (dr_cols + debit_cols):
            if col in df.columns:
                v = clean_val(row[col])
                if v > 0: nature, amount = "Payment", v
        
        # Logic for Receipts
        for col in (cr_cols + credit_cols):
            if col in df.columns:
                v = clean_val(row[col])
                if v > 0: nature, amount = "Receipt", v

        # Date & Description logic
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
        desc_cols = ['PARTICULARS', 'DESCRIPTION', 'REMARKS', 'NARRATION', 'TRANSACTION DETAILS', 'REMARK']
        description = "N/A"
        for d_col in desc_cols:
            if d_col in df.columns and str(row[d_col]).strip() not in ["None", ""]:
                description = str(row[d_col]).replace('\n', ' ').strip()
                break
        
        if amount > 0:
            extracted.append({'Date': str(date).strip(), 'Description': description, 'Nature': nature, 'Amount': amount})

    return pd.DataFrame(extracted)

if uploaded_file:
    try:
        final_df = process_pdf(uploaded_file)
        if final_df is not None and not final_df.empty:
            # Metrics
            t_rec = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Transactions", len(final_df))
            c2.metric("Total Receipts", f"₹{t_rec:,.2f}")
            c3.metric("Total Payments", f"₹{t_pay:,.2f}")
            
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", out.getvalue(), "Statement_Processed.xlsx")
    except Exception as e:
        st.error(f"Error: {e}")