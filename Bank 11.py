import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

# Set Page Config and Theme
st.set_page_config(page_title="FinExtract AI", page_icon="🏦", layout="wide")

# Custom CSS for Black & Gold Theme (Based on Logo)
st.markdown("""
    <style>
    .main { background-color: #000000; color: #FFFFFF; }
    .stMetric { background-color: #1a1a1a; border: 1px solid #D4AF37; padding: 15px; border-radius: 10px; }
    div[data-testid="stMetricValue"] { color: #D4AF37 !important; }
    .stButton>button { background-color: #D4AF37; color: black; border-radius: 5px; font-weight: bold; width: 100%; }
    .stDownloadButton>button { background-color: #D4AF37; color: black; border-radius: 5px; font-weight: bold; }
    h1, h2, h3 { color: #D4AF37 !important; }
    </style>
    """, unsafe_allow_value=True)

# Layout: Logo and Title
col_l, col_r = st.columns([1, 4])
with col_l:
    # This displays your uploaded logo
    st.image("Screenshot 2026-05-09 at 1.57.49 PM.png", width=150)
with col_r:
    st.title("FIN-EXTRACT AI")
    st.subheader("Multi-Bank Standardized Processor")

uploaded_file = st.file_uploader("Upload Bank PDF (HDFC, IDBI, Indian, etc.)", type="pdf")

def strict_clean_num(val):
    """Specifically handles 'INR' prefix and 'Cr/Dr' suffixes for Indian/IDBI"""
    if val is None: return 0.0
    s = str(val).upper().replace(',', '').replace('INR', '').replace('CR', '').replace('DR', '').strip()
    # Extract only the numeric part
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    try:
        return float(nums[0]) if nums else 0.0
    except:
        return 0.0

def process_pdf_v3(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
        for page in pdf.pages:
            # HDFC needs Lattice (Line detection)
            if "HDFC" in first_page_text.upper():
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
                
            # Fallback for IDBI/Indian/Bandhan
            if not table:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None
    df = pd.DataFrame(all_rows)

    # Find the Header row by looking for key terms
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join(map(str, row)).upper()
        if any(k in row_str for k in ['DATE', 'PARTICULARS', 'WITHDRAWAL', 'DEBIT', 'DEBITS']):
            header_idx = i
            break
            
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    df = df[header_idx + 1:].reset_index(drop=True)

    extracted = []
    
    # --- STRICT MAPPING RULES ---
    # Rule 1: HDFC (Withdrawal Amt. / Deposit Amt.)
    # Rule 2: IDBI (Withdrawals / Deposits)
    # Rule 3: Indian (Debits / Credits)
    pay_cols = ['WITHDRAWAL AMT.', 'WITHDRAWALS', 'DEBITS', 'WITHDRAWAL (DR)', 'DEBIT AMOUNT', 'WITHDRAWAL', 'DEBIT']
    rec_cols = ['DEPOSIT AMT.', 'DEPOSITS', 'CREDITS', 'DEPOSIT (CR)', 'CREDIT AMOUNT', 'DEPOSIT', 'CREDIT']
    
    desc_keys = ['TRANSACTION DETAILS', 'PARTICULARS', 'NARRATION', 'DESCRIPTION', 'REMARKS']

    for _, row in df.iterrows():
        nature, amount = "", 0.0
        
        # Payment Logic
        for col in pay_cols:
            if col in df.columns:
                v = strict_clean_num(row[col])
                if v > 0: nature, amount = "Payment", v
        
        # Receipt Logic
        for col in rec_cols:
            if col in df.columns:
                v = strict_clean_num(row[col])
                if v > 0: nature, amount = "Receipt", v

        # Date & Description
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
        desc = "N/A"
        for k in desc_keys:
            if k in df.columns and row[k]:
                desc = str(row[k]).replace('\n', ' ').strip()
                break

        if amount > 0:
            extracted.append({'Date': date, 'Particulars': desc, 'Nature': nature, 'Amount': amount})

    return pd.DataFrame(extracted)

if uploaded_file:
    with st.spinner('Applying Bank-Specific Rules...'):
        data = process_pdf_v3(uploaded_file)
        if data is not None and not data.empty:
            # Metrics Row
            t_rec = data[data['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = data[data['Nature'] == 'Payment']['Amount'].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Transactions", len(data))
            m2.metric("Total Receipts", f"₹{t_rec:,.2f}")
            m3.metric("Total Payments", f"₹{t_pay:,.2f}")

            st.write("### Data Preview")
            st.dataframe(data, use_container_width=True)

            # Excel Export
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                data.to_excel(writer, index=False)
            st.download_button("📥 Download Gold-Standard Excel", out.getvalue(), "Statement_Bifurcated.xlsx")
        else:
            st.error("Structure not recognized. Please check if the PDF is a digital copy.")