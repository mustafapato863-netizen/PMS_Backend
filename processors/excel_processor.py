import pandas as pd
import numpy as np
import io
import logging
from typing import Dict, Any, List, Optional, Tuple
from utils.helpers import convert_aht_to_minutes, convert_percentage
from Data_Cleaning_Teams.inbound import process_inbound
from Data_Cleaning_Teams.outbound import process_outbound
from Data_Cleaning_Teams.inbound_UAE import process_inbound_uae
from Data_Cleaning_Teams.preapprovals_offshore import process_preapprovals_offshore
from Data_Cleaning_Teams.sales import process_sales
from config.loader import load_team_config, ConfigurationError

logger = logging.getLogger(__name__)

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

    def process_sheet_inbound(self, excel_file) -> pd.DataFrame:
        return process_inbound(excel_file)

    def process_sheet_outbound(self, excel_file) -> pd.DataFrame:
        return process_outbound(excel_file)

    def process_sheet_inbound_uae(self, excel_file) -> pd.DataFrame:
        return process_inbound_uae(excel_file)

    def process_sheet_preapprovals(self, excel_file) -> pd.DataFrame:
        return process_preapprovals_offshore(excel_file)

    def process_sheet_sales(self, excel_file) -> pd.DataFrame:
        return process_sales(excel_file)

    def process_sheet_coding(self, excel_file) -> pd.DataFrame:
        from Data_Cleaning_Teams.coding import process_coding
        return process_coding(excel_file)

    def process_sheet_csr(self, excel_file) -> pd.DataFrame:
        from Data_Cleaning_Teams.csr import process_csr
        return process_csr(excel_file)

    def process_sheet_pharmacy(self, excel_file) -> pd.DataFrame:
        from Data_Cleaning_Teams.pharmacy import process_pharmacy
        return process_pharmacy(excel_file)

    def process_sheet_submission(self, excel_file) -> pd.DataFrame:
        from Data_Cleaning_Teams.submission import process_submission
        return process_submission(excel_file)

