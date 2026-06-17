import pandas as pd
import datetime

file_path = r"D:\Trend\PMS_Trend_All.xlsm"
sheets = ["Inbound", "Outbound", "Inbound UAE", "Pre-Approvals IP Offshore"]

for sheet in sheets:
    print(f"\n--- Sheet: {sheet} ---")
    try:
        df = pd.read_excel(file_path, sheet_name=sheet)
        if "Date" in df.columns:
            print("Unique Date values:")
            print(df["Date"].unique())
            
            # Print parsed months
            months = []
            for val in df["Date"]:
                if isinstance(val, (pd.Timestamp, datetime.datetime)):
                    months.append(val.strftime('%B'))
                elif isinstance(val, str):
                    months.append(val)
                else:
                    months.append(str(val))
            print("Unique parsed month values:")
            print(set(months))
        else:
            print("Date column NOT found!")
            print("Columns:", list(df.columns))
    except Exception as e:
        print(f"Error reading sheet: {e}")
