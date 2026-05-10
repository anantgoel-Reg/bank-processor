import streamlit as st
import pandas as pd
import pdfplumber
import io

def parse_pdf_to_df(pdf_file):
    """Extracts tables from the HDFC PDF and merges them into a single DataFrame."""
    all_rows = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # Force pdfplumber to use text alignment instead of drawn gridlines
            table = page.extract_table({
                "vertical_strategy": "text",
                "horizontal_strategy": "text"
            })
            if table:
                all_rows.extend(table)
                
    if not all_rows:
        return None
        
    # Find the index of the header row (starts with 'Date')
    header_idx = -1
    for i, row in enumerate(all_rows):
        # Check if row is not None, has elements, and the first element contains 'Date'
        if row and row[0] and 'Date' in str(row[0]):
            header_idx = i
            break
            
    if header_idx == -1:
        return None # Could not find the header row
            
    # Clean up headers to remove newlines
    headers = [str(h).replace('\n', ' ').strip() if h else f"Column_{i}" for i, h in enumerate(all_rows[header_idx])]
    data = all_rows[header_idx+1:]
    
    df = pd.DataFrame(data, columns=headers)
    return df

def process_bank_statement(df):
    """Cleans the data and bifurcates into the requested 4 columns."""
    # Ensure standard HDFC columns exist
    if 'Date' not in df.columns or 'Narration' not in df.columns:
        return None

    # Drop rows where 'Date' or 'Narration' is empty or just standard text artifacts
    df = df.dropna(subset=['Date', 'Narration'])
    df = df[df['Date'].str.contains(r'\d{2}/\d{2}/\d{2}|\d{2}/\d{2}/\d{4}', na=False, regex=True)]

    # Clean amount columns (remove commas and convert to float)
    if 'Withdrawal Amt.' in df.columns:
        df['Withdrawal Amt.'] = pd.to_numeric(df['Withdrawal Amt.'].astype(str).str.replace(',', ''), errors='coerce')
    else:
        df['Withdrawal Amt.'] = 0.0

    if 'Deposit Amt.' in df.columns:
        df['Deposit Amt.'] = pd.to_numeric(df['Deposit Amt.'].astype(str).str.replace(',', ''), errors='coerce')
    else:
        df['Deposit Amt.'] = 0.0

    # Logic to determine Nature of Transaction and Amount
    def determine_nature(row):
        withdrawal = row.get('Withdrawal Amt.', 0)
        deposit = row.get('Deposit Amt.', 0)
        
        if pd.notna(withdrawal) and withdrawal > 0:
            return pd.Series(['Payment', withdrawal])
        elif pd.notna(deposit) and deposit > 0:
            return pd.Series(['Receipt', deposit])
        else:
            return pd.Series(['Unknown', 0.0])

    df[['Nature of Transaction', 'Amount']] = df.apply(determine_nature, axis=1)

    # Select only the 4 requested columns
    final_df = df[['Date', 'Narration', 'Nature of Transaction', 'Amount']]
    
    # Clean up any residual newlines in Narration
    final_df.loc[:, 'Narration'] = final_df['Narration'].str.replace('\n', ' ')
    
    return final_df

def convert_df_to_excel(df):
    """Converts a pandas DataFrame to an Excel bytes object for downloading."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Bank Statement')
    processed_data = output.getvalue()
    return processed_data

# --- STREAMLIT UI ---
st.title("🏦 HDFC Bank Statement Parser")
st.write("Upload your HDFC Bank Statement PDF to extract transactions, view metrics, and download an Excel report.")

uploaded_file = st.file_uploader("Upload HDFC Statement (PDF)", type="pdf")

if uploaded_file is not None:
    with st.spinner("Parsing PDF..."):
        raw_df = parse_pdf_to_df(uploaded_file)
        
    if raw_df is not None:
        with st.spinner("Processing transactions..."):
            processed_df = process_bank_statement(raw_df)
            
        if processed_df is not None and not processed_df.empty:
            st.success("Statement parsed successfully!")
            
            # --- SUMMARY METRICS ---
            st.subheader("Summary Metrics")
            
            total_transactions = len(processed_df)
            total_receipts = processed_df[processed_df['Nature of Transaction'] == 'Receipt']['Amount'].sum()
            total_payments = processed_df[processed_df['Nature of Transaction'] == 'Payment']['Amount'].sum()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Transactions", total_transactions)
            col2.metric("Total Receipts (₹)", f"{total_receipts:,.2f}")
            col3.metric("Total Payments (₹)", f"{total_payments:,.2f}")
            
            # --- DATA PREVIEW ---
            st.subheader("Bifurcated Transactions")
            st.dataframe(processed_df, use_container_width=True)
            
            # --- EXCEL DOWNLOAD ---
            excel_data = convert_df_to_excel(processed_df)
            st.download_button(
                label="📥 Download as Excel",
                data=excel_data,
                file_name="Parsed_HDFC_Statement.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Could not process the transactions. Please ensure this is a standard HDFC statement format.")
    else:
        st.error("Could not extract tables from the uploaded PDF.")
