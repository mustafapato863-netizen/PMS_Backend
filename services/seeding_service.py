import os
import io
import pandas as pd
import datetime
import uuid
import logging
from typing import Optional
from decimal import Decimal

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
from config.loader import (
    load_team_config,
    resolve_team_config,
    iter_employee_kpi_configs,
    ConfigurationError,
)
from config.database import SessionLocal
from models.models import (
    Team,
    TeamKPIConfig,
    Employee as DBEmployee,
    PerformanceRecord as DBPerformanceRecord,
    KPIValue,
    UploadLog,
)
from data_cleaning.standard_mappings import calculate_achievement
from utils.performance_levels import normalize_performance_level
from services.marketing_import_service import MarketingImportResult, MarketingImportService

logger = logging.getLogger(__name__)

class UploadProcessingError(RuntimeError):
    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report

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

def safe_decimal(val, default: str = "0"):
    if val is None:
        return Decimal(default)
    if isinstance(val, Decimal):
        return val
    if pd.isna(val):
        return Decimal(default)
    text = str(val).strip()
    if not text or text.lower() == "nan":
        return Decimal(default)
    try:
        return Decimal(text)
    except Exception:
        cleaned = text.replace(",", "").replace("%", "")
        if not cleaned:
            return Decimal(default)
        try:
            return Decimal(cleaned)
        except Exception:
            return Decimal(default)

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
        
        self.kpi_service = KPIService(self.weights_repo, self.targets_repo, initialize_defaults=False)
        self.analysis_service = AnalysisService(self.targets_repo)
        self.planning_service = PlanningService(self.performance_repo)
        self.trend_service = TrendService()
        self.marketing_import_service = MarketingImportService()

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

    def seed_demo_performance_levels(self):
        """Opt-in demo data that deliberately uses the real Excel import path."""
        if any(str(employee.id).startswith("DEMO-") for employee in self.employee_repo.get_all()):
            return {"skipped": True, "reason": "Demo performance-level data already exists"}

        sheets = {}
        for team_name, id_col, name_col, region, code in (
            ("Inbound", "EmployeeID", "EnglishName", "EGY", "EGY"),
            ("Sales", "HRID", "AgentName", "UAE", "UAE"),
        ):
            rows = []
            team_config = load_team_config(team_name)
            for level, prefix in (("Managerial", "MGR"), ("Corporate", "CORP")):
                config = resolve_team_config(team_config, level)
                for month_number in range(1, 4):
                    for employee_number in range(1, 5):
                        row = {
                            id_col: f"DEMO-{prefix}-{code}-{employee_number:03d}",
                            name_col: f"Demo {level} {code} {employee_number}",
                            "Date": datetime.datetime(2026, month_number, 1),
                            "Status": "Active",
                            "Region": region,
                            "Role": level,
                        }
                        for kpi_number, kpi in enumerate(config["kpis"]):
                            target = 0.90
                            variance = ((employee_number + month_number + kpi_number) % 5 - 2) * 0.035
                            row[kpi["actual_col"]] = max(0.65, min(1.0, target + variance))
                            row[kpi["target_col"]] = target
                        row["Performance Grade"] = ""
                        rows.append(row)
            sheets[team_name] = pd.DataFrame(rows)

        workbook = io.BytesIO()
        with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
            for sheet_name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=sheet_name, index=False)
        return self.process_uploaded_file("PMS_DEMO_PERFORMANCE_LEVELS.xlsx", workbook.getvalue())

    def process_uploaded_file(self, filename: str, contents: bytes, dry_run: bool = False):
        """Processes an uploaded PMS excel file and returns the import counts."""
        excel_file = self.excel_processor.load_excel(contents)
        marketing_result = self.marketing_import_service.parse_excel(excel_file)

        if dry_run:
            result = self._process_and_save_excel(
                excel_file,
                marketing_result=marketing_result,
                dry_run=True,
            )
            result["dry_run"] = True
            return result

        # Vercel Production Safety: Do not write to JSON repositories for runtime persistence.
        # Generate upload ID for the batch. Metadata persistence is delegated to the DB.
        upload_id = str(uuid.uuid4())
        
        db = SessionLocal()
        try:
            if marketing_result:
                for record in marketing_result.records:
                    record.upload_id = upload_id
            result = self._process_and_save_excel(
                excel_file,
                upload_id=upload_id,
                marketing_result=marketing_result,
                db_session=db,
            )
            db.commit()
            result["dry_run"] = False
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _normalize_sheet_levels(df: pd.DataFrame, id_col: str, team_name: str) -> list[str]:
        if "Role" not in df.columns:
            logger.warning("Legacy %s upload has no Role column; defaulting rows to Employee", team_name)
            df["performance_level"] = "Employee"
            return ["Employee"] * len(df)

        levels = []
        for position, (_, row) in enumerate(df.iterrows(), start=2):
            raw_role = row.get("Role")
            employee_id = str(row.get(id_col, "")).strip() or "unknown"
            try:
                levels.append(normalize_performance_level(raw_role))
            except ValueError as exc:
                raise UploadProcessingError(
                    f"Row {position}, employee {employee_id}: invalid Role {raw_role!r}. "
                    "Accepted values: Emp, Employee, Manager, Managerial, Corp, Corporate",
                    {"team": team_name, "row": position, "employee_id": employee_id, "invalid_role": raw_role},
                ) from exc
        df["performance_level"] = levels
        return levels

    @staticmethod
    def _status_for_record(record: PerformanceRecord) -> str:
        if record.status:
            return record.status
        if record.evaluation.grade == "A":
            return "Exceeds"
        if record.evaluation.grade in {"B", "C"}:
            return "Meets"
        return "Below"

    @staticmethod
    def _sync_marketing_config(db, team: Team) -> None:
        config = load_team_config("Marketing")
        positions = config["performance_levels"]["Employee"]["positions"]
        expected_keys: set[tuple[str, str]] = set()
        for position_name, position_config in positions.items():
            for kpi in position_config["kpis"]:
                expected_keys.add((position_name, kpi["key"]))
                existing = (
                    db.query(TeamKPIConfig)
                    .filter(
                        TeamKPIConfig.team_id == team.id,
                        TeamKPIConfig.performance_level == "Employee",
                        TeamKPIConfig.position_name == position_name,
                        TeamKPIConfig.kpi_key == kpi["key"],
                    )
                    .first()
                )
                values = {
                    "kpi_label": kpi["label"],
                    "perspective": kpi["perspective"],
                    "weight": safe_decimal(kpi["weight"]),
                    "direction": kpi["direction"],
                    "unit": kpi["unit"],
                    "color": kpi["color"],
                    "actual_col": kpi["actual_col"],
                    "target_col": kpi["target_col"],
                    "display_order": kpi["display_order"],
                }
                if existing:
                    for key, value in values.items():
                        setattr(existing, key, value)
                else:
                    db.add(
                        TeamKPIConfig(
                            id=uuid.uuid4(),
                            team_id=team.id,
                            performance_level="Employee",
                            position_name=position_name,
                            kpi_key=kpi["key"],
                            **values,
                        )
                    )

        stale_rows = (
            db.query(TeamKPIConfig)
            .filter(
                TeamKPIConfig.team_id == team.id,
                TeamKPIConfig.performance_level == "Employee",
                TeamKPIConfig.position_name.isnot(None),
            )
            .all()
        )
        for row in stale_rows:
            if (row.position_name, row.kpi_key) not in expected_keys:
                db.delete(row)

    @staticmethod
    def _sync_employee_position_config(db, team: Team, config: dict) -> None:
        """Synchronize position-scoped employee configuration for an uploaded team."""
        expected_keys: set[tuple[str, str]] = set()
        for position_name, display_order, kpi in iter_employee_kpi_configs(config):
            expected_keys.add((position_name, kpi["key"]))
            existing = (
                db.query(TeamKPIConfig)
                .filter(
                    TeamKPIConfig.team_id == team.id,
                    TeamKPIConfig.performance_level == "Employee",
                    TeamKPIConfig.position_name == position_name,
                    TeamKPIConfig.kpi_key == kpi["key"],
                )
                .first()
            )
            values = {
                "kpi_label": kpi["label"],
                "perspective": kpi.get("perspective"),
                "weight": safe_decimal(kpi["weight"]),
                "direction": kpi["direction"],
                "unit": kpi["unit"],
                "color": kpi["color"],
                "actual_col": kpi["actual_col"],
                "target_col": kpi["target_col"],
                "achievement_col": kpi.get("achievement_col"),
                "volume_unit": kpi.get("volume_unit"),
                "display_order": display_order,
            }
            if existing:
                for key, value in values.items():
                    setattr(existing, key, value)
            else:
                db.add(TeamKPIConfig(
                    id=uuid.uuid4(),
                    team_id=team.id,
                    performance_level="Employee",
                    position_name=position_name,
                    kpi_key=kpi["key"],
                    **values,
                ))

        stale_rows = (
            db.query(TeamKPIConfig)
            .filter(
                TeamKPIConfig.team_id == team.id,
                TeamKPIConfig.performance_level == "Employee",
            )
            .all()
        )
        for row in stale_rows:
            if (row.position_name or "", row.kpi_key) not in expected_keys:
                db.delete(row)

    def _sync_to_database(
        self,
        records: list[PerformanceRecord],
        employees: list[Employee],
        db_session=None,
        upload_id: str | None = None,
    ) -> None:
        """Mirror processed JSON records into the relational DB so upload persistence is verifiable."""
        if not records:
            return

        db = db_session or SessionLocal()
        owns_session = db_session is None
        try:
            teams_by_name = {}
            for team in db.query(Team).filter(Team.team_level == "employee").all():
                teams_by_name[team.name.lower()] = team
                teams_by_name[team.db_name.lower()] = team

            position_scoped_teams = {record.team for record in records if record.team != "Marketing"}
            teams_to_sync = []
            for team_name in position_scoped_teams:
                try:
                    team_config = load_team_config(team_name)
                except ConfigurationError:
                    continue

                position_team = teams_by_name.get(str(team_name).lower())
                if not position_team:
                    position_team = Team(
                        id=uuid.uuid4(),
                        name=team_config["team"],
                        db_name=team_config["db_name"],
                        display_name=team_config["team"],
                        region=team_config["region"],
                        team_level="employee",
                        is_active=True,
                    )
                    db.add(position_team)
                else:
                    position_team.display_name = team_config["team"]
                    position_team.region = team_config["region"]
                    position_team.is_active = True
                teams_by_name[position_team.name.lower()] = position_team
                teams_by_name[position_team.db_name.lower()] = position_team
                teams_to_sync.append((position_team, team_config))

            if any(record.team == "Marketing" for record in records):
                marketing_team = teams_by_name.get("marketing")
                if not marketing_team:
                    marketing_config = load_team_config("Marketing")
                    marketing_team = Team(
                        id=uuid.uuid4(),
                        name=marketing_config["team"],
                        db_name=marketing_config["db_name"],
                        display_name=marketing_config["team"],
                        region=marketing_config["region"],
                        team_level="employee",
                        is_active=True,
                    )
                    db.add(marketing_team)
                    teams_by_name["marketing"] = marketing_team
                teams_to_sync.append((marketing_team, None))

            db.flush()

            for position_team, team_config in teams_to_sync:
                if position_team.name == "Marketing":
                    self._sync_marketing_config(db, position_team)
                elif team_config:
                    self._sync_employee_position_config(db, position_team, team_config)

            employee_lookup = {}
            seen_employee_ids: set[str] = set()
            for employee in employees:
                employee_key = str(employee.id).strip()
                if not employee_key or employee_key.lower() == "nan":
                    continue
                if employee_key in seen_employee_ids:
                    continue
                seen_employee_ids.add(employee_key)

                team = teams_by_name.get(str(employee.team).lower())
                if not team:
                    logger.warning("DB sync skipped employee because team was not found: %s", employee.team)
                    continue

                existing_employee = (
                    db.query(DBEmployee)
                    .filter(DBEmployee.employee_id == str(employee.id))
                    .first()
                )
                db_employee = existing_employee
                if not db_employee:
                    db_employee = DBEmployee(
                        id=uuid.uuid4(),
                        employee_id=str(employee.id),
                        name=employee.name,
                        team_id=team.id,
                        region=(employee.region or team.region or "UAE"),
                        performance_level=employee.performance_level,
                        position_name=employee.position,
                        is_active=True,
                    )
                    db.add(db_employee)
                else:
                    db_employee.name = employee.name
                    db_employee.team_id = team.id
                    db_employee.region = (employee.region or team.region or "UAE")
                    db_employee.performance_level = employee.performance_level
                    db_employee.position_name = employee.position
                    db_employee.is_active = True
                employee_lookup[employee_key] = db_employee

            db.flush()

            for record in records:
                record_employee_key = str(record.employee_id).strip()
                if not record_employee_key or record_employee_key.lower() == "nan":
                    continue

                team = teams_by_name.get(str(record.team).lower())
                if not team:
                    logger.warning("DB sync skipped performance record because team was not found: %s", record.team)
                    continue

                db_employee = employee_lookup.get(record_employee_key)
                if not db_employee:
                    db_employee = (
                        db.query(DBEmployee)
                        .filter(DBEmployee.employee_id == record_employee_key)
                        .first()
                    )
                if not db_employee:
                    logger.warning("DB sync skipped performance record because employee was not found: %s", record.employee_id)
                    continue

                year = record.year or datetime.datetime.now().year
                
                # Vercel Production: Store upload metadata in the DB natively.
                upload_log = db.query(UploadLog).filter_by(team_id=team.id, month=record.month, year=year).first()
                if not upload_log:
                    upload_log = UploadLog(
                        team_id=team.id,
                        month=record.month,
                        year=year,
                        record_count=0,
                        status="success"
                    )
                    db.add(upload_log)
                    db.flush()
                upload_log.record_count += 1

                existing = (
                    db.query(DBPerformanceRecord)
                    .filter(
                        DBPerformanceRecord.employee_id == db_employee.id,
                        DBPerformanceRecord.month == record.month,
                        DBPerformanceRecord.year == year,
                    )
                    .first()
                )
                if existing:
                    existing.score = safe_decimal(record.evaluation.score)
                    existing.grade = record.evaluation.grade
                    existing.status = self._status_for_record(record)
                    existing.team_id = team.id
                    existing.performance_level = record.performance_level
                    existing.position_name = record.position
                    existing.region = record.region
                    existing.upload_id = upload_log.id
                    db_record = existing
                else:
                    db_record = DBPerformanceRecord(
                        id=uuid.uuid4(),
                        year=year,
                        employee_id=db_employee.id,
                        team_id=team.id,
                        month=record.month,
                        performance_level=record.performance_level,
                        position_name=record.position,
                        region=record.region,
                        score=safe_decimal(record.evaluation.score),
                        grade=record.evaluation.grade,
                        status=self._status_for_record(record),
                        upload_id=upload_log.id,
                    )
                    db.add(db_record)
                    db.flush()

                db.query(KPIValue).filter(
                    KPIValue.record_id == db_record.id,
                    KPIValue.record_year == db_record.year,
                ).delete(synchronize_session=False)

                raw_data = record.raw_data or {}
                team_config = None
                try:
                    team_config = resolve_team_config(
                        load_team_config(record.team),
                        record.performance_level,
                        record.position,
                    )
                except Exception:
                    team_config = None

                if record.kpi_values:
                    for value in record.kpi_values:
                        db.add(KPIValue(
                            id=uuid.uuid4(),
                            record_id=db_record.id,
                            record_year=db_record.year,
                            kpi_key=str(value["kpi_key"]),
                            actual_value=safe_decimal(value.get("actual_value")),
                            target_value=safe_decimal(value.get("target_value")),
                            achievement_ratio=safe_decimal(value.get("achievement_ratio")),
                            weight_applied=safe_decimal(value.get("weight_applied")),
                            contribution=safe_decimal(value.get("contribution")),
                        ))
                elif team_config and team_config.get("kpis"):
                    for idx, kpi in enumerate(team_config["kpis"], start=1):
                        actual_col = kpi.get("actual_col")
                        target_col = kpi.get("target_col")
                        achievement_col = kpi.get("achievement_col")
                        actual_val = raw_data.get(actual_col)
                        target_val = raw_data.get(target_col)
                        if actual_val is None and achievement_col:
                            actual_val = raw_data.get(achievement_col)
                        if actual_val is None:
                            actual_val = 0.0
                        if target_val is None:
                            target_val = 0.0

                        achievement_ratio = calculate_achievement(
                            actual_val,
                            target_val,
                            is_inverse=str(kpi.get("direction", "higher_better")).lower() == "lower_better",
                            cap_at_100=str(kpi.get("capping", "")).lower() == "capped_at_100",
                        )
                        kpi_value = KPIValue(
                            id=uuid.uuid4(),
                            record_id=db_record.id,
                            record_year=db_record.year,
                            kpi_key=str(kpi.get("key") or f"kpi_{idx}"),
                            actual_value=safe_decimal(actual_val),
                            target_value=safe_decimal(target_val),
                            achievement_ratio=safe_decimal(achievement_ratio),
                            weight_applied=safe_decimal(kpi.get("weight", 0.0)),
                            contribution=safe_decimal(min(float(achievement_ratio), 100.0) * float(kpi.get("weight", 0.0))),
                        )
                        db.add(kpi_value)

            if owns_session:
                db.commit()
        except Exception as exc:
            if owns_session:
                db.rollback()
            logger.exception("Database sync failed after upload: %s", exc)
            raise
        finally:
            if owns_session:
                db.close()

    def _process_and_save_excel(
        self,
        excel_file,
        upload_id: Optional[str] = None,
        marketing_result: MarketingImportResult | None = None,
        dry_run: bool = False,
        db_session=None,
    ):
        sheet_names = set(excel_file.sheet_names)
        inbound_df = self.excel_processor.process_sheet_inbound(excel_file) if "Inbound" in sheet_names else pd.DataFrame()
        outbound_df = self.excel_processor.process_sheet_outbound(excel_file) if "Outbound" in sheet_names else pd.DataFrame()
        inbound_uae_df = self.excel_processor.process_sheet_inbound_uae(excel_file) if "Inbound UAE" in sheet_names else pd.DataFrame()
        preapprovals_df = self.excel_processor.process_sheet_preapprovals(excel_file) if "Pre-Approvals IP Offshore" in sheet_names else pd.DataFrame()
        preapprovals_op_dubai_df = self.excel_processor.process_sheet_preapprovals_op_dubai(excel_file) if "Pre-Approvals OP Dubai" in sheet_names else pd.DataFrame()
        preapprovals_ip_final_dubai_df = self.excel_processor.process_sheet_preapprovals_ip_final_dubai(excel_file) if "Pre-Approvals IP Final Dubai" in sheet_names else pd.DataFrame()
        sales_df = self.excel_processor.process_sheet_sales(excel_file) if "Sales" in sheet_names else pd.DataFrame()
        coding_df = self.excel_processor.process_sheet_coding(excel_file) if "Coding" in sheet_names else pd.DataFrame()
        csr_df = self.excel_processor.process_sheet_csr(excel_file) if "CSR" in sheet_names else pd.DataFrame()
        pharmacy_df = self.excel_processor.process_sheet_pharmacy(excel_file) if "Pharmacy" in sheet_names else pd.DataFrame()
        submission_df = self.excel_processor.process_sheet_submission(excel_file) if "Submission" in sheet_names else pd.DataFrame()
        re_submission_df = self.excel_processor.process_sheet_re_submission(excel_file) if "Re-Submission" in sheet_names else pd.DataFrame()

        all_new_records = []
        all_new_employees = []
        detected_teams = []
        attempted_teams = []
        persisted_teams = set()
        failed_teams = []
        marketing_report = marketing_result.report if marketing_result else None

        if marketing_result is not None:
            detected_teams.append("Marketing")
            attempted_teams.append("Marketing")
            all_new_employees.extend(marketing_result.employees)
            all_new_records.extend(marketing_result.records)
            if marketing_result.records:
                persisted_teams.add("Marketing")

        sheet_mappings = []
        if not inbound_df.empty:
            sheet_mappings.append(("Inbound", inbound_df, "EmployeeID", "EnglishName"))
        if not outbound_df.empty:
            sheet_mappings.append(("Outbound", outbound_df, "SGHCode", "EnglishName"))
        if not inbound_uae_df.empty:
            sheet_mappings.append(("Inbound UAE", inbound_uae_df, "HRID", "AgentName"))
        if not preapprovals_df.empty:
            sheet_mappings.append(("Pre-Approvals IP Offshore", preapprovals_df, "HRID", "AgentName"))
        if not preapprovals_op_dubai_df.empty:
            sheet_mappings.append(("Pre-Approvals OP Dubai", preapprovals_op_dubai_df, "HRID", "AgentName"))
        if not preapprovals_ip_final_dubai_df.empty:
            sheet_mappings.append(("Pre-Approvals IP Final Dubai", preapprovals_ip_final_dubai_df, "HRID", "AgentName"))
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
        if not re_submission_df.empty:
            try:
                re_submission_config = load_team_config("Re-Submission")
                sheet_mappings.append((
                    "Re-Submission",
                    re_submission_df,
                    re_submission_config.get("employee_id_col", "EmployeeID"),
                    re_submission_config.get("employee_name_col", "EmployeeName"),
                ))
            except ConfigurationError:
                sheet_mappings.append(("Re-Submission", re_submission_df, "EmployeeID", "EmployeeName"))

        for team_name, df, id_col, _ in sheet_mappings:
            self._normalize_sheet_levels(df, id_col, team_name)

        for team_name, df, id_col, name_col in sheet_mappings:
            detected_teams.append(team_name)
            attempted_teams.append(team_name)
            team_trace = {
                "upload_filename": upload_id,
                "team": team_name,
                "sheet_detected": True,
                "sheet_name": team_name,
                "config_loaded": True,
                "cleaner_selected": team_name,
                "raw_rows": len(df),
                "rows_after_exclusion": 0,
                "cleaned_rows": 0,
                "kpi_attempted": False,
                "kpi_success": False,
                "employees_saved": 0,
                "performance_records_saved": 0,
                "kpi_values_saved": 0,
                "failed_step": None,
                "first_error": None,
            }
            current_row_number = 1
            current_employee_id = "unknown"
            try:
                cleaned_rows = 0
                for current_row_number, (_, row) in enumerate(df.iterrows(), start=2):
                    if self._should_exclude_raw_row(row):
                        continue
                    cleaned_rows += 1

                    name = str(row.get(name_col, "")).strip()
                    emp_id = str(row.get(id_col, "")).strip()
                    # Clean hidden unicode marks (RTL mark \u200f, LTR mark \u200e, zero-width space \u200b, BOM \ufeff)
                    for bad_char in ['\u200f', '\u200e', '\u200b', '\ufeff']:
                        emp_id = emp_id.replace(bad_char, '')
                    emp_id = emp_id.strip()
                    
                    current_employee_id = emp_id or "unknown"
                    
                    if emp_id.endswith(".0"):
                        emp_id = emp_id[:-2]
                    
                    if not name or name.lower() == "total" or not emp_id or emp_id.lower() == "nan":
                        continue

                    performance_level = row["performance_level"]
                    position_value = row.get("Position")
                    if pd.isna(position_value) or not str(position_value).strip():
                        position_value = row.get("Workstream")
                    position = None if pd.isna(position_value) else str(position_value).strip() or None

                    date_val = row.get("Date")
                    month = "Unknown"
                    if isinstance(date_val, (pd.Timestamp, datetime.datetime)):
                        month = date_val.strftime('%B')
                    
                    status = str(row.get("Status", "Active"))
                    is_new = row.get("Is_New", False)
                    region_val = str(row.get("Region", "EGY")).strip().upper()
                    if not region_val or region_val == "NAN":
                        region_val = "UAE" if team_name in ["Inbound UAE", "Sales", "Coding", "CSR", "Pharmacy", "Submission", "Re-Submission", "Pre-Approvals OP Dubai", "Pre-Approvals IP Final Dubai"] else "EGY"

                    employee = Employee(
                        id=emp_id,
                        name=name,
                        team=team_name,
                        status=status,
                        region=region_val,
                        performance_level=performance_level,
                        position=position,
                    )
                    all_new_employees.append(employee)
                    team_trace["employees_saved"] += 1

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
                        rejection_rate=safe_float(
                            row.get("A.InitialRejectionRate")
                            or row.get("IPInitialRejection%")
                            or row.get("A.CSRRejection%")
                            or row.get("A.RejectionRateAfterResubmission")
                            or row.get("A.RejectionRateAfterRe-Submission")
                            or 0.0
                        ),
                        initial_error_rate=safe_float(row.get("Error%", 0.0)),
                        submission_rate=safe_float(row.get("A.TAT48Hours") or row.get("NumberApprovalwithin48hrs") or row.get("A.TAT") or 0.0),
                        quality_rate=safe_float(row.get("A.QualityScore") or row.get("A.QualityErrorsRate") or 0.0),
                        utz_rate=safe_float(row.get("A.UTZ%", 0.0))
                    )

                    row_dict = row.to_dict()
                    team_trace["kpi_attempted"] = True
                    if performance_level == "Employee" and position:
                        score, grade, kpi_values = self.kpi_service.calculate_performance_multi_team(
                            team_name,
                            row_dict,
                            performance_level,
                            position,
                        )
                        achievements = {value["kpi_key"]: value["achievement_ratio"] for value in kpi_values}
                        weights_used = {value["kpi_key"]: value["weight_applied"] for value in kpi_values}
                    elif performance_level == "Employee":
                        score, grade, achievements, weights_used = self.kpi_service.calculate_performance(team_name, row_dict)
                        kpi_values = []
                    else:
                        score, grade, kpi_values = self.kpi_service.calculate_performance_multi_team(
                            team_name, row_dict, performance_level
                        )
                        achievements = {value["kpi_key"]: value["achievement_ratio"] for value in kpi_values}
                        weights_used = {value["kpi_key"]: value["weight_applied"] for value in kpi_values}

                    ach = AchievementMetrics(
                        booking_ach=achievements.get("Booking", 0.0),
                        attend_ach=achievements.get("Attend", 0.0),
                        quality_ach=achievements.get("Quality") or achievements.get("quality_errors_rate") or 0.0,
                        aht_ach=achievements.get("AHT", 0.0),
                        reachability_ach=achievements.get("Other", 0.0) if team_name == "Outbound" else 0.0,
                        abandon_ach=achievements.get("Other", 0.0) if team_name in ["Inbound", "Inbound UAE"] else 0.0,
                        rejection_ach=achievements.get("Rejection") or achievements.get("initial_rejection_rate") or achievements.get("rejection_rate_after_resubmission") or 0.0,
                        initial_error_ach=achievements.get("InitialError", 0.0),
                        submission_ach=achievements.get("Submission") or achievements.get("submission_within_due_date") or achievements.get("tat") or 0.0,
                        op_census_ach=achievements.get("OPCensus", 0.0),
                        op_revenue_ach=achievements.get("OPRevenue", 0.0),
                        ip_census_ach=achievements.get("IPCensus", 0.0),
                        ip_revenue_ach=achievements.get("IPRevenue", 0.0),
                        activity_ach=achievements.get("Activity", 0.0)
                    )

                    root_cause = self.analysis_service.run_root_cause_analysis(team_name, achievements, weights_used, row_dict)
                    if root_cause and kpi_values:
                        root_value = next((value for value in kpi_values if value["kpi_key"] == root_cause.kpi), None)
                        if root_value:
                            root_cause.actual = root_value["actual_value"]
                            root_cause.target = root_value["target_value"]
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
                        performance_level=performance_level,
                        position=position,
                        calls=calls,
                        geo=geo,
                        actual=actual,
                        achievement=ach,
                        evaluation=evaluation,
                        upload_id=upload_id,
                        raw_data={str(k): safe_value(v) for k, v in row_dict.items()},
                        kpi_values=kpi_values,
                    )
                    all_new_records.append(record)
                    team_trace["cleaned_rows"] = cleaned_rows
                    team_trace["performance_records_saved"] += 1
                    team_trace["kpi_success"] = True
                    team_trace["kpi_values_saved"] += len(kpi_values)

                persisted_teams.add(team_name)
                logger.info(
                    "upload_team_trace",
                    extra={
                    "upload_filename": upload_id,
                        **team_trace,
                        "failed_step": None,
                        "first_error": None,
                    },
                )
            except Exception as exc:
                failed_teams.append({
                    "team": team_name,
                    "failed_step": "kpi_calculation",
                    "error": str(exc)[:180],
                })
                team_trace["cleaned_rows"] = cleaned_rows
                team_trace["failed_step"] = "kpi_calculation"
                team_trace["first_error"] = str(exc)[:180]
                logger.exception("upload_team_trace", extra={"upload_filename": upload_id, **team_trace})
                if isinstance(exc, (ConfigurationError, ValueError)):
                    raise UploadProcessingError(
                        f"Row {current_row_number}, employee {current_employee_id}: {exc}",
                        {
                            "detected_teams": detected_teams,
                            "attempted_teams": attempted_teams,
                            "failed_teams": failed_teams,
                            "row": current_row_number,
                            "employee_id": current_employee_id,
                        },
                    ) from exc

        all_new_employees = list({employee.id: employee for employee in all_new_employees}.values())
        imported_teams = list(dict.fromkeys([team_name for team_name, _, _, _ in sheet_mappings]))
        if marketing_result is not None:
            imported_teams.append("Marketing")

        if dry_run:
            return {
                "records_imported": len(all_new_records),
                "employees_imported": len(all_new_employees),
                "teams": imported_teams,
                "detected_teams": detected_teams,
                "attempted_teams": attempted_teams,
                "persisted_teams": sorted(persisted_teams),
                "failed_teams": failed_teams,
                "marketing": marketing_report,
            }

        # Vercel Production Safety: Do not write to JSON repositories. DB is the sole runtime persistence.
        try:
            self._sync_to_database(all_new_records, all_new_employees, db_session=db_session, upload_id=upload_id)
        except Exception as exc:
            report = {
                "records_imported": len(all_new_records),
                "employees_imported": len(all_new_employees),
                "teams": imported_teams,
                "detected_teams": detected_teams,
                "attempted_teams": attempted_teams,
                "persisted_teams": sorted(persisted_teams),
                "failed_teams": failed_teams or [{
                    "team": "All Teams",
                    "failed_step": "db_save",
                    "error": str(exc)[:180],
                }],
            }
            raise UploadProcessingError(str(exc), report) from exc

        # Read all history once (not inside the loop) to avoid O(n²) file reads
        all_history = self.performance_repo.get_all()
        updated_records = []
        from services.planning_service import MONTH_ORDER
        for r in all_new_records:
            emp_history = [h for h in all_history if h.employee_id == r.employee_id]
            emp_history.sort(key=lambda x: (x.year or 0, MONTH_ORDER.get(x.month, 0)))
            
            curr_idx = -1
            for i, h in enumerate(emp_history):
                if h.id == r.id:
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
            "employees_imported": len(all_new_employees),
            "teams": imported_teams,
            "detected_teams": detected_teams,
            "attempted_teams": attempted_teams,
            "persisted_teams": sorted(persisted_teams),
            "failed_teams": failed_teams,
            "marketing": marketing_report,
        }
