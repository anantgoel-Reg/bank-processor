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
    # Removes any non-numeric characters except the dot
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
        first_page_text = pdf.pages[0].extract_text() or ""
        bank_type = get_bank_type(first_page_text)
        
        for page in pdf.pages:
            # HDFC works best with Lattice (lines) strategy
            if bank_type == "HDFC":
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            # Fallback
            if not table:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    # Find Header Row
    header_idx = 0
    for i, row in enumerate(all_rows[:20]):
        row_str = " ".join(map(str, row)).upper()
        if any(k in row_str for k in ['DATE', 'PARTICULARS', 'DESCRIPTION', 'WITHDRAWAL', 'DEBIT']):
            header_idx = i
            break
    
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    extracted = []
    for row_data in data_rows:
        # Create a dictionary for easier keyword lookup
        row_dict = dict(zip(headers, row_data))
        nature, amount = "Check", 0.0
        
        # --- HDFC KEYWORD SYSTEM ---
        if bank_type == "HDFC":
            # HDFC standard column names
            withdrawal = clean_val(row_dict.get('WITHDRAWAL AMT.', 0))
            deposit = clean_val(row_dict.get('DEPOSIT AMT.', 0))
            
            if withdrawal > 0:
                nature, amount = "Payment", withdrawal
            elif deposit > 0:
                nature, amount = "Receipt", deposit
                
            date = row_dict.get('DATE', "N/A")
            description = row_dict.get('NARRATION', row_dict.get('PARTICULARS', "N/A"))

        # --- OTHER BANKS (Standard Logic) ---
        else:
            dr_cols = ['WITHDRAWAL (DR.)', 'WITHDRAWAL (DR)', 'WITHDRAWAL', 'DEBIT AMOUNT', 'DEBIT', 'DEBITS']
            cr_cols = ['DEPOSIT (CR.)', 'DEPOSIT (CR)', 'DEPOSIT', 'CREDIT AMOUNT', 'CREDIT', 'CREDITS']

            for col in dr_cols:
                if col in headers:
                    v = clean_val(row_dict.get(col))
                    if v > 0: nature, amount = "Payment", v; break
            
            if amount == 0:
                for col in cr_cols:
                    if col in headers:
                        v = clean_val(row_dict.get(col))
                        if v > 0: nature, amount = "Receipt", v; break

            date = next((row_dict[c] for c in headers if 'DATE' in c), "N/A")
            description = next((row_dict[c] for c in headers if any(k in c for k in ['PARTICULARS', 'DESCRIPTION', 'REMARKS'])), "N/A")

        if amount > 0:
            extracted.append({
                'Date': str(date).replace('\n', ' ').strip(), 
                'Description': str(description).replace('\n', ' ').strip(), 
                'Nature': nature, 
                'Amount': amount
            })

    return pd.DataFrame(extracted)

if uploaded_file:
    try:
        final_df = process_pdf(uploaded_file)
        if final_df is not None and not final_df.empty:
            t_rec = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
            
            st.subheader("Statement Summary")
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