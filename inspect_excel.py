import pandas as pd

file_path = r"D:\Trend\PMS_Trend_All.xlsx"
df = pd.read_excel(file_path, sheet_name="CSR")
df.columns = df.columns.str.replace(r'\s+', '', regex=True)

# Find rows where A.CPTConversion% is > 0
non_zero = df[df['A.CPTConversion%'] > 0]
cols = ['AgentName', 'A.CPTConversion%', 'T.AttendedC.R', 'AttendedC.R%', 'PerformanceScore']
print(f"Found {len(non_zero)} rows with non-zero A.CPTConversion%")
print(non_zero[cols].head(10).to_string())
