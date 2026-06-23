import os
import pandas as pd
import datetime
import uuid
from typing import Optional

from config.settings import DEFAULT_FILE_PATH
from models.schemas import (
    Employee, PerformanceRecord, CallsData, GeoBreakdown, GeoData,
    ActualMetrics, AchievementMetrics, EvaluationData, UploadRecord
)
from repositories.json_repos import (
    JSONEmployeeRepository, JSONPerformanceRepository, JSONKPIWeightsRepository,
    JSONTargetsRepository, JSONManagerNotesRepository, JSONCorrectiveActionsRepository, JSONUploadsRepository
)
from processors.excel_processor import ExcelProcessor
from services.kpi_service import KPIService
from services.analysis_service import AnalysisService
from services.learning_service import LearningService
from services.planning_service import PlanningService
from services.trend_service import TrendService
from config.loader import load_team_config, ConfigurationError

def safe_int(val) -> int:
    if pd.isna(val):
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0

def safe_float(val) -> float:
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def safe_value(val):
    import math
    import numpy as np
    if pd.isna(val):
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    return str(val)

class DatabaseSeeder:
    def __init__(self):
        self.employee_repo = JSONEmployeeRepository()
        self.performance_repo = JSONPerformanceRepository()
        self.weights_repo = JSONKPIWeightsRepository()
        self.targets_repo = JSONTargetsRepository()
        self.notes_repo = JSONManagerNotesRepository()
        self.actions_repo = JSONCorrectiveActionsRepository()
        self.uploads_repo = JSONUploadsRepository()
        self.excel_processor = ExcelProcessor()
        
        self.kpi_service = KPIService(self.weights_repo, self.targets_repo)
        self.analysis_service = AnalysisService(self.targets_repo)
        self.planning_service = PlanningService(self.performance_repo)
        self.trend_service = TrendService()

    @staticmethod
    def _should_exclude_raw_row(row: pd.Series) -> bool:
        excluded_grades = {"-", "new staff", "leave"}
        for column_name, value in row.items():
            normalized_name = str(column_name).strip().lower().replace(" ", "")
            if normalized_name != "performancegrade":
                continue
            normalized_value = "" if pd.isna(value) else str(value).strip().lower()
            return normalized_value in excluded_grades
        return False

    def seed_database(self):
        """Initializes the database from the default Excel file if performance repository is empty."""
        if not os.path.exists(DEFAULT_FILE_PATH):
            print(f"⚠️ Default Excel file not found at {DEFAULT_FILE_PATH}. Skipping seeding.")
            return

        if len(self.performance_repo.get_all()) > 0:
            print("✓ Performance database is already populated. Skipping seeding.")
            return

        print("🌱 Seeding database from default Excel file...")
        try:
            excel_file = self.excel_processor.load_excel(DEFAULT_FILE_PATH)
            self._process_and_save_excel(excel_file)
            print("🌱 Seeding completed successfully!")
        except Exception as e:
            print(f"❌ Seeding database failed: {str(e)}")

    def process_uploaded_file(self, filename: str, contents: bytes):
        """Processes an uploaded PMS excel file and returns the import counts."""
        excel_file = self.excel_processor.load_excel(contents)
        
        # Save upload audit record
        upload_rec = UploadRecord(
            id=str(uuid.uuid4()),
            filename=filename,
            uploaded_at=datetime.datetime.now().isoformat(),
            uploaded_by="Admin"
        )
        self.uploads_repo.save(upload_rec)
        
        return self._process_and_save_excel(excel_file, upload_id=upload_rec.id)

    def _process_and_save_excel(self, excel_file, upload_id: Optional[str] = None):
        sheet_names = set(excel_file.sheet_names)
        inbound_df = self.excel_processor.process_sheet_inbound(excel_file) if "Inbound" in sheet_names else pd.DataFrame()
        outbound_df = self.excel_processor.process_sheet_outbound(excel_file) if "Outbound" in sheet_names else pd.DataFrame()
        inbound_uae_df = self.excel_processor.process_sheet_inbound_uae(excel_file) if "Inbound UAE" in sheet_names else pd.DataFrame()
        preapprovals_df = self.excel_processor.process_sheet_preapprovals(excel_file) if "Pre-Approvals IP Offshore" in sheet_names else pd.DataFrame()
        sales_df = self.excel_processor.process_sheet_sales(excel_file) if "Sales" in sheet_names else pd.DataFrame()
        coding_df = self.excel_processor.process_sheet_coding(excel_file) if "Coding" in sheet_names else pd.DataFrame()
        csr_df = self.excel_processor.process_sheet_csr(excel_file) if "CSR" in sheet_names else pd.DataFrame()
        pharmacy_df = self.excel_processor.process_sheet_pharmacy(excel_file) if "Pharmacy" in sheet_names else pd.DataFrame()
        submission_df = self.excel_processor.process_sheet_submission(excel_file) if "Submission" in sheet_names else pd.DataFrame()

        all_new_records = []
        all_new_employees = []

        sheet_mappings = []
        if not inbound_df.empty:
            sheet_mappings.append(("Inbound", inbound_df, "EmployeeID", "EnglishName"))
        if not outbound_df.empty:
            sheet_mappings.append(("Outbound", outbound_df, "SGHCode", "EnglishName"))
        if not inbound_uae_df.empty:
            sheet_mappings.append(("Inbound UAE", inbound_uae_df, "HRID", "AgentName"))
        if not preapprovals_df.empty:
            sheet_mappings.append(("Pre-Approvals IP Offshore", preapprovals_df, "HRID", "AgentName"))
        if not sales_df.empty:
            sheet_mappings.append(("Sales", sales_df, "HRID", "AgentName"))
        if not coding_df.empty:
            sheet_mappings.append(("Coding", coding_df, "HRID", "AgentName"))
        if not csr_df.empty:
            sheet_mappings.append(("CSR", csr_df, "HRID", "AgentName"))
        if not pharmacy_df.empty:
            sheet_mappings.append(("Pharmacy", pharmacy_df, "HRID", "AgentName"))
        if not submission_df.empty:
            try:
                submission_config = load_team_config("Submission")
                sheet_mappings.append((
                    "Submission",
                    submission_df,
                    submission_config.get("employee_id_col", "EmployeeID"),
                    submission_config.get("employee_name_col", "EmployeeName"),
                ))
            except ConfigurationError:
                sheet_mappings.append(("Submission", submission_df, "EmployeeID", "EmployeeName"))

        for team_name, df, id_col, name_col in sheet_mappings:
            for _, row in df.iterrows():
                if self._should_exclude_raw_row(row):
                    continue

                name = str(row.get(name_col, "")).strip()
                emp_id = str(row.get(id_col, "")).strip()
                
                if emp_id.endswith(".0"):
                    emp_id = emp_id[:-2]
                
                if not name or name.lower() == "total" or not emp_id or emp_id.lower() == "nan":
                    continue

                date_val = row.get("Date")
                month = "Unknown"
                if isinstance(date_val, (pd.Timestamp, datetime.datetime)):
                    month = date_val.strftime('%B')
                
                status = str(row.get("Status", "Active"))
                is_new = row.get("Is_New", False)
                region_val = str(row.get("Region", "EGY")).strip().upper()
                if not region_val or region_val == "NAN":
                    region_val = "UAE" if team_name in ["Inbound UAE", "Sales", "Coding", "CSR", "Pharmacy", "Submission"] else "EGY"

                employee = Employee(
                    id=emp_id,
                    name=name,
                    team=team_name,
                    status=status,
                    region=region_val
                )
                all_new_employees.append(employee)

                aht_val = row.get("AHT") or row.get("A.AHT") or row.get("A.AHT.1") or "00:00:00"
                if isinstance(aht_val, datetime.time):
                    aht_raw = aht_val.strftime("%H:%M:%S")
                elif isinstance(aht_val, str):
                    aht_raw = aht_val
                elif isinstance(aht_val, (int, float)):
                    from utils.helpers import convert_aht_to_minutes, format_minutes_to_hhmmss
                    aht_raw = format_minutes_to_hhmmss(convert_aht_to_minutes(aht_val))
                else:
                    aht_raw = "00:00:00"

                calls = CallsData(
                    inbound=safe_int(row.get("InboundCalls", 0)) if "InboundCalls" in df.columns else safe_int(row.get("InboundCalls ", 0)) if "InboundCalls " in df.columns else 0,
                    outbound=safe_int(row.get("OutboundCalls", 0)) if "OutboundCalls" in df.columns else 0,
                    total_handled=safe_int(row.get("TotalHandledCalls", 0)) if "TotalHandledCalls" in df.columns else (safe_int(row.get("Reached", 0)) if team_name == "Outbound" else 0),
                    abandoned=safe_int(row.get("AbandonedCalls", 0)) if "AbandonedCalls" in df.columns else 0,
                    aht_raw=aht_raw
                )

                geo_bookings = GeoBreakdown(
                    dubai=safe_int(row.get("Dubai_Booking") or row.get("Dubai_Booking") or 0),
                    sharjah=safe_int(row.get("Sharjah_Booking") or 0),
                    ajman=safe_int(row.get("Ajman_Booking") or 0),
                    clinics=safe_int(row.get("Clinics_Booking") or row.get("clinics_Booking") or row.get("Clinics_Booking") or 0),
                )
                geo_attended = GeoBreakdown(
                    dubai=safe_int(row.get("Dubai_Attend") or 0),
                    sharjah=safe_int(row.get("Sharjah_Attend") or 0),
                    ajman=safe_int(row.get("Ajman_Attend") or 0),
                    clinics=safe_int(row.get("Clinics_Attend") or row.get("clinics_Attend") or row.get("clinics.Attend") or row.get("Clinics.Attend") or 0),
                )
                geo = GeoData(bookings=geo_bookings, attended=geo_attended)

                actual = ActualMetrics(
                    booking_rate=safe_float(row.get("A.Booking%", 0.0)),
                    attend_rate=safe_float(row.get("A.Attend%", 0.0)),
                    abandon_rate=safe_float(row.get("A.AbandonRate%", 0.0)),
                    reachability_rate=safe_float(row.get("A.Reachability%", 0.0)),
                    rejection_rate=safe_float(row.get("A.InitialRejectionRate") or row.get("IPInitialRejection%") or row.get("A.CSRRejection%") or 0.0),
                    initial_error_rate=safe_float(row.get("Error%", 0.0)),
                    submission_rate=safe_float(row.get("A.TAT48Hours") or row.get("NumberApprovalwithin48hrs") or 0.0),
                    quality_rate=safe_float(row.get("A.QualityScore", 0.0)),
                    utz_rate=safe_float(row.get("A.UTZ%", 0.0))
                )

                row_dict = row.to_dict()
                score, grade, achievements, weights_used = self.kpi_service.calculate_performance(team_name, row_dict)

                ach = AchievementMetrics(
                    booking_ach=achievements.get("Booking", 0.0),
                    attend_ach=achievements.get("Attend", 0.0),
                    quality_ach=achievements.get("Quality", 0.0),
                    aht_ach=achievements.get("AHT", 0.0),
                    reachability_ach=achievements.get("Other", 0.0) if team_name == "Outbound" else 0.0,
                    abandon_ach=achievements.get("Other", 0.0) if team_name in ["Inbound", "Inbound UAE"] else 0.0,
                    rejection_ach=achievements.get("Rejection") or achievements.get("initial_rejection_rate") or 0.0,
                    initial_error_ach=achievements.get("InitialError", 0.0),
                    submission_ach=achievements.get("Submission") or achievements.get("submission_within_due_date") or 0.0,
                    op_census_ach=achievements.get("OPCensus", 0.0),
                    op_revenue_ach=achievements.get("OPRevenue", 0.0),
                    ip_census_ach=achievements.get("IPCensus", 0.0),
                    ip_revenue_ach=achievements.get("IPRevenue", 0.0),
                    activity_ach=achievements.get("Activity", 0.0)
                )

                root_cause = self.analysis_service.run_root_cause_analysis(team_name, achievements, weights_used, row_dict)
                suggested_action = self.analysis_service.generate_suggested_action(score, is_new, root_cause)

                note_rec = self.notes_repo.get_note(emp_id, month)
                action_rec = self.actions_repo.get_latest_by_employee_and_month(emp_id, month)

                evaluation = EvaluationData(
                    score=score,
                    grade=grade,
                    root_cause=root_cause,
                    suggested_action=suggested_action,
                    corrective_action=action_rec.manager_action if action_rec else None,
                    manager_notes=note_rec.notes if note_rec else None
                )

                record = PerformanceRecord(
                    id=f"{emp_id}_{month}",
                    employee_id=emp_id,
                    employee_name=name,
                    team=team_name,
                    month=month,
                    region=region_val,
                    calls=calls,
                    geo=geo,
                    actual=actual,
                    achievement=ach,
                    evaluation=evaluation,
                    upload_id=upload_id,
                    raw_data={str(k): safe_value(v) for k, v in row_dict.items()}
                )
                all_new_records.append(record)

        self.employee_repo.save_all(all_new_employees)
        self.performance_repo.save_all(all_new_records)

        # Read all history once (not inside the loop) to avoid O(n²) file reads
        all_history = self.performance_repo.get_all()
        updated_records = []
        from services.planning_service import MONTH_ORDER
        for r in all_new_records:
            emp_history = [h for h in all_history if h.employee_id == r.employee_id]
            emp_history.sort(key=lambda x: MONTH_ORDER.get(x.month, 0))
            
            curr_idx = -1
            for i, h in enumerate(emp_history):
                if h.month == r.month:
                    curr_idx = i
                    break

            if curr_idx >= 0:
                trend_status = self.trend_service.calculate_trends(emp_history, curr_idx)
                r.evaluation.trend_status = trend_status

            planning_lists = self.planning_service.classify_all(r.month)
            r.evaluation.planning_category = []
            for cat, recs in planning_lists.items():
                if any(x.id == r.id for x in recs):
                    r.evaluation.planning_category.append(cat)

            updated_records.append(r)

        self.performance_repo.save_all(updated_records)
        return {
            "records_imported": len(all_new_records),
            "employees_imported": len(all_new_employees)
        }
