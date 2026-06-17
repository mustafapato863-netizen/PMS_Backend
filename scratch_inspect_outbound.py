import pandas as pd

file_path = r"D:\Trend\PMS_Trend_All.xlsx"
df = pd.read_excel(file_path, sheet_name="Outbound")
print("Outbound columns containing 'date':")
print([c for c in df.columns if "date" in str(c).lower()])
print("\nFirst 5 values of Date column:")
print(df["Date"].head())
print("\nTypes of Date column values:")
print(df["Date"].apply(type).unique())
