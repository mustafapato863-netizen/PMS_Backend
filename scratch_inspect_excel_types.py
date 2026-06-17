import pandas as pd

file_path = r"D:\Trend\PMS_Trend_All.xlsx"
sheets = ["Inbound", "Outbound", "Inbound UAE", "Pre-Approvals IP Offshore"]

for sheet in sheets:
    print(f"\n--- Sheet: {sheet} ---")
    try:
        df = pd.read_excel(file_path, sheet_name=sheet)
        if "Date" in df.columns:
            print("Unique values in Date:")
            for val in df["Date"].unique():
                print(f"  Value: {val} | Type: {type(val)}")
        else:
            print("Date column NOT found!")
    except Exception as e:
        print(f"Error: {e}")
