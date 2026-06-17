import pandas as pd
import os

files = [
    r"D:\PMS\May\Callcenter\CC PMS.xlsx",
    r"D:\PMS\May\Pre-Approval\Offshore_PMS_PreApproval.xlsx",
    r"D:\PMS\May\UAE\May Performance Report.xlsx"
]

for file_path in files:
    print(f"\n=========================================")
    print(f"File: {file_path}")
    print(f"Exists: {os.path.exists(file_path)}")
    if not os.path.exists(file_path):
        continue
    try:
        xl = pd.ExcelFile(file_path)
        print("Sheets:", xl.sheet_names)
        for sheet in xl.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet)
            date_cols = [c for c in df.columns if "date" in str(c).lower()]
            if date_cols:
                print(f"  Sheet '{sheet}': Date-like columns: {date_cols}")
                for col in date_cols:
                    print(f"    Unique dates in '{col}': {df[col].unique()[:5]}")
            else:
                # print first 5 columns if no date column
                print(f"  Sheet '{sheet}': No Date-like column. First 5 columns: {list(df.columns[:5])}")
    except Exception as e:
        print(f"Error: {e}")
