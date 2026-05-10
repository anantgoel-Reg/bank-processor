import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Final Precision", layout="wide")
st.title("🏦 HDFC Bank - Precise Column Mapping")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(text):
    if not text: return 0.0
    clean = "".join(c for c in str(text) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc_final(file):
    all_data = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            
            # Group by vertical line
            lines = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_line_text = " ".join([w['text'] for w in line_words])
                
                # Check for Date (DD/MM/YY)
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
                    
                    # 1. NARATION ONLY (Narrowed X-range to avoid Ref No column)
                    # We stop at x=290 because Chq/Ref usually starts around 300
                    if 90 <= x <= 295:
                        narration_parts.append(text)
                    
                    # 2. WITHDRAWAL (Payment)
                    elif 415 <= x <= 485:
                        if "." in text: withdrawal = clean_amt(text)
                    
                    # 3. DEPOSIT (Receipt)
                    elif 490 <= x <= 565:
                        if "." in text: deposit = clean_amt(text)

                # Use Date and Narration only if we found an amount
                desc = " ".join(narration_parts).strip()
                
                if withdrawal > 0:
                    all_data.append({"Date": date_str, "Description": desc, "Nature": "Payment", "Amount": withdrawal})
                elif deposit > 0:
                    all_data.append({"Date": date_str, "Description": desc, "Nature": "Receipt", "Amount": deposit})

    return pd.DataFrame(all_data)

if uploaded_file:
    df = process_hdfc_final(uploaded_file)
    
    if not df.empty:
        st.success(f"Captured {len(df)} transactions.")
        
        # Validation Metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Count", len(df)) # Target: 16
        c2.metric("Total Payments (Dr)", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") # 31,245.02
        c3.metric("Total Receipts (Cr)", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") # 60,002.00
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Final Excel", out.getvalue(), "HDFC_Corrected_Statement.xlsx")