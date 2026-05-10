import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="HDFC Simple", layout="wide")
st.title("🏦 HDFC Bank Statement - Simple Logic")

uploaded_file = st.file_uploader("Upload HDFC PDF", type="pdf")

def clean_amt(val):
    if not val: return 0.0
    # Strip everything except numbers and decimals
    clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
    try: return float(clean)
    except: return 0.0

def process_hdfc(file):
    all_transactions = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue
            
            # Find the header row
            headers = []
            for row in table:
                row_str = " ".join(str(c) for c in row if c).upper()
                if "WITHDRAWAL" in row_str and "DEPOSIT" in row_str:
                    headers = [str(c).replace('\n', ' ').strip().upper() for c in row]
                    break
                    
            if not headers: continue
            
            # Get precise column numbers
            try:
                d_idx = next(i for i, h in enumerate(headers) if 'DATE' in h)
                n_idx = next(i for i, h in enumerate(headers) if 'NARRATION' in h)
                w_idx = next(i for i, h in enumerate(headers) if 'WITHDRAWAL' in h)
                c_idx = next(i for i, h in enumerate(headers) if 'DEPOSIT' in h)
            except:
                continue

            for row in table:
                # Protect against short rows or headers
                if len(row) <= max(w_idx, c_idx) or row[d_idx] == "Date": 
                    continue
                
                raw_date = str(row[d_idx]) if row[d_idx] else ""
                raw_narration = str(row[n_idx]) if row[n_idx] else ""
                raw_withdrawal = str(row[w_idx]) if row[w_idx] else ""
                raw_deposit = str(row[c_idx]) if row[c_idx] else ""
                
                # THE FIX: Un-squash any merged rows (splits by invisible newlines)
                dates = [d.strip() for d in raw_date.split('\n') if d.strip()]
                narrations = [n.strip() for n in raw_narration.split('\n') if n.strip()]
                withdrawals = [w.strip() for w in raw_withdrawal.split('\n') if w.strip()]
                deposits = [d.strip() for d in raw_deposit.split('\n') if d.strip()]
                
                # Find how many actual transactions were squashed into this row
                max_items = max(len(dates), len(withdrawals), len(deposits))
                
                for i in range(max_items):
                    # Safely grab the corresponding data
                    d_val = dates[i] if i < len(dates) else (dates[0] if dates else "")
                    n_val = narrations[i] if i < len(narrations) else " ".join(narrations)
                    
                    w_val = clean_amt(withdrawals[i] if i < len(withdrawals) else "")
                    c_val = clean_amt(deposits[i] if i < len(deposits) else "")
                    
                    # ==========================================
                    # YOUR EXACT LOGIC
                    # ==========================================
                    amount = 0.0
                    nature = ""
                    
                    if w_val > 0:
                        nature = "Payment"
                        amount = w_val
                    elif c_val > 0:
                        nature = "Receipt"
                        amount = c_val
                    # ==========================================
                        
                    # Save it if it has an amount and a valid date
                    if amount > 0 and re.search(r'\d', d_val):
                        all_transactions.append({
                            "Date": d_val,
                            "Description": n_val,
                            "Nature": nature,
                            "Amount": amount
                        })

    return pd.DataFrame(all_transactions)

if uploaded_file:
    try:
        df = process_hdfc(uploaded_file)
        if not df.empty:
            total_pay = df[df['Nature'] == 'Payment']['Amount'].sum()
            total_rec = df[df['Nature'] == 'Receipt']['Amount'].sum()
            
            st.success("✅ Processed Successfully using Simplified Logic")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Transactions", len(df))
            c2.metric("Total Receipts", f"₹{total_rec:,.2f}")
            c3.metric("Total Payments", f"₹{total_pay:,.2f}")
            
            st.dataframe(df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", out.getvalue(), "HDFC_Simple_Processed.xlsx")
        else:
            st.warning("No transactions found.")
    except Exception as e:
        st.error(f"Error: {e}")