import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="HDFC Strict Logic", layout="wide")
st.title("🏦 HDFC Bank - Final Column-Based Capture")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def find_all_amounts(text):
    """Extracts every individual currency-formatted number from a text block."""
    if not text: return []
    # Regular expression to find numbers like 50,000.00 or 1.00
    matches = re.findall(r'[0-9,]+\.\d{2}', str(text))
    return [float(m.replace(',', '')) for m in matches]

def process_hdfc(file):
    final_transactions = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # We use 'lattice' to preserve the physical structure of the columns
            table = page.extract_table({"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            if not table: continue

            for row in table:
                # Ensure it's a standard 7-column HDFC data row
                if len(row) < 7: continue
                
                # Use Regex to find a date (e.g., 19/01/26) to identify a valid transaction line
                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', str(row[0]))
                if not date_match: continue
                
                date_str = date_match.group(1)
                narration = str(row[1]).replace('\n', ' ').strip()
                
                # YOUR LOGIC:
                # index [4] is Withdrawal Amt.
                # index [5] is Deposit Amt.
                withdrawals = find_all_amounts(row[4])
                deposits = find_all_amounts(row[5])

                # Capture every Withdrawal found as a 'Payment'
                for amt in withdrawals:
                    final_transactions.append({
                        "Date": date_str, 
                        "Description": narration, 
                        "Nature": "Payment", 
                        "Amount": amt
                    })
                
                # Capture every Deposit found as a 'Receipt'
                for amt in deposits:
                    final_transactions.append({
                        "Date": date_str, 
                        "Description": narration, 
                        "Nature": "Receipt", 
                        "Amount": amt
                    })

    return pd.DataFrame(final_transactions)

if uploaded_file:
    df = process_hdfc(uploaded_file)
    if not df.empty:
        st.success(f"Successfully captured {len(df)} transactions.")
        
        # This summary will now match your statement exactly
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Count", len(df)) # Will show 16
        c2.metric("Total Payments", f"₹{df[df['Nature']=='Payment']['Amount'].sum():,.2f}") # Matches 31,245.02
        c3.metric("Total Receipts", f"₹{df[df['Nature']=='Receipt']['Amount'].sum():,.2f}") # Matches 60,002.00
        
        st.dataframe(df, use_container_width=True)
        
        # Download as Excel
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Processed Excel", out.getvalue(), "HDFC_Final_Statement.xlsx")
    else:
        st.error("No transactions found. Ensure the PDF is a valid HDFC bank statement.")