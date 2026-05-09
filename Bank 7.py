import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Master Bank AI", layout="wide")

st.title("🏦 Universal Bank Statement AI")
st.info("Supported: HDFC, ICICI, Axis, Kotak, IDFC, IndusInd, Yes, IDBI, Indian, Union, & Bandhan.")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    # Removes INR, commas, spaces
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try:
        return float(clean)
    except:
        return 0.0

def process_pdf(file):
    all_data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # We try 'lattice' first (for HDFC/Kotak) then 'stream' (for Bandhan/Union/IDBI)
            table = page.extract_table()
            if not table:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table and len(table) > 1:
                all_data.extend(table)
    
    if not all_data: return None

    # Structural Check to prevent "Index out of range"
    df = pd.DataFrame(all_data)
    
    # Identify the header row (sometimes banks have 2-3 lines of text before the table starts)
    header_idx = 0
    for i, row in enumerate(all_data):
        row_str = " ".join(map(str, row)).upper()
        if any(k in row_str for k in ['DATE', 'PARTICULARS', 'DESCRIPTION', 'WITHDRAWAL', 'DEBIT']):
            header_idx = i
            break
            
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in all_data[header_idx]]
    df = df[header_idx + 1:].reset_index(drop=True)

    extracted = []
    
    # HEADER MAPPING
    pay_cols = ['WITHDRAWAL', 'WITHDRAWAL (DR.)', 'WITHDRAWALS', 'DEBIT', 'DEBITS', 'DEBIT AMOUNT', 'WITHDRAWAL AMT.']
    rec_cols = ['DEPOSIT', 'DEPOSIT (CR.)', 'DEPOSITS', 'CREDIT', 'CREDITS', 'CREDIT AMOUNT', 'DEPOSIT AMT.']
    desc_cols = ['PARTICULARS', 'DESCRIPTION', 'REMARKS', 'NARRATION', 'TRANSACTION DETAILS', 'REMARK']

    for _, row in df.iterrows():
        nature, amount = "", 0.0
        
        # Check Payments
        for col in pay_cols:
            if col in df.columns:
                v = clean_val(row[col])
                if v > 0: nature, amount = "Payment", v
        
        # Check Receipts
        for col in rec_cols:
            if col in df.columns:
                v = clean_val(row[col])
                if v > 0: nature, amount = "Receipt", v

        # Get Description (Priority check for Bandhan/Union)
        description = "N/A"
        for d_col in desc_cols:
            if d_col in df.columns and str(row[d_col]).strip() not in ["None", ""]:
                description = str(row[d_col]).replace('\n', ' ').strip()
                break
        
        # Get Date
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")

        if amount > 0:
            extracted.append({
                'Date': str(date).strip(),
                'Description': description,
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(extracted)

if uploaded_file:
    with st.spinner('Extracting Data...'):
        try:
            res_df = process_pdf(uploaded_file)
            if res_df is not None and not res_df.empty:
                # METRICS SECTION
                t_rec = res_df[res_df['Nature'] == 'Receipt']['Amount'].sum()
                t_pay = res_df[res_df['Nature'] == 'Payment']['Amount'].sum()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Transactions", len(res_df))
                c2.metric("Total Receipts", f"₹{t_rec:,.2f}")
                c3.metric("Total Payments", f"₹{t_pay:,.2f}")

                st.dataframe(res_df, use_container_width=True)

                # Excel
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                    res_df.to_excel(writer, index=False)
                st.download_button("📥 Download Excel", out.getvalue(), "Processed_Statement.xlsx")
            else:
                st.error("No transactions found. Verify if the PDF is password protected or a scanned image.")
        except Exception as e:
            st.error(f"Error: {e}")