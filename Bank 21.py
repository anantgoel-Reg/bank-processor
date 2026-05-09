import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

# --- UI CONFIGURATION & THEMING ---
st.set_page_config(page_title="Master Bank AI", layout="wide")

# Custom CSS to match your screenshot (Dark Indigo/Slate Theme)
st.markdown("""
    <style>
    .stApp {
        background-color: #0E1117;
        color: #FFFFFF;
    }
    [data-testid="stMetricValue"] {
        color: #6366F1;
        font-size: 1.8rem !important;
    }
    [data-testid="stMetricLabel"] {
        color: #94A3B8;
    }
    .stDataFrame {
        border: 1px solid #1E293B;
        border-radius: 10px;
    }
    .stButton>button {
        background-color: #4F46E5;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 2rem;
    }
    .stButton>button:hover {
        background-color: #6366F1;
        border: none;
    }
    h1 {
        color: #F8FAFC;
        font-weight: 700;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🏦 Financial Bifurcator AI")
st.subheader("Standardized Bank Statement Processing")

uploaded_file = st.file_uploader("Upload Bank PDF (HDFC, Axis, ICICI, etc.)", type="pdf")

# --- CORE LOGIC FUNCTIONS ---

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: return 0.0
    s = str(val).replace(',', '').strip()
    # Guard: If it looks like a date, it is not an amount
    if "/" in s or ("-" in s and len(s) > 5): return 0.0
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    try: return float(nums[0]) if nums else 0.0
    except: return 0.0

def process_pdf(file):
    all_rows = []
    with pdfplumber.open(file) as pdf:
        # Detect if it's HDFC or others for strategy
        bank_text = (pdf.pages[0].extract_text() or "").upper()
        
        for page in pdf.pages:
            if "HDFC" in bank_text:
                table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            else:
                table = page.extract_table()
            
            if not table or len(table) < 2:
                table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            
            if table: all_rows.extend(table)
    
    if not all_rows: return None

    # 1. Header Detection
    header_idx = 0
    for i, row in enumerate(all_rows):
        row_str = " ".join([str(x) for x in row if x]).upper()
        if 'DATE' in row_str and any(k in row_str for k in ['PARTICULARS', 'DESCRIPTION', 'CR/DR']):
            header_idx = i
            break
    
    headers = [str(c).replace('\n', ' ').strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]

    # 2. Strict Mapping (Rollback version)
    # Finding columns without 'greedy' keyword matching
    amt_col = next((c for c in headers if 'AMOUNT(INR)' in c or 'TRANSACTION AVAILABLE AMOUNT' in c), None)
    ind_col = next((c for c in headers if 'DEBIT/CREDIT' in c or 'CR/DR' in c), None)
    date_col = next((i for i, h in enumerate(headers) if 'DATE' in h and 'VALUE' not in h), 
                    next((i for i, h in enumerate(headers) if 'DATE' in h), 0))
    desc_col_idx = next((i for i, h in enumerate(headers) if any(k in h for k in ['DESC', 'PARTICULARS', 'REMARK'])), 1)

    extracted = []
    current_txn = None

    for row_data in data_rows:
        row = [str(x).replace('\n', ' ').strip() if x else "" for x in row_data]
        if not any(row): continue
        
        # Determine Amount and Nature
        nature, amount = "Check", 0.0
        if amt_col and ind_col:
            v = clean_val(row[headers.index(amt_col)])
            indicator = str(row[headers.index(ind_col)]).upper()
            if 'CR' in indicator: nature, amount = "Receipt", v
            elif 'DR' in indicator: nature, amount = "Payment", v
        else:
            # HDFC / Two-column fallback
            pay_keys = ['WITHDRAWAL AMT.', 'WITHDRAWALS', 'DEBITS', 'WITHDRAWAL', 'DEBIT']
            rec_keys = ['DEPOSIT AMT.', 'DEPOSITS', 'CREDITS', 'DEPOSIT', 'CREDIT']
            for i, h in enumerate(headers):
                if any(k in h for k in pay_keys) and clean_val(row[i]) > 0:
                    nature, amount = "Payment", clean_val(row[i])
                if any(k in h for k in rec_keys) and clean_val(row[i]) > 0:
                    nature, amount = "Receipt", clean_val(row[i])

        # Date handling
        date_val = row[date_col] if isinstance(date_col, int) else ""
        has_date = len(re.findall(r'\d{1,2}[/-]\d{1,2}', date_val)) > 0
        
        if has_date and amount > 0:
            if current_txn: extracted.append(current_txn)
            current_txn = {
                'Date': date_val.split()[-1] if len(date_val) > 15 else date_val,