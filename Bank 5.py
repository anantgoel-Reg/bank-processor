import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="AI Bank Processor", layout="wide")

st.title("🏦 Universal Bank Statement Processor")
st.info("Updated Logic: Specific handling for HDFC, ICICI, Kotak, IDFC, Axis, and Yes Bank.")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_num(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try:
        return float(clean)
    except:
        return 0.0

def process_pdf(file):
    all_data = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # TRY 1: Look for table with visible lines (Good for HDFC/Kotak)
            table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            
            # TRY 2: Fallback to text-based table (Good for Axis/ICICI)
            if not table or len(table) < 2:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table:
                all_data.extend(table)
    
    if not all_data: return None

    # Create DataFrame and clean headers
    df = pd.DataFrame(all_data)
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in df.iloc[0]]
    df = df[1:].reset_index(drop=True)

    extracted_rows = []

    for _, row in df.iterrows():
        nature = ""
        amount = 0.0
        
        # 1. Define specific Bank Header Groups
        # ICICI, HDFC, KOTAK, INDUSIND
        withdrawal_headers = ['WITHDRAWAL (DR.)', 'WITHDRAWAL (DR)', 'WITHDRAWAL AMT.', 'WITHDRAWAL']
        deposit_headers = ['DEPOSIT (CR.)', 'DEPOSIT (CR)', 'DEPOSIT AMT.', 'DEPOSIT']
        
        # AXIS, IDFC, YES BANK
        debit_headers = ['DEBIT AMOUNT(INR)', 'DEBIT AMOUNT', 'DEBIT']
        credit_headers = ['CREDIT AMOUNT(INR)', 'CREDIT AMOUNT', 'CREDIT']

        # 2. APPLY LOGIC (Your specific rules)
        # Check Payments
        for col in (withdrawal_headers + debit_headers):
            if col in df.columns:
                val = clean_num(row[col])
                if val > 0:
                    nature, amount = "Payment", val

        # Check Receipts (Overrides if needed, but usually only one exists)
        for col in (deposit_headers + credit_headers):
            if col in df.columns:
                val = clean_num(row[col])
                if val > 0:
                    nature, amount = "Receipt", val

        # 3. Get Date & Description
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
        desc = next((row[c] for c in df.columns if any(k in c for k in ['PARTICULARS', 'DESCRIPTION', 'NARRATION', 'CHQ/REF']) ), "N/A")

        if amount > 0:
            extracted_rows.append({
                'Date': str(date).strip(),
                'Description': str(desc).replace('\n', ' ').strip(),
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(extracted_rows)

if uploaded_file:
    try:
        final_df = process_pdf(uploaded_file)
        if final_df is not None and not final_df.empty:
            st.success(f"Processed {len(final_df)} transactions.")
            
            # Summary
            st.dataframe(final_df, use_container_width=True)

            # Excel Export
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            
            st.download_button("📥 Download Excel", output.getvalue(), "Statement_Bifurcated.xlsx")
        else:
            st.warning("No transactions found. This usually happens if the PDF headers don't match our list.")
    except Exception as e:
        st.error(f"System Error: {e}")