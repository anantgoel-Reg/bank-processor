import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

# --- SETTINGS ---
st.set_page_config(page_title="Pro Bank Parser", layout="wide")
st.title("🏦 Enterprise Multi-Bank Processor")

# --- UTILITY: VALUE CLEANER ---
def clean_val(val):
    if val is None: return 0.0
    s = str(val).replace(',', '').replace('INR', '').strip()
    if not s or any(x in s.lower() for x in ["none", "-", "balance", "date"]): return 0.0
    nums = re.findall(r'(\d+\.\d+|\d+)', s)
    try: return float(nums[0]) if nums else 0.0
    except: return 0.0

# --- BANK ENGINES ---

def extract_axis(pages):
    data = []
    for page in pages:
        table = page.extract_table()
        if table:
            for row in table:
                row_str = " ".join([str(x) for x in row if x]).upper()
                # Detect Axis 1 (Indicator) vs Axis 2 (Dual Column)
                date_m = re.search(r'\d{2}/\d{2}/\d{4}', row_str)
                if date_m:
                    if 'CR' in row_str or 'DR' in row_str: # Indicator
                        data.append({"Date": date_m.group(), "Desc": row[3], "Nature": "Receipt" if "CR" in row_str else "Payment", "Amount": clean_val(row[4])})
                    else: # Dual Column
                        d_amt, c_amt = clean_val(row[3]), clean_val(row[4])
                        if d_amt > 0: data.append({"Date": date_m.group(), "Desc": row[5], "Nature": "Payment", "Amount": d_amt})
                        elif c_amt > 0: data.append({"Date": date_m.group(), "Desc": row[5], "Nature": "Receipt", "Amount": c_amt})
    return pd.DataFrame(data)

def extract_hdfc(pages):
    data = []
    for page in pages:
        # HDFC needs strict line detection
        table = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
        if table:
            for row in table:
                date_m = re.search(r'\d{2}/\d{2}/\d{2}', str(row[0]))
                if date_m:
                    w_amt, d_amt = clean_val(row[4]), clean_val(row[5])
                    if w_amt > 0: data.append({"Date": date_m.group(), "Desc": row[2], "Nature": "Payment", "Amount": w_amt})
                    elif d_amt > 0: data.append({"Date": date_m.group(), "Desc": row[2], "Nature": "Receipt", "Amount": d_amt})
    return pd.DataFrame(data)

def extract_icici(pages):
    data = []
    for page in pages:
        table = page.extract_table()
        if table:
            for row in table:
                row_str = " ".join([str(x) for x in row if x]).upper()
                date_m = re.search(r'\d{2}-[A-Za-z]{3}-\d{4}|\d{2}/\d{2}/\d{4}', row_str)
                if date_m:
                    # Logic for ICICI standard dual column
                    w_amt, d_amt = clean_val(row[-3]), clean_val(row[-2])
                    if w_amt > 0: data.append({"Date": date_m.group(), "Desc": row[4], "Nature": "Payment", "Amount": w_amt})
                    elif d_amt > 0: data.append({"Date": date_m.group(), "Desc": row[4], "Nature": "Receipt", "Amount": d_amt})
    return pd.DataFrame(data)

# --- MAIN CONTROLLER ---

uploaded_file = st.file_uploader("Upload Bank Statement", type="pdf")

if uploaded_file:
    with pdfplumber.open(uploaded_file) as pdf:
        # STEP 1: IDENTIFY THE BANK
        first_page_text = (pdf.pages[0].extract_text() or "").upper()
        bank_detected = "UNKNOWN"
        
        if "AXIS BANK" in first_page_text: bank_detected = "AXIS"
        elif "HDFC BANK" in first_page_text: bank_detected = "HDFC"
        elif "ICICI BANK" in first_page_text: bank_detected = "ICICI"
        elif "KOTAK" in first_page_text: bank_detected = "KOTAK"
        elif "STATE BANK OF INDIA" in first_page_text or "SBI" in first_page_text: bank_detected = "SBI"
        
        st.info(f"Detected Bank: **{bank_detected}**")

        # STEP 2: EXECUTE SPECIFIC ENGINE
        df = pd.DataFrame()
        if bank_detected == "AXIS": df = extract_axis(pdf.pages)
        elif bank_detected == "HDFC": df = extract_hdfc(pdf.pages)
        elif bank_detected == "ICICI": df = extract_icici(pdf.pages)
        # ... Add other bank elifs here
        
        if not df.empty:
            # STEP 3: SUMMARY & DISPLAY
            receipts = df[df['Nature'] == 'Receipt']['Amount'].sum()
            payments = df[df['Nature'] == 'Payment']['Amount'].sum()

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Transactions", len(df))
            c2.metric("Total Receipts (CR)", f"₹{receipts:,.2f}")
            c3.metric("Total Payments (DR)", f"₹{payments:,.2f}")

            st.dataframe(df, use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", output.getvalue(), "Statement.xlsx")
        else:
            st.error("Identification successful, but failed to parse rows. Ensure the PDF is not a scanned image.")