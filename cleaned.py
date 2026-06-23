import pandas as pd
import numpy as np
from utils import convert_aht_to_minutes, convert_percentage

def clean_sheet_data(df, sheet_name, column_name="Performance Grade"):
    """
    Applies the global cleaning process to a sheet DataFrame:
    1. Crops columns up to the specified target column (default: "Performance Grade").
    2. Converts specific columns: AHT to AHT_Minutes, columns with '%' to percentages,
       Performance Score to numeric, and Date to datetime.
    3. Adds helper boolean columns for status (Is_Inactive, Is_New).
    """
    print(f"\n--- Processing sheet: {sheet_name} ---")
    
    # Standardize column headers to string to prevent TypeError with numeric/float headers
    df.columns = [str(col).strip() for col in df.columns]
    
    # STEP 1: Crop columns up to "Performance Grade"
    if column_name in df.columns:
        col_index = df.columns.get_loc(column_name)
        df = df.iloc[:, :col_index + 1]
        print(f"  ✓ Cropped to {df.shape[1]} columns")
    
    # STEP 2: Identify and convert data types
    print(f"  ✓ Converting data types...")
    for col in df.columns:
        # AHT column -> convert to minutes
        if col == 'AHT':
            df['AHT_Minutes'] = df[col].apply(convert_aht_to_minutes)
            print(f"    - {col} → AHT_Minutes (numeric)")
        
        # Any column with '%' in name -> convert to percentage
        elif '%' in col:
            df[col] = df[col].apply(convert_percentage)
            print(f"    - {col} → percentage (0-1 range)")
        
        # Performance Score -> numeric
        elif col == 'Performance Score':
            df[col] = pd.to_numeric(df[col], errors='coerce')
            print(f"    - {col} → numeric")
        
        # Date -> datetime
        elif col == 'Date':
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors='coerce')
            print(f"    - {col} → datetime")
            
    # STEP 3: Add helper columns
    # Detect Inactive staff
    if 'Status' in df.columns:
        df['Is_Inactive'] = df['Status'].str.lower().str.contains('inactive', na=False)
    
    # Detect New staff
    df['Is_New'] = df['Status'].str.lower().str.contains('new', na=False) if 'Status' in df.columns else False
    
    return df
