import pandas as pd
import numpy as np
import io
from utils.helpers import convert_aht_to_minutes, convert_percentage

class ExcelProcessor:
    @staticmethod
    def load_excel(file_source) -> pd.ExcelFile:
        """Load an Excel file from a file path or in-memory bytes."""
        if isinstance(file_source, bytes):
            return pd.ExcelFile(io.BytesIO(file_source))
        return pd.ExcelFile(file_source)

    @staticmethod
    def clean_sheet(df: pd.DataFrame, sheet_name: str, crop_col: str = "Performance Grade") -> pd.DataFrame:
        """Crop columns and convert data types for consistency."""
        df = df.copy()
        
        # Crop columns up to crop_col if present
        if crop_col in df.columns:
            col_index = df.columns.get_loc(crop_col)
            df = df.iloc[:, :col_index + 1]
            
        # Standardize column names by removing spaces
        df.columns = df.columns.str.replace(r'\s+', '', regex=True)

        for col in df.columns:
            if col == 'AHT' or col == 'A.AHT' or col == 'A.AHT.1':
                df['AHT_Minutes'] = df[col].apply(convert_aht_to_minutes)
            elif '%' in col:
                df[col] = df[col].apply(convert_percentage)
            elif col == 'Date':
                df[col] = pd.to_datetime(df[col], dayfirst=True, errors='coerce')

        # Status Helpers
        if 'Status' in df.columns:
            df['Is_Inactive'] = df['Status'].str.lower().str.contains('inactive', na=False)
            df['Is_New'] = df['Status'].str.lower().str.contains('new', na=False)
        else:
            df['Is_Inactive'] = False
            df['Is_New'] = False

        return df

    def process_sheet_inbound(self, excel_file: pd.ExcelFile) -> pd.DataFrame:
        df = pd.read_excel(excel_file, sheet_name="Inbound")
        df = self.clean_sheet(df, "Inbound", "Performance Grade")
        
        # Select booking and attend columns for volume trend
        start_booking_idx = df.columns.get_loc('Dubai_Booking') if 'Dubai_Booking' in df.columns else -1
        start_attend_idx = df.columns.get_loc('Dubai_Attend') if 'Dubai_Attend' in df.columns else -1
        
        if start_booking_idx >= 0:
            booking_cols = df.columns[start_booking_idx : start_booking_idx + 4]
            df['Total_Booking_Trend'] = df[booking_cols].sum(axis=1)
        else:
            df['Total_Booking_Trend'] = 0

        if start_attend_idx >= 0:
            attend_cols = df.columns[start_attend_idx : start_attend_idx + 4]
            df['Total_Attend_Trend'] = df[attend_cols].sum(axis=1)
        else:
            df['Total_Attend_Trend'] = 0

        return df

    def process_sheet_outbound(self, excel_file: pd.ExcelFile) -> pd.DataFrame:
        df = pd.read_excel(excel_file, sheet_name="Outbound")
        df = self.clean_sheet(df, "Outbound", "Performance Grade")

        start_booking_idx = df.columns.get_loc('Dubai_Booking') if 'Dubai_Booking' in df.columns else -1
        start_attend_idx = df.columns.get_loc('Dubai_Attend') if 'Dubai_Attend' in df.columns else -1
        
        if start_booking_idx >= 0:
            booking_cols = df.columns[start_booking_idx : start_booking_idx + 4]
            df['Total_Booking_Trend'] = df[booking_cols].sum(axis=1)
        else:
            df['Total_Booking_Trend'] = 0

        if start_attend_idx >= 0:
            attend_cols = df.columns[start_attend_idx : start_attend_idx + 4]
            df['Total_Attend_Trend'] = df[attend_cols].sum(axis=1)
        else:
            df['Total_Attend_Trend'] = 0

        return df

    def process_sheet_inbound_uae(self, excel_file: pd.ExcelFile) -> pd.DataFrame:
        df = pd.read_excel(excel_file, sheet_name="Inbound UAE")
        df = self.clean_sheet(df, "Inbound UAE", "Performance Grade")

        start_booking_idx = df.columns.get_loc('Dubai_Booking') if 'Dubai_Booking' in df.columns else -1
        start_attend_idx = df.columns.get_loc('Dubai_Attend') if 'Dubai_Attend' in df.columns else -1
        
        if start_booking_idx >= 0:
            booking_cols = df.columns[start_booking_idx : start_booking_idx + 4]
            df['Total_Booking_Trend'] = df[booking_cols].sum(axis=1)
        else:
            df['Total_Booking_Trend'] = 0

        if start_attend_idx >= 0:
            attend_cols = df.columns[start_attend_idx : start_attend_idx + 4]
            df['Total_Attend_Trend'] = df[attend_cols].sum(axis=1)
        else:
            df['Total_Attend_Trend'] = 0

        return df

    def process_sheet_preapprovals(self, excel_file: pd.ExcelFile) -> pd.DataFrame:
        df = pd.read_excel(excel_file, sheet_name="Pre-Approvals IP Offshore")
        df = self.clean_sheet(df, "Pre-Approvals IP Offshore", "Performance Grade")
        return df
