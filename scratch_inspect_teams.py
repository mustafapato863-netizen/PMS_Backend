import pandas as pd

file_path = r"D:\Trend\PMS_Trend_All.xlsx"
xl = pd.ExcelFile(file_path)

for sheet in xl.sheet_names:
    if sheet in ["Inbound", "Outbound", "Inbound UAE", "Pre-Approvals IP Offshore", "Sales"]:
        print(f"\n--- Sheet: {sheet} ---")
        try:
            df = pd.read_excel(file_path, sheet_name=sheet)
            col = "Out Team" if "Out Team" in df.columns else "Team"
            if col in df.columns:
                print(f"Unique values in '{col}':", df[col].dropna().unique())
            else:
                print(f"Column '{col}' not found!")
        except Exception as e:
            print(f"Error: {e}")
