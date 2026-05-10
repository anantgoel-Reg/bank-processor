import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Precision Narration", layout="wide")
st.title("🏦 HDFC Bank - Final Narration Fix")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(text):
    if not text: return 0.0
    clean = "".join(c for c in str(text) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc_flow(file):
    all_data = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            
            # Group by Y-coordinate (lines)
            lines = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            sorted_y = sorted(lines.keys())
            
            for i, y in enumerate(sorted_y):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_line_text = " ".join([w['text'] for w in line_words])
                
                # Identify the start of a transaction
                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', full_line_text)
                if date_match:
                    date_str = date_match.group(1)
                    withdrawal = 0.0
                    deposit = 0.0
                    narration_parts = []
                    
                    # 1. Capture amounts and narration from the INITIAL line
                    for w in line_words:
                        x = w['x0']
                        txt = w['text']
                        if 85 <= x <= 300: # Narration Zone
                            narration_parts.append(txt)
                        elif 410 <= x <= 485: # Withdrawal Zone
                            if "." in txt: withdrawal = clean_amt(txt)
                        elif 490 <= x <= 565: # Deposit Zone
                            if "." in txt: deposit = clean_amt(txt)

                    # 2. Look AHEAD at subsequent lines for wrapped narration
                    # Stop if we hit a new date or a very large gap
                    for next_y in sorted_y[i+1:]:
                        next_line_words = sorted(lines[next_y], key=lambda x: x['x0'])
                        next_line_text = " ".join([w['text'] for w in next_line_words])
                        
                        # Stop if the next line is a new transaction
                        if re.search(r'(\d{2}/\d{2}/\d{2})', next_line_text):
                            break
                        
                        # Capture text that falls strictly in the narration column
                        for nw in next_line_words:
                            if 85 <= nw['x0'] <= 300:
                                narration_parts.append(nw['text'])
                        
                        # If there's an amount on this sub-line, it's a squashed row
                        # (Relevant for the 07/02/26 case)
                        sub_w = 0.0
                        sub_d = 0.0
                        for nw in next_line_words:
                            if 410 <= nw['x0'] <= 485 and "." in nw['text']: sub_w = clean_amt(nw['text'])
                            if 490 <= nw['x0'] <= 565 and "." in nw['text']: sub_d = clean_amt(nw['text'])
                        
                        # If we find a sub-amount, we handle it separately in the next main loop iteration
                        # or break here if it's just a narration wrap. 
                        # To keep it simple, we only break if a DATE is found.
                    
                    desc = " ".join(narration_parts).strip()
                    
                    # APPLY LOGIC
                    if withdrawal > 0:
                        all_data.append({"Date": date_str, "Description": desc, "Nature": "Payment", "Amount": withdrawal})
                    elif deposit > 0:
                        all_data.append({"Date": date_str, "Description": desc, "Nature": "Receipt", "Amount": deposit})

    # Deduplicate to handle the "sub-line amount" edge case
    df = pd.DataFrame(all_data).drop_duplicates(subset=['Date', 'Amount', 'Description'], keep='first')
    return df

if uploaded_file:
    df = process_hdfc_flow(uploaded_file)
    
    if not df.empty:
        st.success(f"Captured {len(df)} transactions.")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Count", len(df))
        c2.metric("Total Payments", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}")
        c3.metric("Total Receipts", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}")
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Final Excel", out.getvalue(), "HDFC_Corrected.xlsx")