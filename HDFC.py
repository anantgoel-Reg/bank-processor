import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.title("🏦 Dedicated HDFC Statement Processor")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_hdfc_val(val):
    if val is None or str(val).strip() in ["", "None", "-"]:
        return 0.0
    # HDFC uses commas for thousands; we remove them to convert to float
    clean = str(val).replace(',', '').strip()
    try:
        return float(clean)
    except:
        return 0.0

def process_hdfc(file):
    all_data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # HDFC layout requires the 'lines' strategy to capture the grid correctly
            table = page.extract_table(table_settings={
                "vertical_strategy": "lines", 
                "horizontal_strategy": "lines"
            })
            
            if not table:
                continue

            # Identify headers for HDFC specifically
            headers = [str(c).replace('\n', ' ').strip() for c in table[0]]
            
            # Map the exact HDFC column names from your sample
            try:
                date_idx = headers.index("Date")
                desc_idx = headers.index("Narration")
                dr_idx = headers.index("Withdrawal Amt.")
                cr_idx = headers.index("Deposit Amt.")
            except ValueError:
                # If headers aren't on the first row, look deeper (up to row 10)
                continue

            for row in table[1:]:
                # Basic validation: ensure the date column has a date
                date_val = str(row[date_idx]).strip()
                if not re.search(r'\d', date_val):
                    continue

                dr_val = clean_hdfc_val(row[dr_idx])
                cr_val = clean_hdfc_val(row[cr_idx])

                nature = "Payment" if dr_val > 0 else "Receipt"
                amount = dr_val if dr_val > 0 else cr_val

                if amount > 0:
                    all_data.append({
                        "Date": date_val.split('\n')[0],
                        "Description": str(row[desc_idx]).replace('\n', ' '),
                        "Nature": nature,
                        "Amount": amount
                    })

    return pd.DataFrame(all_data)

if uploaded_file:
    df = process_hdfc(uploaded_file)
    if not df.empty:
        # Summary Metrics based on sample data totals
        # Total Debits should match ~31,245.02 and Credits ~60,002.00 [cite: 44, 45]
        st.write("### HDFC Transaction Summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Transactions", len(df))
        c2.metric("Total Receipts", f"₹{df[df['Nature'] == 'Receipt']['Amount'].sum():,.2f}")
        c3.metric("Total Payments", f"₹{df[df['Nature'] == 'Payment']['Amount'].sum():,.2f}")
        
        st.dataframe(df, use_container_width=True)
        
        # Excel Export
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download HDFC Data", out.getvalue(), "HDFC_Processed.xlsx")