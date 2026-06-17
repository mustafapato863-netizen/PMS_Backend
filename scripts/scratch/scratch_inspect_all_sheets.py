import pandas as pd

file_path = r"D:\Trend\PMS_Trend_All.xlsx"
xl = pd.ExcelFile(file_path)

for sheet in xl.sheet_names:
    print(f"\n--- Sheet: {sheet} ---")
    try:
        df = pd.read_excel(file_path, sheet_name=sheet)
        date_cols = [c for c in df.columns if "date" in c.lower()]
        print(f"Date-like columns: {date_cols}")
        for col in date_cols:
            print(f"Unique values in {col}:")
            print(df[col].unique()[:10])
    except Exception as e:
        print(f"Error: {e}")
