import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

# Set Page Config
st.set_page_config(page_title="FIN-EXTRACT AI", page_icon="🏦", layout="wide")

# Custom CSS for Black & Gold Theme based on your Logo
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #FFFFFF; }
    .stMetric { background-color: #1c1c1c; border: 1px solid #D4AF37; padding: 15px; border-radius: 10px; }
    div[data-testid="stMetricValue"] { color: #D4AF37 !important; }
    .stButton>button { background-color: #D4AF37; color: black; border-radius: 5px; font-weight: bold; }
    .stDownloadButton>button { background-color: #D4AF37 !important; color: black !important; border-radius: 5px; font-weight: bold; width: 100%; border: none; }
    h1, h2, h3 { color: #D4AF37 !important; }
    .stDataFrame { border: 1px solid #D4AF37; border-radius: 5px; }
    </style>
    """, unsafe_allow_value=True)

# UI Header with Logo
col_logo, col_title = st.columns([1, 5])
with col_logo:
    st.image("Screenshot 2026-05-09 at 1.57.49 PM.png", width=120)
with col_title:
    st.title("FIN-EXTRACT AI")
    st.markdown("### Standardized Multi-Bank Statement Processor")

st.divider()

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

def strict_clean_num(val):
    """Deep cleans values: handles 'INR 10,000', '500.00 Cr', and commas"""
    if val is None or str(val).strip() == "": return 0.0
    # Remove text, currency symbols, and commas
    s = str(val).upper().replace(',', '').replace('INR', '').replace('CR', '').replace('DR', '').strip()
    # Find the first number in the string
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    try:
        return float(nums[0]) if nums else 0.0
    except:
        return 0.0

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
        for page in pdf.pages:
            # Bank-specific extraction strategy
            if any(x in first_page_text.upper() for x in ["HDFC", "KOTAK"]):
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
                
            if not table: # Fallback to text-based parsing
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None
    
    df = pd.DataFrame(all_rows)
    
    # Identify Header Row
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join(map(str, row)).upper()
        if any(k in row_str for k in ['DATE', 'PARTICULARS', 'DESCRIPTION', 'WITHDRAWAL', 'DEBIT']):
            header_idx = i
            break
            
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    df = df[header_idx + 1:].reset_index(drop=True)

    # RULES MAPPING
    pay_cols = ['WITHDRAWAL AMT.', 'WITHDRAWALS', 'DEBITS', 'WITHDRAWAL (DR)', 'DEBIT AMOUNT', 'WITHDRAWAL', 'DEBIT']
    rec_cols = ['DEPOSIT AMT.', 'DEPOSITS', 'CREDITS', 'DEPOSIT (CR)', 'CREDIT AMOUNT', 'DEPOSIT', 'CREDIT']
    desc_cols = ['PARTICULARS', 'DESCRIPTION', 'REMARKS', 'NARRATION', 'TRANSACTION DETAILS']

    extracted = []
    for _, row in df.iterrows():
        nature, amount = "Check", 0.0
        
        # 1. Process Payments
        for col in pay_cols:
            if col in df.columns:
                v = strict_clean_num(row[col])
                if v > 0: nature, amount = "Payment", v
        
        # 2. Process Receipts
        for col in rec_cols:
            if col in df.columns:
                v = strict_clean_num(row[col])
                if v > 0: nature, amount = "Receipt", v

        # 3. Get Description & Date
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
        description = "N/A"
        for d_col in desc_cols:
            if d_col in df.columns and row[d_col]:
                description = str(row[d_col]).replace('\n', ' ').strip()
                break
        
        if amount > 0:
            extracted.append({
                'Date': str(date).strip(),
                'Description': description,
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(extracted)

if uploaded_file:
    with st.spinner('Processing Statement...'):
        try:
            final_df = process_pdf(uploaded_file)
            if final_df is not None and not final_df.empty:
                # Calculate Metrics
                t_rec = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
                t_pay = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
                
                # Show Summary Dashboard
                m1, m2, m3 = st.columns(3)
                m1.metric("Transactions Count", len(final_df))
                m2.metric("Total Receipts", f"₹{t_rec:,.2f}")
                m3.metric("Total Payments", f"₹{t_pay:,.2f}")

                st.markdown("### Unified Transaction Table")
                st.dataframe(final_df, use_container_width=True)

                # Excel Export
                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False, sheet_name='Sheet1')
                
                st.download_button(
                    label="📥 DOWNLOAD STANDARDIZED EXCEL",
                    data=excel_buffer.getvalue(),
                    file_name=f"Processed_{uploaded_file.name.split('.')[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("No valid transactions found in this PDF.")
        except Exception as e:
            st.error(f"Processing Error: {e}")