import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Master Bank AI", layout="wide")
st.title("🏦 Universal Bank Statement AI")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    # Removes commas and handles formatting like '31,000.00'
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
    with pdfplumber.open(file) as pdf:
        first_page_text = (pdf.pages[0].extract_text() or "").upper()
        
        for page in pdf.pages:
            # Try Lattice for HDFC/Kotak, otherwise default
            if "HDFC" in first_page_text or "KOTAK" in first_page_text:
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            # Fallback for Axis/ICICI History/Indian Bank
            if not table:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    df = pd.DataFrame(all_rows)
    
    # FIND HEADER ROW
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join(map(str, row)).upper()
        if any(k in row_str for k in ['DATE', 'PARTICULARS', 'DESCRIPTION', 'CR/DR']):
            header_idx = i
            break
    
    # CLEAN HEADERS (Crucial for the \n characters in ICICI History)
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    df = df[header_idx + 1:].reset_index(drop=True)

    extracted = []
    for _, row in df.iterrows():
        nature, amount = "Check", 0.0
        
        # --- NEW LOGIC FOR ICICI HISTORY & AXIS ---
        # 1. Check for 'CR/DR' or 'DEBIT/CREDIT' indicator columns
        indicator_col = next((c for c in df.columns if 'CR/DR' in c or 'DEBIT/CREDIT' in c), None)
        amount_col = next((c for c in df.columns if 'AMOUNT' in c and 'BALANCE' not in c), None)
        
        if indicator_col and amount_col:
            v = clean_val(row[amount_col])
            ind = str(row[indicator_col]).upper().strip()
            if 'CR' in ind: nature, amount = "Receipt", v
            elif 'DR' in ind: nature, amount = "Payment", v
        
        # --- FALLBACK FOR STANDARD HDFC/INDIAN/IDBI ---
        else:
            pay_keys = ['WITHDRAWAL', 'DEBIT', 'DR']
            rec_keys = ['DEPOSIT', 'CREDIT', 'CR']
            
            for col in df.columns:
                if any(k in col for k in pay_keys) and 'BALANCE' not in col:
                    v = clean_val(row[col])
                    if v > 0: nature, amount = "Payment", v
                if any(k in col for k in rec_keys) and 'BALANCE' not in col:
                    v = clean_val(row[col])
                    if v > 0: nature, amount = "Receipt", v

        # DATE & DESCRIPTION
        date_col = next((c for c in df.columns if 'DATE' in c), df.columns[0])
        date = str(row[date_col]).replace('\n', ' ').strip()
        # If date cell contains ID + Date, take the last part
        if len(date) > 15: date = date.split()[-1] 

        desc_cols = ['DESCRIPTION', 'PARTICULARS', 'REMARKS', 'NARRATION']
        description = "N/A"
        for d_col in desc_cols:
            if d_col in df.columns and row[d_col]:
                description = str(row[d_col]).replace('\n', ' ').strip()
                break
        
        if amount > 0:
            extracted.append({'Date': date, 'Description': description, 'Nature': nature, 'Amount': amount})

    return pd.DataFrame(extracted)

if uploaded_file:
    try:
        final_df = process_pdf(uploaded_file)
        if final_df is not None and not final_df.empty:
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