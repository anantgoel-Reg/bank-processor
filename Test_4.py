import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Narration Fix", layout="wide")
st.title("🏦 HDFC Bank - Final Narration Alignment")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(text):
    if not text: return 0.0
    # Clean standard currency format
    clean = "".join(c for c in str(text) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc_anchored(file):
    all_transactions = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            
            # Group words by their vertical (Y) line
            lines = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            sorted_y = sorted(lines.keys())
            
            for i, y in enumerate(sorted_y):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_line_text = " ".join([w['text'] for w in line_words])
                
                # Check for Date (DD/MM/YY)
                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', full_line_text)
                if date_match:
                    date_str = date_match.group(1)
                    
                    # We initialize containers for this specific transaction
                    withdrawal = 0.0
                    deposit = 0.0
                    narration_parts = []
                    
                    # Find the physical boundaries for Narration in THIS specific line
                    # We know Narration starts after the date (usually x > 80)
                    # and ends before the Chq/Ref or Value Date (usually x < 310)
                    for w in line_words:
                        x = w['x0']
                        txt = w['text']
                        
                        # NARATION ZONE: Strictly between Date and Reference Column
                        if 85 < x < 305: 
                            # Filter out common header leftovers or noise
                            if txt.lower() not in ["narration", "chq/ref.no.", "value"]:
                                narration_parts.append(txt)
                        
                        # WITHDRAWAL ZONE: x is roughly 410-480
                        elif 400 < x < 485:
                            if "." in txt: withdrawal = clean_amt(txt)
                        
                        # DEPOSIT ZONE: x is roughly 490-560
                        elif 486 < x < 570:
                            if "." in txt: deposit = clean_amt(txt)

                    # Multi-line Narration Check:
                    # Look at the lines below. If they have NO date and NO amount, 
                    # but have text in the Narration column, it's a wrap-around.
                    for next_y in sorted_y[i+1:]:
                        next_line_words = sorted(lines[next_y], key=lambda x: x['x0'])
                        next_line_txt = " ".join([w['text'] for w in next_line_words])
                        
                        # Stop if we hit a new date or an amount (new transaction)
                        if re.search(r'(\d{2}/\d{2}/\d{2})', next_line_txt): break
                        
                        has_amt = False
                        for nw in next_line_words:
                            if 400 < nw['x0'] < 570 and "." in nw['text']:
                                has_amt = True
                                break
                        if has_amt: break

                        # Collect wrapped narration text
                        for nw in next_line_words:
                            if 85 < nw['x0'] < 305:
                                narration_parts.append(nw['text'])

                    final_desc = " ".join(narration_parts).strip()
                    
                    # Store based on Withdrawal vs Deposit logic
                    if withdrawal > 0:
                        all_transactions.append({"Date": date_str, "Description": final_desc, "Nature": "Payment", "Amount": withdrawal})
                    elif deposit > 0:
                        all_transactions.append({"Date": date_str, "Description": final_desc, "Nature": "Receipt", "Amount": deposit})

    # Final cleanup: HDFC sometimes repeats rows across page breaks
    df = pd.DataFrame(all_transactions).drop_duplicates()
    return df

if uploaded_file:
    df = process_hdfc_anchored(uploaded_file)
    
    if not df.empty:
        st.success(f"Success! Captured {len(df)} transactions.")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Count", len(df))
        c2.metric("Total Payments", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}")
        c3.metric("Total Receipts", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}")
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Final Excel", out.getvalue(), "HDFC_Clean_Statement.xlsx")