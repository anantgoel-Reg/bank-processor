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
        for page in pdf.pages:
            # Use basic extraction; fallback to text-strategy for ICICI History
            table = page.extract_table()
            if not table or len(table) < 5:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            if table: all_rows.extend(table)
    
    if not all_rows: return None
    df_raw = pd.DataFrame(all_rows)

    # 1. Find Header
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join(map(str, row)).upper()
        if 'DATE' in row_str and ('CR/DR' in row_str or 'PARTICULARS' in row_str):
            header_idx = i
            break
    
    # Clean headers to handle: "Transaction\n Amount" -> "TRANSACTION AMOUNT"
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    # Identify Columns Dynamically
    col_map = {
        'amount': next((i for i, h in enumerate(headers) if 'AMOUNT' in h and 'BALANCE' not in h), None),
        'indicator': next((i for i, h in enumerate(headers) if 'CR/DR' in h or 'DEBIT/CREDIT' in h), None),
        'date': next((i for i, h in enumerate(headers) if 'DATE' in h), 0),
        'desc': next((i for i, h in enumerate(headers) if 'DESCRIPTION' in h or 'PARTICULARS' in h), 1),
        'withdrawal': next((i for i, h in enumerate(headers) if 'WITHDRAWAL' in h or 'DEBIT' in h and 'AMOUNT' not in h), None),
        'deposit': next((i for i, h in enumerate(headers) if 'DEPOSIT' in h or 'CREDIT' in h and 'AMOUNT' not in h), None)
    }

    final_extracted = []
    temp_row = None

    for row in data_rows:
        # Clean the row data
        row = [str(x).replace('\n', ' ').strip() if x else "" for x in row]
        
        # Determine if this is a NEW transaction (usually has a date or a valid amount)
        has_date = len(re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}', row[col_map['date']])) > 0
        
        # Check for Amount in either single-column or multi-column layout
        amt_val = 0.0
        if col_map['amount'] is not None:
            amt_val = clean_val(row[col_map['amount']])
        elif col_map['withdrawal'] is not None or col_map['deposit'] is not None:
            amt_val = max(clean_val(row[col_map['withdrawal']]), clean_val(row[col_map['deposit']]))

        if has_date and amt_val > 0:
            # If we had a previous row, save it before starting new one
            if temp_row: final_extracted.append(temp_row)
            
            # Start new transaction
            nature = "Payment" # Default
            if col_map['indicator'] is not None:
                nature = "Receipt" if "CR" in row[col_map['indicator']].upper() else "Payment"
            elif col_map['deposit'] is not None and clean_val(row[col_map['deposit']]) > 0:
                nature = "Receipt"

            temp_row = {
                'Date': row[col_map['date']].split()[-1], # Gets date if ID is attached
                'Description': row[col_map['desc']],
                'Nature': nature,
                'Amount': amt_val
            }
        elif temp_row and row[col_map['desc']]:
            # This is a continuation line - append to the previous description
            temp_row['Description'] += " " + row[col_map['desc']]

    # Add the last row
    if temp_row: final_extracted.append(temp_row)

    return pd.DataFrame(final_extracted)

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