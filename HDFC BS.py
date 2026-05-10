import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="HDFC Statement Processor", layout="wide")
st.title("🏦 Specialized HDFC Bank Statement AI")

uploaded_file = st.file_uploader("Upload HDFC Bank PDF", type="pdf")

def clean_val(val):
    if val is None or str(val).strip() in ["", "None", "-", "0", "0.00"]: 
        return 0.0
    # Removes commas and handles the specific HDFC number format
    clean = str(val).replace(',', '').strip()
    try: 
        return float(clean)
    except: 
        return 0.0

def process_hdfc_pdf(file):
    all_data = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # HDFC statements have clear grid lines, so 'lines' strategy is best
            table = page.extract_table(table_settings={
                "vertical_strategy": "lines", 
                "horizontal_strategy": "lines"
            })
            
            if not table:
                continue

            # Identify the header row specifically for HDFC
            headers = []
            header_row_idx = -1
            for i, row in enumerate(table):
                row_str = " ".join([str(cell) for cell in row if cell]).upper()
                if "WITHDRAWAL AMT." in row_str and "DEPOSIT AMT." in row_str:
                    headers = [str(c).replace('\n', ' ').strip() for c in row]
                    header_row_idx = i
                    break
            
            if header_row_idx == -1:
                continue

            # Map the columns
            try:
                date_idx = headers.index("Date")
                desc_idx = headers.index("Narration")
                wd_idx = headers.index("Withdrawal Amt.")
                dp_idx = headers.index("Deposit Amt.")
            except ValueError:
                continue

            # Process data rows
            for row in table[header_row_idx + 1:]:
                date_val = str(row[date_idx]).strip()
                # Skip rows that don't start with a date (like multi-line narration continuations)
                if not re.search(r'\d{2}/\d{2}/\d{2}', date_val):
                    continue
                
                withdrawal = clean_val(row[wd_idx])
                deposit = clean_val(row[dp_idx])
                
                nature, amount = "Check", 0.0
                if withdrawal > 0:
                    nature, amount = "Payment", withdrawal
                elif deposit > 0:
                    nature, amount = "Receipt", deposit
                
                if amount > 0:
                    all_data.append({
                        "Date": date_val,
                        "Description": str(row[desc_idx]).replace('\n', ' ').strip(),
                        "Nature": nature,
                        "Amount": amount
                    })

    return pd.DataFrame(all_data)

if uploaded_file:
    try:
        final_df = process_hdfc_pdf(uploaded_file)
        if not final_df.empty:
            # Metrics based on your specific HDFC file totals
            t_rec = final_df[final_df['Nature'] == 'Receipt']['Amount'].sum()
            t_pay = final_df[final_df['Nature'] == 'Payment']['Amount'].sum()
            
            st.subheader("Statement Summary")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Transactions", len(final_df))
            c2.metric("Total Receipts", f"₹{t_rec:,.2f}")
            c3.metric("Total Payments", f"₹{t_pay:,.2f}")
            
            st.dataframe(final_df, use_container_width=True)
            
            # Excel Download
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Download HDFC Excel Report", out.getvalue(), "HDFC_Processed.xlsx")
        else:
            st.error("No transactions found. Please ensure this is a standard HDFC Bank statement.")
    except Exception as e:
        st.error(f"Error processing PDF: {e}")