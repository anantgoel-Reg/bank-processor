import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="AI Bank Bifurcator", layout="wide")

st.title("🏦 Professional Bank Statement Bifurcator")
st.info("Upload your PDF. The AI now uses specific column logic for Axis, ICICI, Kotak, IDFC, IndusInd, and Yes Bank.")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def process_statement(file):
    all_data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                all_data.extend(table)
    
    if not all_data:
        return None

    # Convert to DataFrame and clean headers
    df = pd.DataFrame(all_data)
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in df.iloc[0]]
    df = df[1:].reset_index(drop=True)

    # --- THE FIXED NATURE LOGIC ---
    def identify_nature(row):
        # 1. ICICI / KOTAK / INDUSIND (Withdrawal vs Deposit)
        if 'WITHDRAWAL (DR.)' in df.columns or 'WITHDRAWAL' in df.columns:
            col = 'WITHDRAWAL (DR.)' if 'WITHDRAWAL (DR.)' in df.columns else 'WITHDRAWAL'
            dep_col = 'DEPOSIT (CR.)' if 'DEPOSIT (CR.)' in df.columns else 'DEPOSIT'
            if row.get(col) and str(row[col]).strip() not in ['', 'None', '0.00', '0']:
                return 'Payment'
            if row.get(dep_col) and str(row[dep_col]).strip() not in ['', 'None', '0.00', '0']:
                return 'Receipt'

        # 2. AXIS / YES BANK / IDFC (Debit Amount vs Credit Amount)
        debit_cols = ['DEBIT AMOUNT(INR)', 'DEBIT AMOUNT', 'DEBIT']
        credit_cols = ['CREDIT AMOUNT(INR)', 'CREDIT AMOUNT', 'CREDIT']
        
        for d_col, c_col in zip(debit_cols, credit_cols):
            if d_col in df.columns:
                if row.get(d_col) and str(row[d_col]).strip() not in ['', 'None', '0.00', '0']:
                    return 'Payment'
                if row.get(c_col) and str(row[c_col]).strip() not in ['', 'None', '0.00', '0']:
                    return 'Receipt'
        
        return "Check Manually"

    df['NATURE'] = df.apply(identify_nature, axis=1)
    
    # Keep only useful columns for the final Excel
    essential_cols = [c for c in df.columns if any(k in c for k in ['DATE', 'PARTICULARS', 'DESCRIPTION', 'NATURE'])]
    return df[essential_cols]

if uploaded_file:
    result_df = process_statement(uploaded_file)
    if result_df is not None:
        st.write("### Extracted Data Preview")
        st.dataframe(result_df, use_container_width=True)

        # Excel Export
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            result_df.to_excel(writer, index=False)
        
        st.download_button("📥 Download Standardized Excel", output.getvalue(), "Bifurcated_Statement.xlsx")