import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Universal Bank Processor", layout="wide")

st.title("🏦 Universal Bank Statement Processor")
st.markdown("---")

uploaded_file = st.file_uploader("Upload Bank PDF (HDFC, Kotak, ICICI, etc.)", type="pdf")

def clean_amount(val):
    """Deep cleans currency strings into floats"""
    if val is None or str(val).strip() == "": return 0.0
    # Remove commas, symbols, and extra spaces
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try:
        return float(clean)
    except:
        return 0.0

def process_statement(file):
    all_rows = []
    
    # ADVANCED PDF READING
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # We use 'lattice' strategy to find table lines in HDFC/Kotak
            table = page.extract_table(table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_header_resolution": 100
            })
            
            # If standard lattice fails, fallback to text-based extraction
            if not table:
                table = page.extract_table()
                
            if table:
                all_rows.extend(table)
    
    if not all_rows: return None

    df = pd.DataFrame(all_rows)
    # Clean headers: Remove newlines and trim whitespace
    df.columns = [str(c).replace('\n', ' ').strip().upper() for c in df.iloc[0]]
    df = df[1:].reset_index(drop=True)

    final_results = []

    for _, row in df.iterrows():
        nature = "Check"
        amount = 0.0
        
        # --- DEFINING HEADER GROUPS ---
        # HDFC/Kotak/ICICI format
        withdrawal_cols = ['WITHDRAWAL (DR.)', 'WITHDRAWAL (DR)', 'WITHDRAWAL AMT.', 'WITHDRAWAL']
        deposit_cols = ['DEPOSIT (CR.)', 'DEPOSIT (CR)', 'DEPOSIT AMT.', 'DEPOSIT']
        
        # Axis/IDFC/Yes format
        debit_cols = ['DEBIT AMOUNT(INR)', 'DEBIT AMOUNT', 'DEBIT']
        credit_cols = ['CREDIT AMOUNT(INR)', 'CREDIT AMOUNT', 'CREDIT']

        # --- LOGIC: CHECK PAYMENTS FIRST ---
        for col in (withdrawal_cols + debit_cols):
            if col in df.columns:
                val = clean_amount(row[col])
                if val > 0:
                    nature = "Payment"
                    amount = val

        # --- LOGIC: CHECK RECEIPTS SECOND ---
        for col in (deposit_cols + credit_cols):
            if col in df.columns:
                val = clean_amount(row[col])
                if val > 0:
                    nature = "Receipt"
                    amount = val

        # --- EXTRACT DATE & DESCRIPTION ---
        date = next((row[c] for c in df.columns if 'DATE' in c), "N/A")
        # Finds columns like Particulars, Narration, or Description
        desc = next((row[c] for c in df.columns if any(k in c for k in ['PARTICULARS', 'DESCRIPTION', 'NARRATION'])), "N/A")

        if amount > 0:
            final_results.append({
                'Date': str(date).replace('\n', ' '),
                'Particulars': str(desc).replace('\n', ' '),
                'Nature': nature,
                'Amount': amount
            })

    return pd.DataFrame(final_results)

if uploaded_file:
    with st.spinner('AI Engine is reading the table structure...'):
        try:
            df_final = process_statement(uploaded_file)
            
            if df_final is not None and not df_final.empty:
                st.success(f"Successfully processed {len(df_final)} transactions!")
                
                # Visual Dashboard
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Total Receipts", f"₹{df_final[df_final['Nature']=='Receipt']['Amount'].sum():,.2f}")
                with c2:
                    st.metric("Total Payments", f"₹{df_final[df_final['Nature']=='Payment']['Amount'].sum():,.2f}")

                st.dataframe(df_final, use_container_width=True)

                # Excel Export
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Bifurcated')
                
                st.download_button(
                    label="📥 Download Standardized Excel",
                    data=output.getvalue(),
                    file_name=f"Bifurcated_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("Could not find any transaction rows. Please ensure the PDF is a digital statement and not a scan.")
        except Exception as e:
            st.error(f"Error reading PDF: {e}")