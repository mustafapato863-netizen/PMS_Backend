import pandas as pd

file_path = r"D:\Trend\PMS_Trend_All.xlsx"
xl = pd.ExcelFile(file_path)

for sheet in xl.sheet_names:
    print(f"\n--- Sheet: {sheet} ---")
    try:
        df = pd.read_excel(file_path, sheet_name=sheet)
        print("Columns:")
        for col in df.columns:
            print(f"  Col: {repr(col)} | Type: {type(col)}")
    except Exception as e:
        print(f"Error: {e}")
