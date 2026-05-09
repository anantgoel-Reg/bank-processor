import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

# UI Configuration
st.set_page_config(page_title="Company Bank Tool", layout="wide")

st.title("🏦 Internal Bank Statement Processor")
st.markdown("Upload a PDF to automatically bifurcate Receipts and Payments.")

uploaded_file = st.file_uploader("Upload Bank PDF", type="pdf")

if uploaded_file:
  with st.spinner('Processing...'):
      all_rows = []
      with pdfplumber.open(uploaded_file) as pdf:
          for page in pdf.pages:
              table = page.extract_table()
              if table: all_rows.extend(table)
      
      df = pd.DataFrame(all_rows)
      # Set first row as header and clean up
      df.columns = [str(c).replace('\n', ' ').strip().upper() for c in df.iloc[0]]
      df = df[1:].reset_index(drop=True)

      # Bifurcation Logic based on your Bank Samples
      def detect_nature(row):
          val = " ".join(map(str, row.values)).lower()
          if any(k in val for k in ['credit', 'deposit', '(cr)', 'initial funding']):
              return 'Receipt'
          return 'Payment'

      df['NATURE'] = df.apply(detect_nature, axis=1)

      # Show results to employee
      st.dataframe(df, use_container_width=True)

      # Download Button
      output = BytesIO()
      with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
          df.to_excel(writer, index=False)
      
      st.download_button("📥 Download Excel", output.getvalue(), 
                         file_name="Bifurcated_Statement.xlsx")