import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Universal Transaction Bifurcator", layout="wide")

st.title("🏦 Universal Bank Statement AI")
st.markdown("---")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_amount(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    # Removes 'INR', commas, and whitespace
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try:
        return float(clean)
    except:
        return 0.0

def process_universal_pdf(file):
    all_rows = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # We use 'stream' mode as it is the most compatible across all 11 banks mentioned
            table = page.extract_table(table_settings={
                "vertical_strategy": "text", 
                "horizontal_strategy": "text",
                "intersection_y_tolerance": 10
            })
            if table:
                all_rows.extend(table)
    
    if not all_rows: return None

    df = pd.DataFrame(all_rows)
    # Clean headers and handle multi-line headers
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in df.iloc[0]]
    df = df[1:].reset_index(drop=True)

    extracted_data = []

    # --- DEFINING COLUMN MAPS ---
    payment_cols = [
        'WITHDRAWAL', 'WITHDRAWAL (DR.)', 'WITHDRAWAL (DR)', 'WITHDRAWAL AMT.', 
        'DEBIT', 'DEBIT AMOUNT', 'DEBIT AMOUNT(INR)', 'DEBITS'
    ]
    receipt_cols = [
        'DEPOSIT', 'DEPOSIT (CR.)', 'DEPOSIT (CR)', 'DEPOSIT AMT.', 
        'CREDIT', 'CREDIT AMOUNT', 'CREDIT AMOUNT(INR)', 'CREDITS'
    ]
    desc_cols = ['PARTICULARS', 'DESCRIPTION', 'NARRATION', 'TRANSACTION DETAILS', 'REMARKS']

    for _, row in df.iterrows():
        nature = ""
        amount = 0.0
        
        # Check for Payments
        for p_col in payment_cols:
            if p_col in df.columns:
                val = clean_amount(row[p_col])
                if val > 0:
                    nature, amount = "Payment", val
        
        # Check for Receipts
        for r_col in receipt_cols:
            if r_col in df.columns:
                val = clean_amount(row[r_col])
                if val > 0:
                    nature, amount = "Receipt", val

        # Handle Date
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
        
        # Handle Description (Specially for Bandhan/Union where names vary)
        description = "N/A"
        for d_col in desc_cols:
            if d_col in df.columns:
                description = str(row[d_col]).replace('\n', ' ').strip()
                break

        if amount > 0:
            extracted_data.append({
                'Date': str(date).strip(),
                'Description': description,
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(extracted_data)

if uploaded_file:
    with st.spinner('Analyzing patterns across 11 supported banks...'):
        try:
            final_df = process_universal_pdf(uploaded_file)
            
            if final_df is not None and not final_df.empty:
                # 1. SUMMARY METRICS (Requested Feature)
                total_receipts = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
                total_payments = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
                count = len(final_df)

                m1, m2, m3 = st.columns(3)
                m1.metric("Total Transactions", count)
                m2.metric("Total Receipts", f"₹{total_receipts:,.2f}", delta_color="normal")
                m3.metric("Total Payments", f"₹{total_payments:,.2f}", delta_color="inverse")

                # 2. DATA DISPLAY
                st.write("### Processed Transactions")
                st.dataframe(final_df, use_container_width=True)

                # 3. EXCEL DOWNLOAD
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False, sheet_name='Bifurcated')
                
                st.download_button(
                    label="🚀 Download Standardized Excel",
                    data=output.getvalue(),
                    file_name=f"Processed_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("Could not find transactions. Ensure the PDF header row is visible on the first page.")
        except Exception as e:
            st.error(f"Error: {e}")