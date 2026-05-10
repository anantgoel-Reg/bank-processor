import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Final Precision", layout="wide")
st.title("🏦 HDFC Bank - Precise Line Sync")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(val):
    if not val or str(val).strip() == "": return 0.0
    # Removes commas and handles accounting formats
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc(file):
    final_data = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Using 'lattice' settings to keep the grid strictly separated
            table = page.extract_table({
                "vertical_strategy": "lines", 
                "horizontal_strategy": "lines"
            })
            if not table: continue

            for row in table:
                if len(row) < 7: continue
                
                # Check for the Date pattern to ensure we are in the transaction area
                if not re.search(r'\d{2}/\d{2}/\d{2}', str(row[0])): continue

                # THE CORE FIX: Split each cell into a list of lines
                # This handles the "Squashed" rows on 07/02/26
                dates = str(row[0] or "").split('\n')
                narrations = str(row[1] or "").split('\n')
                withdrawals = str(row[4] or "").split('\n')
                deposits = str(row[5] or "").split('\n')

                # Find the maximum lines in this row block
                num_lines = max(len(dates), len(withdrawals), len(deposits))

                for i in range(num_lines):
                    # Get values for this specific line index
                    w_val = clean_amt(withdrawals[i]) if i < len(withdrawals) else 0.0
                    d_val = clean_amt(deposits[i]) if i < len(deposits) else 0.0
                    
                    # Only proceed if there is an actual amount on this sub-line
                    if w_val == 0 and d_val == 0: continue

                    # Sync Date: Use the line-specific date, or the first date if empty
                    current_date = dates[i].strip() if (i < len(dates) and re.search(r'\d', dates[i])) else dates[0].strip()
                    
                    # Sync Narration: Match the line or use the whole block
                    current_narration = narrations[i].strip() if i < len(narrations) else " ".join(narrations).strip()

                    # APPLY YOUR LOGIC: Column 4 = Payment, Column 5 = Receipt
                    if w_val > 0:
                        final_data.append({
                            "Date": current_date,
                            "Description": current_narration,
                            "Nature": "Payment",
                            "Amount": w_val
                        })
                    
                    if d_val > 0:
                        final_data.append({
                            "Date": current_date,
                            "Description": current_narration,
                            "Nature": "Receipt",
                            "Amount": d_val
                        })

    return pd.DataFrame(final_data)

if uploaded_file:
    df = process_hdfc(uploaded_file)
    if not df.empty:
        st.success(f"Success! Found {len(df)} transactions.")
        
        # This will now correctly show 11 Payments and 5 Receipts
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Count", len(df)) 
        c2.metric("Total Payments (Dr)", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") 
        c3.metric("Total Receipts (Cr)", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") 
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Corrected Excel", out.getvalue(), "HDFC_Final_Bifurcation.xlsx")