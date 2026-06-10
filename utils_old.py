import pandas as pd
import numpy as np

def convert_aht_to_minutes(aht_value):
    """Convert AHT from HH:MM:SS to minutes (float)"""
    if pd.isna(aht_value):
        return np.nan
    try:
        if isinstance(aht_value, str):
            parts = aht_value.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 60 + minutes + seconds / 60
            elif len(parts) == 2:
                minutes = int(parts[0])
                seconds = int(parts[1])
                return minutes + seconds / 60
        elif isinstance(aht_value, (int, float)):
            # If Excel time fraction
            if aht_value < 1:
                return aht_value * 24 * 60  # convert fraction of a day to minutes
            else:
                return aht_value / 60
    except:
        pass
    return np.nan

def convert_percentage(col_value):
    """Convert percentage (string with % or decimal) to float (0-1 range)"""
    if pd.isna(col_value):
        return np.nan
    try:
        if isinstance(col_value, str):
            col_value = col_value.replace('%', '').strip()
            val = float(col_value)
            if val > 1:
                return val / 100
            return val
        elif isinstance(col_value, (int, float)):
            if col_value > 1:
                return col_value / 100
            return col_value
    except:
        pass
    return np.nan

def add_computed_columns(df):
    """
    Add computed columns:
    - Performance Grade (based on score: >0.9 = "Exceeds", >0.8 = "Meet", >0.7 = "Average", else "Below")
    - Suggested Action (simple logic: score>0.9="Reward", score<0.7="PIP", else="Monitor")
    """
    if 'Performance' in df.columns:
        scores = df['Performance']
        
        # Calculate Performance Grade
        conditions_grade = [
            scores > 0.9,
            scores > 0.8,
            scores > 0.7
        ]
        choices_grade = ["Exceeds", "Meet", "Average"]
        df['PerformanceGrade'] = np.select(conditions_grade, choices_grade, default="Below")
        
        # Calculate Suggested Action
        conditions_action = [
            scores > 0.9,
            scores < 0.7
        ]
        choices_action = ["Reward", "PIP"]
        df['SuggestedAction'] = np.select(conditions_action, choices_action, default="Monitor")
        
    return df

