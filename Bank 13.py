import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Bank Processor", layout="wide")
st.title("🏦 Universal Bank Statement Processor")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_amount(val):
    if val is None: return 0.0
    # Removes INR, Cr, Dr, commas, and whitespace
    s = str(val).upper().replace('INR', '').replace('CR', '').replace('DR', '').replace(',', '').strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    try:
        return float(nums[0]) if nums else 0.0
    except:
        return 0.0

def process_bank_statement(file):
    all_rows = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Method 1: Standard Table Extraction
            table = page.extract_table()
            
            # Method 2: Force Text-based Extraction (For HDFC/Indian Bank)
            if not table or len(table) < 2:
                table = page.extract_table(table_settings={
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "snap_tolerance": 3,
                })
            
            if table:
                all_rows.extend(table)

    if not all_rows:
        return None

    # Create DataFrame
    df_raw = pd.DataFrame(all_rows)
    
    # 1. Find Header Row (Search for Date/Particulars in the list)
    header_idx = None
    for i, row in enumerate(all_rows):
        row_str = " ".join([str(x) for x in row if x is not None]).upper()
        if "DATE" in row_str and ("PARTICULARS" in row_str or "DESCRIPTION" in row_str or "REMARKS" in row_str):
            header_idx = i
            break
    
    if header_idx is None:
        header_idx = 0 # Fallback to first row
        
    df_raw.columns = [str(c).replace('\n', ' ').strip().upper() for c in df_raw.iloc[header_idx]]
    df = df_raw.iloc[header_idx + 1:].reset_index(drop=True)

    # 2. Map Column Names for the 3 Specific Banks
    # HDFC: WITHDRAWAL AMT / DEPOSIT AMT
    # IDBI: WITHDRAWALS / DEPOSITS
    # Indian: DEBITS / CREDITS
    pay_cols = ['WITHDRAWAL AMT.', 'WITHDRAWALS', 'DEBITS', 'WITHDRAWAL (DR)', 'DEBIT AMOUNT', 'DEBIT', 'WITHDRAWAL']
    rec_cols = ['DEPOSIT AMT.', 'DEPOSITS', 'CREDITS', 'DEPOSIT (CR)', 'CREDIT AMOUNT', 'DEPOSIT', 'CREDIT']
    desc_cols = ['PARTICULARS', 'DESCRIPTION', 'REMARKS', 'NARRATION', 'TRANSACTION DETAILS']

    final_results = []

    for _, row in df.iterrows():
        nature = ""
        amount = 0.0
        
        # Check for Payments (Withdrawals/Debits)
        for col in pay_cols:
            if col in df.columns:
                val = clean_amount(row[col])
                if val > 0:
                    nature, amount = "Payment", val
                    break # Stop once found
        
        # Check for Receipts (Deposits/Credits)
        if amount == 0: # Only check if not already a payment
            for col in rec_cols:
                if col in df.columns:
                    val = clean_amount(row[col])
                    if val > 0:
                        nature, amount = "Receipt", val
                        break

        # Get Date and Description
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
        desc = "N/A"
        for d_col in desc_cols:
            if d_col in df.columns and row[d_col]:
                desc = str(row[d_col]).replace('\n', ' ').strip()
                break

        if amount > 0:
            final_results.append({
                'Date': str(date).strip(),
                'Description': desc,
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(final_results)

if uploaded_file:
    with st.spinner("Extracting transactions..."):
        try:
            result_df = process_bank_statement(uploaded_file)
            
            if result_df is not None and not result_df.empty:
                # Dashboard Metrics
                t_rec = result_df[result_df['Nature'] == 'Receipt']['Amount'].sum()
                t_pay = result_df[result_df['Nature'] == 'Payment']['Amount'].sum()
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Transactions", len(result_df))
                col2.metric("Total Receipts", f"₹{t_rec:,.2f}")
                col3.metric("Total Payments", f"₹{t_pay:,.2f}")

                st.dataframe(result_df, use_container_width=True)

                # Excel Export
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    result_df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 Download Excel Report",
                    data=output.getvalue(),
                    file_name="Bank_Statement_Bifurcated.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("No transactions found. This PDF format might be unsupported or scanned.")
        except Exception as e:
            st.error(f"System Error: {e}")