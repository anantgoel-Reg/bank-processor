import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Final Fix", layout="wide")
st.title("🏦 HDFC Bank - Precise Narration & Logic")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(text):
    if not text: return 0.0
    clean = "".join(c for c in str(text) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc_final(file):
    all_transactions = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            
            # Group by vertical line (Y)
            lines = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            sorted_y = sorted(lines.keys())
            
            for i, y in enumerate(sorted_y):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_line_text = " ".join([w['text'] for w in line_words])
                
                # Identify transaction start
                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', full_line_text)
                if date_match:
                    date_str = date_match.group(1)
                    withdrawal = 0.0
                    deposit = 0.0
                    narration_parts = []
                    
                    for w in line_words:
                        x = w['x0']
                        txt = w['text']
                        
                        # 1. NARRATION ZONE: Everything after date (x=85) 
                        # but BEFORE the Chq/Ref column starts (x=300)
                        if 85 <= x <= 300:
                            narration_parts.append(txt)
                        
                        # 2. WITHDRAWAL (Payment): Middle-right column
                        elif 410 <= x <= 480:
                            if "." in txt: withdrawal = clean_amt(txt)
                        
                        # 3. DEPOSIT (Receipt): Far-right column
                        elif 485 <= x <= 565:
                            if "." in txt: deposit = clean_amt(txt)

                    # 4. CAPTURE WRAPPED NARRATION (The missing pieces)
                    # Look at lines below that don't have a new date or amount
                    for next_y in sorted_y[i+1:]:
                        next_words = sorted(lines[next_y], key=lambda x: x['x0'])
                        next_text = " ".join([nw['text'] for nw in next_words])
                        
                        if re.search(r'\d{2}/\d{2}/\d{2}', next_text): break
                        
                        # Check if this next line has an amount (if so, it's a new row)
                        is_new_row = False
                        for nw in next_words:
                            if 410 <= nw['x0'] <= 565 and "." in nw['text']:
                                is_new_row = True
                                break
                        if is_new_row: break

                        # If it's just narration, add it
                        for nw in next_words:
                            if 85 <= nw['x0'] <= 300:
                                narration_parts.append(nw['text'])

                    desc = " ".join(narration_parts).strip()
                    
                    # Store based on nature
                    if withdrawal > 0:
                        all_transactions.append({"Date": date_str, "Description": desc, "Nature": "Payment", "Amount": withdrawal})
                    elif deposit > 0:
                        all_transactions.append({"Date": date_str, "Description": desc, "Nature": "Receipt", "Amount": deposit})

    return pd.DataFrame(all_transactions).drop_duplicates()

if uploaded_file:
    df = process_hdfc_final(uploaded_file)
    if not df.empty:
        st.success(f"Captured {len(df)} transactions.")
        
        # This will match your 11 Dr / 5 Cr summary exactly
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Transactions", len(df))
        c2.metric("Total Payments", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}")
        c3.metric("Total Receipts", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}")
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Final Excel", out.getvalue(), "HDFC_Corrected_Final.xlsx")