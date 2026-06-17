import pandas as pd
import numpy as np
from cleaned import clean_sheet_data
from utils import add_computed_columns


def process_pharmacy(file_path):
    # --- 1. Load and Clean Data ---
    sheet_name = "Pharmacy"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
    
    # Standardize column names by removing ALL hidden whitespaces
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)
    
    # --- 2. Helper to Parse Percentages Safely to 0-100 Scale ---
    def parse_percentage_col(col_name):
        # Fallback to search for closest matching column name if exact not found
        if col_name not in df.columns:
            matched = [c for c in df.columns if col_name.replace('%', '') in c]
            if matched:
                col_name = matched[0]
            else:
                return pd.Series(0.0, index=df.index)
        
        series = df[col_name].fillna(0)
        if series.dtype == object:
            series = series.astype(str).str.rstrip('%').str.replace(',', '')
            series = pd.to_numeric(series, errors='coerce').fillna(0)
        else:
            series = pd.to_numeric(series, errors='coerce').fillna(0)
            # If already fraction format (e.g. 0.94 instead of 94), scale up to 100
            if series.max() <= 2.0 and (series > 0).any():
                series = series * 100.0
        return series

    # --- 3. Dynamic Performance Calculation (Using Defined Weights and Dynamic Ratios) ---
    W_WAITTIME = 0.20    # 20%
    W_LEAKAGE = 0.20     # 20%
    W_T_COMP = 0.20      # 20%
    W_ATV = 0.20         # 20%
    W_PRESC = 0.20       # 20%
    
    # Dynamic achievement calculation: actuals / targets with optional inversion
    def calculate_kpi_ach(a_col, t_col, ach_col, invert=False):
        if a_col in df.columns and t_col in df.columns:
            a_series = pd.to_numeric(df[a_col], errors='coerce').fillna(0)
            t_series = pd.to_numeric(df[t_col], errors='coerce').fillna(0)
            
            if invert:
                # الحساب العكسي للمؤشرات السلبية: المستهدف / الفعلي (الأقل أفضل)
                ratio = np.where(a_series > 0, t_series / a_series, 0.0)
            else:
                # الحساب الطردي التقليدي: الفعلي / المستهدف (الأعلى أفضل)
                ratio = np.where(t_series > 0, a_series / t_series, 0.0)
                
            df[ach_col] = ratio * 100.0
            return ratio * 100.0
        else:
            return parse_percentage_col(ach_col)

    # احتساب كل مؤشر ديناميكياً من واقع الداتا الفعلية والمستهدفة بالشيت
    wait_time_ach = calculate_kpi_ach('A.TotalAvgWaitingTime', 'T.TotalWaitingTime', 'WaitingTimeAch%', invert=True)
    leakage_ach = calculate_kpi_ach('A.Leakage%', 'T.Leakage%', 'LeakageAch%', invert=True)
    t_comp_ach = calculate_kpi_ach('A.TenderItemCompliance', 'T.TenderItemCompliance', 'TenderComplianceAch%', invert=False)
    atv_ach = calculate_kpi_ach('A.ATV', 'T.ATV', 'ATVAch%', invert=False)
    
    # حساب مساهمة الروشتات (وفي حال غياب المستهدف الصريح، يسحب النسبة الجاهزة كـ Fallback تلقائي)
    presc_ach = calculate_kpi_ach('A.NoofPrescriptionsContribution', 'T.NoofPrescriptionsContribution', 'NoofPrescriptionAch%', invert=False)
    
    # Final Weighted Performance Formula (Score out of 100)
    df['Performance'] = (
        (wait_time_ach * W_WAITTIME) +
        (leakage_ach * W_LEAKAGE) +
        (t_comp_ach * W_T_COMP) +
        (atv_ach * W_ATV) +
        (presc_ach * W_PRESC)
    )
    
    # Map back to standard system columns for downstream processing
    for target_score_col in ['PerformanceScore', 'Performance_Score']:
        if target_score_col in df.columns:
            df[target_score_col] = df['Performance']
            
    # Apply grade/class generation mapping rules
    df = add_computed_columns(df)
    return df


# --- 4. Execution and Testing Block ---
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        df_result = process_pharmacy(r"D:\Trend\PMS_Trend_All.xlsx")
        print("✅ Pharmacy KPIs and Dynamic Ratios calculated successfully!")
        
        # الانتخاب الديناميكي للأعمدة المتاحة للعرض للتأكد من نجاح العملية
        available_cols = [c for c in ['WaitingTimeAch%', 'LeakageAch%', 'Performance', 'Class'] if c in df_result.columns]
        
        print("\n--- Previewing Cleaned Pharmacy Results ---")
        print(df_result[available_cols].head())
        
    except Exception as e:
        print(f"❌ Testing Failed! Error detail: {e}")