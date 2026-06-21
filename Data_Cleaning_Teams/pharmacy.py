"""
Pharmacy Team Data Cleaner

Handles Pharmacy team data standardization and KPI calculation.
All 5 KPIs preserve uncapped achievements.
Each KPI contribution is capped by its configured weight.
Final performance score is capped at 100%.
Performance score = min(sum(min(achievement_i, 100) * weight_i), 100)
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def parse_percentage(value: Any) -> float:
    """
    Parse percentage value from various formats.
    
    Handles: "95%", "0.95", 95, etc.
    Returns normalized value (0-100 scale)
    
    Args:
        value: Value to parse
        
    Returns:
        Float value on 0-100 scale
    """
    if pd.isna(value):
        return 0.0
    
    if isinstance(value, str):
        # Remove % and commas, then convert
        value = value.rstrip('%').replace(',', '').strip()
        try:
            numeric = float(value)
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse percentage value: {value}")
            return 0.0
    else:
        try:
            numeric = float(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse percentage value: {value}")
            return 0.0
    
    # If value is between 0-1, assume it's a decimal fraction, scale to 100
    if 0 <= numeric <= 1:
        numeric = numeric * 100.0
    
    return numeric


def calculate_achievement(actual: float, target: float, is_inverse: bool = False, cap_at_100: bool = False) -> float:
    """
    Calculate KPI achievement ratio.
    
    Args:
        actual: Actual performance value
        target: Target performance value
        is_inverse: If True, calculate as target/actual (lower is better)
        cap_at_100: If True, cap result at 100%
        
    Returns:
        Achievement ratio (0-100 scale or higher if uncapped)
    """
    actual = float(actual) if not pd.isna(actual) else 0.0
    target = float(target) if not pd.isna(target) else 0.0
    
    if is_inverse:
        # Lower is better: target/actual
        if actual == 0:
            # No division by zero - assume perfect performance
            achievement = 100.0
        else:
            achievement = (target / actual) * 100.0
    else:
        # Higher is better: actual/target
        if target == 0:
            # Cannot measure achievement if target is zero
            achievement = 0.0 if actual == 0 else 0.0
        else:
            achievement = (actual / target) * 100.0
    
    # Apply capping if needed
    if cap_at_100:
        achievement = min(achievement, 100.0)
    
    return achievement


def process_pharmacy(file_path: str, team_config: Dict[str, Any] = None) -> pd.DataFrame:
    """
    Process Pharmacy team Excel data.
    
    Performs:
    1. Data standardization (column names, data types)
    2. Percentage parsing
    3. KPI achievement calculations (all 5 KPIs)
    4. Performance score calculation (capped contribution model)
    5. Grade assignment
    
    Args:
        file_path: Path to Excel file
        team_config: Optional team configuration dict with KPI definitions
        
    Returns:
        DataFrame with calculated KPI values and performance score
    """
    from cleaned import clean_sheet_data
    from utils import add_computed_columns
    
    # Load and clean basic data
    sheet_name = "Pharmacy"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = clean_sheet_data(df, sheet_name=sheet_name)
    
    # Standardize column names: remove all whitespace
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)
    
    logger.info(f"Loaded Pharmacy data with {len(df)} rows and columns: {list(df.columns)}")
    
    # KPI Definitions and Weights (Pharmacy achievements are uncapped)
    kpis = {
        'WaitingTime': {
            'actual_col': 'A.TotalAvgWaitingTime',
            'target_col': 'T.TotalWaitingTime',
            'is_inverse': True,
            'weight': 0.20,
            'cap': False,
        },
        'Leakage': {
            'actual_col': 'A.Leakage%',
            'target_col': 'T.Leakage%',
            'is_inverse': True,
            'weight': 0.20,
            'cap': False,
        },
        'TenderCompliance': {
            'actual_col': 'A.TenderItemCompliance',
            'target_col': 'T.TenderItemCompliance',
            'is_inverse': False,
            'weight': 0.20,
            'cap': False,
        },
        'ATV': {
            'actual_col': 'A.ATV',
            'target_col': 'T.ATV',
            'is_inverse': False,
            'weight': 0.20,
            'cap': False,
        },
        'Prescription': {
            'actual_col': 'A.NoofPrescriptionsContribution',
            'target_col': 'T.NoofPrescriptionsContribution',
            'is_inverse': False,
            'weight': 0.20,
            'cap': False,
        },
    }
    
    # Grade thresholds
    thresholds = {
        'A': 95,
        'B': 85,
        'C': 75,
        'D': 65,
    }
    
    # Calculate achievements for each KPI
    achievement_cols = {}
    
    for kpi_key, kpi_def in kpis.items():
        actual_col = kpi_def['actual_col']
        target_col = kpi_def['target_col']
        
        # Find columns (case insensitive, attempt exact match then fallback)
        actual_found = None
        target_found = None
        
        for col in df.columns:
            if col.lower() == actual_col.lower():
                actual_found = col
            if col.lower() == target_col.lower():
                target_found = col
        
        if actual_found and target_found:
            # Parse actual and target values
            actuals = df[actual_found].apply(lambda x: parse_percentage(x) if 'Leakage' in actual_col or 'Compliance' in actual_col else float(x) if not pd.isna(x) else 0.0)
            targets = df[target_found].apply(lambda x: parse_percentage(x) if 'Leakage' in target_col or 'Compliance' in target_col else float(x) if not pd.isna(x) else 0.0)
            
            # Calculate achievements
            achievements = np.array([
                calculate_achievement(
                    actuals.iloc[i],
                    targets.iloc[i],
                    is_inverse=kpi_def['is_inverse'],
                    cap_at_100=kpi_def['cap']
                )
                for i in range(len(df))
            ])
        else:
            # Try to find a pre-calculated achievement column in the Excel sheet
            ach_col_found = None
            possible_keys = [f"{kpi_key}Ach%", f"{kpi_key}Ach", f"Noof{kpi_key}Ach%", f"{kpi_key}_Achievement", f"{kpi_key}RateAch%"]
            for possible_key in possible_keys:
                for col in df.columns:
                    if col.lower() == possible_key.lower():
                        ach_col_found = col
                        break
                if ach_col_found:
                    break
            
            if ach_col_found:
                # Read achievement directly from sheet
                ach_vals = df[ach_col_found].apply(lambda x: float(x) if not pd.isna(x) else 0.0)
                # If values are <= 2.0 (decimal scale), convert to 0-100 scale
                ach_vals = ach_vals.apply(lambda x: x if x > 2.0 else x * 100.0)
                achievements = ach_vals.to_numpy()
            else:
                logger.warning(f"Could not find columns for {kpi_key}: actual={actual_col}, target={target_col}")
                achievements = np.zeros(len(df))
            
        achievement_cols[kpi_key] = achievements
        df[f'{kpi_key}_Achievement'] = achievements
        logger.info(f"Calculated or resolved {kpi_key} achievement (inverse={kpi_def['is_inverse']})")
    
    # Calculate performance score: Σ(achievement_i × weight_i) - UNCAPPED
    performance_scores = np.zeros(len(df))
    
    for kpi_key, achievement in achievement_cols.items():
        weight = kpis[kpi_key]['weight']
        performance_scores += np.minimum(achievement, 100.0) * weight
    
    performance_scores = np.minimum(performance_scores, 100.0)
    df['Performance'] = performance_scores
    
    # Assign grades
    def assign_grade(score: float) -> str:
        if score >= thresholds['A']:
            return 'A'
        elif score >= thresholds['B']:
            return 'B'
        elif score >= thresholds['C']:
            return 'C'
        elif score >= thresholds['D']:
            return 'D'
        else:
            return 'E'
    
    df['Grade'] = df['Performance'].apply(assign_grade)
    
    # Map to standard system columns
    for col in ['PerformanceScore', 'Performance_Score']:
        if col in df.columns:
            df[col] = df['Performance']
    
    # Apply standard computed columns
    df = add_computed_columns(df)
    
    logger.info(f"Pharmacy processing complete. Performance scores range: {df['Performance'].min():.2f} - {df['Performance'].max():.2f}")
    
    return df


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    try:
        df_result = process_pharmacy(r"D:\Projects\Pharmacy_Data.xlsx")
        print("✅ Pharmacy KPIs calculated successfully!")
        
        preview_cols = [c for c in ['WaitingTime_Achievement', 'Leakage_Achievement', 'TenderCompliance_Achievement', 'ATV_Achievement', 'Prescription_Achievement', 'Performance', 'Grade'] if c in df_result.columns]
        print("\n--- Previewing Cleaned Pharmacy Results ---")
        print(df_result[preview_cols].head())
        
    except Exception as e:
        print(f"❌ Testing Failed! Error: {e}")
        import traceback
        traceback.print_exc()
