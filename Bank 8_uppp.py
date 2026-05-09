import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Master Bank AI", layout="wide")
st.title("🏦 Universal Bank Statement AI")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    # Removes commas and extra text, keeping only numbers and dots
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
    if "BANK OF BARODA" in text or "BOB" in text: return "BOB" # Added BoB Detection
    return "UNKNOWN"

def process_pdf(file):
    all_rows = []
    bank_type = "UNKNOWN"
    
    with pdfplumber.open(file) as pdf:
        bank_type = get_bank_type(pdf.pages[0].extract_text() or "")
        
        for page in pdf.pages:
            # HDFC, Kotak, and BoB often use clear lines/grids
            if bank_type in ["HDFC", "KOTAK", "BOB"]:
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            if not table:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    df = pd.DataFrame(all_rows)
    
    # Find Header Row
    header_idx = 0
    for i, row in enumerate(all_rows[:30]):
        row_str = " ".join(map(str, row)).upper()
        # Added 'TRAN DATE' for Bank of Baroda header detection
        if any(k in row_str for k in ['DATE', 'PARTICULARS', 'DESCRIPTION', 'WITHDRAWAL', 'DEBIT', 'TRAN DATE']):
            header_idx = i
            break
    
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    df = df[header_idx + 1:].reset_index(drop=True)

    extracted = []
    for _, row in df.iterrows():
        nature, amount = "Check", 0.0
        
        # --- COLUMN DEFINITIONS ---
        # Added Bank of Baroda specific: 'WITHDRAWAL DR)' and 'DEPOSIT(CR)'
        dr_cols = ['WITHDRAWAL (DR.)', 'WITHDRAWAL (DR)', 'WITHDRAWAL DR)', 'WITHDRAWAL AMT.', 'WITHDRAWAL', 'DEBIT AMOUNT', 'DEBITS']
        cr_cols = ['DEPOSIT (CR.)', 'DEPOSIT (CR)', 'DEPOSIT(CR)', 'DEPOSIT AMT.', 'DEPOSIT', 'CREDIT AMOUNT', 'CREDITS']
        
        # Logic for Payments
        for col in dr_cols:
            if col in df.columns:
                v = clean_val(row[col])
                if v > 0: nature, amount = "Payment", v; break
        
        # Logic for Receipts (if not already found as payment)
        if amount == 0:
            for col in cr_cols:
                if col in df.columns:
                    v = clean_val(row[col])
                    if v > 0: nature, amount = "Receipt", v; break

        # Date logic: Search for any column containing 'DATE'
        date = next((row[c] for c in df.columns if 'DATE' in c and 'VALUE' not in c), "N/A")
        
        # Description logic
        desc_cols = ['NARRATION', 'PARTICULARS', 'DESCRIPTION', 'REMARKS', 'TRANSACTION DETAILS']
        description = "N/A"
        for d_col in desc_cols:
            # BoB often uses 'CHO.NO. NARRATION' or just 'NARRATION'
            found_col = next((c for c in df.columns if d_col in c), None)
            if found_col and str(row[found_col]).strip() not in ["None", ""]:
                description = str(row[found_col]).replace('\n', ' ').strip()
                break
        
        if amount > 0:
            extracted.append({
                'Date': str(date).strip().split('\n')[0], # Clean multi-line dates
                'Description': description, 
                'Nature': nature, 
                'Amount': amount
            })

    return pd.DataFrame(extracted)

if uploaded_file:
    try:
        final_df = process_pdf(uploaded_file)
        if final_df is not None and not final_df.empty:
            # Separate Summary Metrics
            t_rec = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
            
            st.subheader("Statement Summary")
            c1, c2, c3 = st.columns(3)
            c1.metric("Transactions Found", len(final_df))
            c2.metric("Total Receipts (CR)", f"₹{t_rec:,.2f}")
            c3.metric("Total Payments (DR)", f"₹{t_pay:,.2f}")
            
            st.divider()
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel Report", out.getvalue(), "Statement_Processed.xlsx")
        else:
            st.warning("No transactions found. Ensure the PDF is not a scanned image.")
    except Exception as e:
        st.error(f"Error: {e}")