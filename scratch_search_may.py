import pandas as pd

file_path = r"D:\PMS_Trend_All.xlsm"
xl = pd.ExcelFile(file_path)

for sheet in xl.sheet_names:
    print(f"\n--- Sheet: {sheet} ---")
    try:
        df = pd.read_excel(file_path, sheet_name=sheet)
        for col in df.columns:
            mask = df[col].astype(str).str.lower().str.contains('may')
            if mask.any():
                print(f"  Col '{col}' contains 'may':")
                print(df[mask][col].head())
            
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                mask_dt = df[col].dt.month == 5
                if mask_dt.any():
                    print(f"  Col '{col}' contains May dates:")
                    print(df[mask_dt][col].head())
    except Exception as e:
        print(f"Error: {e}")
