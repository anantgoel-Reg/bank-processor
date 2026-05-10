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
    s = str(val).replace(',', '').strip()
    # Capture the sign for Kotak/Single column variations
    is_negative = True if s.startswith('-') else False
    # Remove all non-numeric characters except the dot
    clean = "".join(c for c in s if c.isdigit() or c == '.')
    try: 
        num = float(clean)
        return -num if is_negative else num
    except: 
        return 0.0

def get_bank_type(text):
    text = text.upper()
    banks = ["HDFC", "ICICI", "AXIS", "KOTAK", "IDFC", "INDUSIND", "YES", "IDBI", "INDIAN", "UNION", "BANDHAN"]
    for b in banks:
        if b in text: return b
    if "BANK OF BARODA" in text or "BOB" in text: return "BOB"
    return "UNKNOWN"

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        bank_type = get_bank_type(pdf.pages[0].extract_text() or "")
        for page in pdf.pages:
            # Grid-based banks
            if bank_type in ["HDFC", "KOTAK", "BOB"]:
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            if not table:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    df_raw = pd.DataFrame(all_rows)
    header_idx = 0
    # Find Header Row dynamically
    for i, row in enumerate(all_rows[:50]):
        row_str = " ".join(map(str, row)).upper()
        if any(k in row_str for k in ['DATE', 'PARTICULARS', 'DESCRIPTION', 'WITHDRAWAL', 'DEBIT/CREDIT']):
            header_idx = i
            break
    
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    extracted = []
    for row in data_rows:
        # Map row to headers to avoid KeyError
        row_dict = dict(zip(headers, row))
        nature, amount = "Check", 0.0
        
        # 1. Kotak Single Column Variation (Positive/Negative)
        sign_cols = ['DEBIT/CREDIT( )', 'DEBIT/CREDIT', 'AMOUNT', 'TRANSACTION AMOUNT']
        for col in sign_cols:
            if col in row_dict and str(row_dict[col]).strip():
                v = clean_val(row_dict[col])
                if v != 0:
                    nature = "Payment" if v < 0 else "Receipt"
                    amount = abs(v)
                    break

        # 2. Standard Dual Column Logic (If amount not already found)
        if amount == 0:
            dr_cols = ['WITHDRAWAL (DR.)', 'WITHDRAWAL (DR)', 'WITHDRAWAL DR)', 'WITHDRAWAL AMT.', 'WITHDRAWAL', 'DEBIT AMOUNT', 'DEBIT AMOUNT(INR)']
            for col in dr_cols:
                if col in row_dict:
                    v = clean_val(row_dict[col])
                    if v > 0: nature, amount = "Payment", v; break
            
            if amount == 0:
                cr_cols = ['DEPOSIT (CR.)', 'DEPOSIT (CR)', 'DEPOSIT(CR)', 'DEPOSIT AMT.', 'DEPOSIT', 'CREDIT AMOUNT', 'CREDIT AMOUNT(INR)']
                for col in cr_cols:
                    if col in row_dict:
                        v = clean_val(row_dict[col])
                        if v > 0: nature, amount = "Receipt", v; break

        # 3. Date Logic (Universal)
        date = "N/A"
        date_keys = ['DATE', 'TRAN DATE', 'TRANSACTION DATE', 'VALUE DATE']
        for k in date_keys:
            # Finds any header that CONTAINS the key
            found_key = next((h for h in headers if k in h), None)
            if found_key and row_dict.get(found_key):
                date = str(row_dict[found_key]).split('\n')[0].strip()
                break

        # 4. Description Logic (Universal)
        description = "N/A"
        desc_keys = ['CHO.NO. NARRATION', 'PARTICULARS', 'DESCRIPTION', 'REMARKS', 'NARRATION']
        for k in desc_keys:
            if k in row_dict and str(row_dict[k]).strip() not in ["None", ""]:
                description = str(row_dict[k]).replace('\n', ' ').strip()
                break
        
        if amount > 0 and re.search(r'\d', date):
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
        else:
            st.error("No transactions found. Check if the PDF is a scanned image.")
    except Exception as e:
        st.error(f"System Error: {e}")