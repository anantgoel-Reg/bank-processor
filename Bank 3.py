import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="AI Bank Processor", layout="wide")

st.title("🏦 Standardized Bank Statement Processor")
st.markdown("---")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    """Helper to turn messy PDF strings into clean numbers"""
    if val is None or val == "": return 0.0
    # Remove commas, currency symbols, and whitespace
    clean = str(val).replace(',', '').replace('₹', '').replace(' ', '').strip()
    try:
        return float(clean)
    except:
        return 0.0

def process_statement(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                all_rows.extend(table)
    
    if not all_rows: return None

    # Load into DataFrame
    df = pd.DataFrame(all_rows)
    # Clean up column names (remove newlines and extra spaces)
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in df.iloc[0]]
    df = df[1:].reset_index(drop=True)

    final_data = []

    for index, row in df.iterrows():
        nature = "Check Manually"
        amount = 0.0
        
        # 1. HDFC / ICICI / KOTAK / INDUSIND (Withdrawal vs Deposit)
        # Checking for all variations of header names found in your PDFs
        dr_headers = ['WITHDRAWAL (DR)', 'WITHDRAWAL (DR.)', 'WITHDRAWAL', 'WITHDRAWAL AMT.']
        cr_headers = ['DEPOSIT (CR)', 'DEPOSIT (CR.)', 'DEPOSIT', 'DEPOSIT AMT.']
        
        # 2. AXIS / YES BANK / IDFC (Debit vs Credit)
        debit_headers = ['DEBIT AMOUNT(INR)', 'DEBIT AMOUNT', 'DEBIT']
        credit_headers = ['CREDIT AMOUNT(INR)', 'CREDIT AMOUNT', 'CREDIT']

        # COMBINED LOGIC
        # We check the Debit/Withdrawal side first
        for dr in (dr_headers + debit_headers):
            if dr in df.columns:
                val = clean_val(row[dr])
                if val > 0:
                    nature = "Payment"
                    amount = val

        # Then check the Credit/Deposit side
        for cr in (cr_headers + credit_headers):
            if cr in df.columns:
                val = clean_val(row[cr])
                if val > 0:
                    nature = "Receipt"
                    amount = val

        # Extract Date and Description (Finding common column names)
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
        desc = next((row[c] for c in df.columns if any(k in c for k in ['PARTICULARS', 'DESCRIPTION', 'NARRATION'])), "N/A")

        if amount > 0: # Only add rows that actually have a transaction amount
            final_data.append({
                'Date': date,
                'Description': str(desc).replace('\n', ' '),
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(final_data)

if uploaded_file:
    with st.spinner('Extracting amounts and bifurcating...'):
        result_df = process_statement(uploaded_file)
        
        if result_df is not None and not result_df.empty:
            # Show summary metrics
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Transactions", len(result_df))
            c2.metric("Total Receipts", f"₹{result_df[result_df['Nature']=='Receipt']['Amount'].sum():,.2f}")
            c3.metric("Total Payments", f"₹{result_df[result_df['Nature']=='Payment']['Amount'].sum():,.2f}")

            st.dataframe(result_df, use_container_width=True)

            # Excel Download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                result_df.to_excel(writer, index=False, sheet_name='Bifurcated Data')
            
            st.download_button(
                label="📥 Download Standardized Excel",
                data=output.getvalue(),
                file_name=f"Processed_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("No transactions found. Please ensure the PDF is a readable bank statement.")