import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="Bank Statement Pro", layout="wide")

# --- SIDEBAR SELECTION ---
st.sidebar.title("🏦 Selection Panel")
bank_choice = st.sidebar.selectbox(
    "Select the Bank Statement Type:",
    ["ICICI Bank", "Axis Bank", "Bank of Baroda", "HDFC Bank"]
)

st.title(f"Processing: {bank_choice}")
uploaded_file = st.file_uploader(f"Upload {bank_choice} PDF", type="pdf")

# --- UTILITY: Numeric Cleaner ---
def clean_num(val):
    if val is None or str(val).strip() in ["", "-"]: return 0.0
    s = str(val).upper().replace(',', '').replace('INR', '').strip()
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    try: return float(match.group()) if match else 0.0
    except: return 0.0

# --- ENGINE: ICICI BANK (Variations: Detailed Transaction History & Account Statement) ---
def engine_icici(pdf):
    data = []
    for page in pdf.pages:
        tbl = page.extract_table()
        if not tbl: continue
        
        # Identify headers for this page
        raw_headers = [str(c).replace('\n', ' ').strip().upper() for c in tbl[0]]
        h_map = {val: i for i, val in enumerate(raw_headers)}
        
        for row in tbl[1:]:
            # 1. Identify Date (Handles 'Txn Posted Date' or 'Transaction date')
            date_col = h_map.get('TXN POSTED DATE', h_map.get('TRANSACTION DATE', 2))
            date_cell = str(row[date_col] if date_col < len(row) else "").strip()
            if not re.search(r'\d', date_cell): continue
            
            # 2. Determine Variation Logic
            nature, amt = "Check", 0.0
            
            # VARIATION: Detailed Transaction History (Uses CR/DR column)
            if 'CR/DR' in h_map:
                amt = clean_num(row[h_map['TRANSACTION AMOUNT(INR)']])
                ind = str(row[h_map['CR/DR']]).upper()
                nature = "Receipt" if "CR" in ind else "Payment"
            
            # VARIATION: Standard Account Statement (Uses Withdrawal/Deposit columns)
            else:
                dr = clean_num(row[h_map.get('WITHDRAWAL (DR)', 5)])
                cr = clean_num(row[h_map.get('DEPOSIT (CR)', 6)])
                nature = "Payment" if dr > 0 else "Receipt"
                amt = dr if dr > 0 else cr

            data.append({
                "Date": date_cell.split('\n')[0].strip(),
                "Description": str(row[h_map.get('DESCRIPTION', 4)]).replace('\n', ' '),
                "Nature": nature,
                "Amount": amt
            })
    return pd.DataFrame(data)

# --- ENGINE: AXIS BANK (Variations: Single Amount Column vs Dual Column) ---
def engine_axis(pdf):
    data = []
    for page in pdf.pages:
        tbl = page.extract_table()
        if not tbl: continue
        
        raw_headers = [str(c).replace('\n', ' ').strip().upper() for c in tbl[0]]
        h_map = {val: i for i, val in enumerate(raw_headers)}
        
        for row in tbl[1:]:
            date_cell = str(row[h_map.get('TRANSACTION DATE (DD/MM/YYYY)', 1)])
            if not re.search(r'\d', date_cell): continue
            
            nature, amt = "Check", 0.0
            
            # VARIATION: Axis 1 (Amount + Debit/Credit column)
            if 'DEBIT/CREDIT' in h_map:
                amt = clean_num(row[h_map['AMOUNT(INR)']])
                ind = str(row[h_map['DEBIT/CREDIT']]).upper()
                nature = "Receipt" if "CR" in ind else "Payment"
            
            # VARIATION: Axis 2 (Separate Debit/Credit Amount columns)
            else:
                # Some Axis versions have 'DEBIT AMOUNT(INR)' and 'CREDIT AMOUNT(INR)'
                dr = clean_num(row[h_map.get('DEBIT AMOUNT(INR)', 3)])
                cr = clean_num(row[h_map.get('CREDIT AMOUNT(INR)', 4)])
                nature = "Payment" if dr > 0 else "Receipt"
                amt = dr if dr > 0 else cr

            data.append({
                "Date": date_cell.split('\n')[0].strip(),
                "Description": str(row[h_map.get('PARTICULARS', 3)]).replace('\n', ' '),
                "Nature": nature,
                "Amount": amt
            })
    return pd.DataFrame(data)

# --- ENGINE: BANK OF BARODA ---
def engine_bob(pdf):
    data = []
    for page in pdf.pages:
        # BoB must use Lattice
        tbl = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
        if not tbl: continue
        
        header_row_found = False
        h_map = {}
        
        for row in tbl:
            row_str = " ".join([str(x) for x in row if x]).upper()
            if 'TRAN DATE' in row_str:
                headers = [str(c).replace('\n', ' ').strip().upper() for c in row]
                h_map = {val: i for i, val in enumerate(headers)}
                header_row_found = True
                continue
            
            if header_row_found:
                date_val = row[h_map.get('TRAN DATE', 0)]
                if not date_val or not re.search(r'\d', str(date_val)): continue
                
                dr = clean_num(row[h_map.get('WITHDRAWAL DR)', 3)])
                cr = clean_num(row[h_map.get('DEPOSIT(CR)', 4)])
                
                data.append({
                    "Date": str(date_val).strip(),
                    "Description": str(row[h_map.get('CHO.NO. NARRATION', 2)]).replace('\n', ' '),
                    "Nature": "Payment" if dr > 0 else "Receipt",
                    "Amount": dr if dr > 0 else cr
                })
    return pd.DataFrame(data)

# --- MAIN EXECUTION ---
if uploaded_file:
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            if bank_choice == "ICICI Bank":
                final_df = engine_icici(pdf)
            elif bank_choice == "Axis Bank":
                final_df = engine_axis(pdf)
            elif bank_choice == "Bank of Baroda":
                final_df = engine_bob(pdf)
            else:
                st.warning("Selected engine is under construction.")
                final_df = pd.DataFrame()

            if not final_df.empty:
                t_rec = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
                t_pay = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
                
                st.subheader(f"✅ Processed {len(final_df)} Transactions")
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Transactions", len(final_df))
                c2.metric("Total Receipts", f"₹{t_rec:,.2f}")
                c3.metric("Total Payments", f"₹{t_pay:,.2f}")
                
                st.dataframe(final_df, use_container_width=True)
                
                # Excel Download
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False)
                st.download_button("📥 Download Excel Report", out.getvalue(), f"{bank_choice}_Processed.xlsx")
            else:
                st.error("No transactions found. Ensure you selected the correct bank for the uploaded file.")
    except Exception as e:
        st.error(f"Error processing PDF: {e}")