import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Absolute Position", layout="wide")
st.title("🏦 HDFC Bank - Positional Extraction")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(text):
    if not text: return 0.0
    clean = "".join(c for c in str(text) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc_positional(file):
    all_data = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Get every word and its horizontal (x0) and vertical (top) position
            words = page.extract_words(keep_blank_chars=False)
            
            # Group words by their vertical line (y-coordinate)
            # We round to 0 decimal to catch words on the same visual line
            lines = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_line_text = " ".join([w['text'] for w in line_words])
                
                # Check if this line is a transaction (starts with a date)
                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', full_line_text)
                if not date_match:
                    continue
                
                date_str = date_match.group(1)
                narration_parts = []
                withdrawal = 0.0
                deposit = 0.0

                for w in line_words:
                    x = w['x0']
                    text = w['text']
                    
                    # Logic based on horizontal X-coordinates:
                    # 1. Narration Column (Starts early, ends before amount area)
                    if 85 < x < 350:
                        narration_parts.append(text)
                    
                    # 2. Withdrawal Column (The 'Left' side of the amount section)
                    # Standard HDFC Withdrawal x-coord is usually between 390 and 460
                    elif 385 <= x <= 470:
                        if "." in text: withdrawal = clean_amt(text)
                    
                    # 3. Deposit Column (The 'Right' side of the amount section)
                    # Standard HDFC Deposit x-coord is usually between 475 and 550
                    elif 471 <= x <= 560:
                        if "." in text: deposit = clean_amt(text)

                # Applying your exact logic
                if withdrawal > 0:
                    all_data.append({
                        "Date": date_str,
                        "Description": " ".join(narration_parts),
                        "Nature": "Payment",
                        "Amount": withdrawal
                    })
                elif deposit > 0:
                    all_data.append({
                        "Date": date_str,
                        "Description": " ".join(narration_parts),
                        "Nature": "Receipt",
                        "Amount": deposit
                    })

    return pd.DataFrame(all_data)

if uploaded_file:
    df = process_hdfc_positional(uploaded_file)
    
    if not df.empty:
        st.success(f"Captured {len(df)} transactions using Positional Mapping.")
        
        # Cross-verify with your specific statement totals
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Transactions", len(df)) # Target: 16
        c2.metric("Total Payments (Dr)", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") # Target: 31,245.02
        c3.metric("Total Receipts (Cr)", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") # Target: 60,002.00
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", out.getvalue(), "HDFC_Positional_Statement.xlsx")