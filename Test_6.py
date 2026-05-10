import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Final Precision", layout="wide")
st.title("🏦 HDFC Bank - Locked-In Logic")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(text):
    if not text: return 0.0
    clean = "".join(c for c in str(text) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc_locked(file):
    final_rows = []
    
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
                
                # Detect the start of a transaction via Date
                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', full_line_text)
                if date_match:
                    date_str = date_match.group(1)
                    
                    # 1. Initialize for this transaction
                    withdrawal = 0.0
                    deposit = 0.0
                    narration_parts = []
                    
                    # 2. Extract components based on FIXED X-Coordinates
                    for w in line_words:
                        x = w['x0']
                        txt = w['text']
                        
                        # NARRATION: Only take text in this specific horizontal band
                        if 90 <= x <= 290: 
                            narration_parts.append(txt)
                        
                        # WITHDRAWAL (Payment): The middle-right column
                        elif 410 <= x <= 480:
                            if "." in txt: withdrawal = clean_amt(txt)
                        
                        # DEPOSIT (Receipt): The far-right column
                        elif 485 <= x <= 560:
                            if "." in txt: deposit = clean_amt(text=txt)

                    # 3. Handle Wrapped Narration (Multi-line)
                    # Check lines below that don't have a new date or new amounts
                    for next_y in sorted_y[i+1:]:
                        next_line_words = sorted(lines[next_y], key=lambda x: x['x0'])
                        next_line_txt = " ".join([w['text'] for w in next_line_words])
                        
                        if re.search(r'\d{2}/\d{2}/\d{2}', next_line_txt): break # Stop at next date
                        
                        has_val = False
                        for nw in next_line_words:
                            if 410 <= nw['x0'] <= 560 and "." in nw['text']:
                                has_val = True # Stop if we hit a new amount (squashed row)
                        if has_val: break
                        
                        for nw in next_line_words:
                            if 90 <= nw['x0'] <= 290:
                                narration_parts.append(nw['text'])

                    desc = " ".join(narration_parts).strip()

                    # 4. Apply strict Payment/Receipt Logic
                    if withdrawal > 0:
                        final_rows.append({"Date": date_str, "Description": desc, "Nature": "Payment", "Amount": withdrawal})
                    if deposit > 0:
                        final_rows.append({"Date": date_str, "Description": desc, "Nature": "Receipt", "Amount": deposit})

    df = pd.DataFrame(final_rows).drop_duplicates()
    return df

if uploaded_file:
    df = process_hdfc_locked(uploaded_file)
    if not df.empty:
        st.success(f"Captured {len(df)} transactions.")
        
        # Validation Metrics (Targeting your specific 16-trans totals)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Count", len(df)) # Target: 16
        c2.metric("Total Payments", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") # Target: 31,245.02
        c3.metric("Total Receipts", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") # Target: 60,002.00
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Final Excel", out.getvalue(), "HDFC_Corrected_Final.xlsx")