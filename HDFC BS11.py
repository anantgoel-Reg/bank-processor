import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Precision Fix", layout="wide")
st.title("🏦 HDFC Bank - Precise Column Alignment")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(val):
    if not val or str(val).strip() == "": return 0.0
    # Remove commas and non-numeric junk
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean) if clean else 0.0
    except: return 0.0

def process_hdfc(file):
    final_data = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # We use a very strict 'lines' strategy to maintain column integrity
            table = page.extract_table({
                "vertical_strategy": "lines", 
                "horizontal_strategy": "lines",
                "snap_tolerance": 3
            })
            if not table: continue

            for row in table:
                # HDFC standard table has 7 columns 
                if len(row) < 7: continue
                
                # Identify valid rows by looking for the Date pattern (DD/MM/YY) 
                raw_date_cell = str(row[0] or "").strip()
                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', raw_date_cell)
                if not date_match: continue
                
                # Split cells by newline to handle "stacked" transactions (like on 07/02/26) 
                lines_date = raw_date_cell.split('\n')
                lines_narration = str(row[1] or "").split('\n')
                lines_withdrawal = str(row[4] or "").split('\n')
                lines_deposit = str(row[5] or "").split('\n')

                # Determine the true number of transactions in this visual block
                num_entries = max(len(lines_withdrawal), len(lines_deposit))

                for i in range(num_entries):
                    # Get values for this specific line index
                    w_val = clean_amt(lines_withdrawal[i]) if i < len(lines_withdrawal) else 0.0
                    d_val = clean_amt(lines_deposit[i]) if i < len(lines_deposit) else 0.0
                    
                    # Logic: Only process if there is a number in THAT SPECIFIC line/column
                    if w_val == 0 and d_val == 0: continue

                    # Assign Date: Use specific line date if available, otherwise fallback to row's primary date
                    current_date = lines_date[i].strip() if (i < len(lines_date) and re.search(r'\d', lines_date[i])) else lines_date[0].strip()
                    
                    # Assign Narration: Use specific line if available, otherwise use the whole block
                    current_narration = lines_narration[i].strip() if i < len(lines_narration) else " ".join(lines_narration).strip()

                    # Apply Strict Column Mapping
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
        # Cross-verify with the Statement Summary [cite: 154, 155, 156, 157]
        st.success(f"Successfully processed {len(df)} transactions.")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Transactions", len(df)) # Target: 16
        c2.metric("Total Payments (Dr)", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") # Target: 31,245.02
        c3.metric("Total Receipts (Cr)", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") # Target: 60,002.00
        
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Corrected Excel", out.getvalue(), "HDFC_Precision_Final.xlsx")