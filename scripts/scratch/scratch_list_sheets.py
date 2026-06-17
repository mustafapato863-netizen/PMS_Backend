import pandas as pd

file_path = r"D:\Trend\PMS_Trend_All.xlsx"
xl = pd.ExcelFile(file_path)
print("Sheet names in PMS_Trend_All.xlsx:", xl.sheet_names)
