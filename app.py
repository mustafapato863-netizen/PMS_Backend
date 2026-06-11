"""
FastAPI backend server for PMS Dashboard.
Provides clean endpoints for PMS Dashboard following Clean Architecture.

Run with:  cd Backend && uvicorn app:app --reload --port 8000
"""
import sys
import os
import io

# Force UTF-8 encoding for console output (Windows compatibility)
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Ensure Backend directory is on the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.routes import router as api_router
from api.routes import (
    performance_repo, employee_repo, excel_processor, kpi_service,
    analysis_service, planning_service, trend_service, notes_repo, actions_repo, safe_value
)
from config.settings import DEFAULT_FILE_PATH
from models.schemas import (
    Employee, PerformanceRecord, CallsData, GeoBreakdown, GeoData, ActualMetrics, AchievementMetrics, EvaluationData
)
import pandas as pd
import datetime

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

def seed_database():
    """Initializes the database from the default Excel file if performance repository is empty."""
    if not os.path.exists(DEFAULT_FILE_PATH):
        print(f"⚠️ Default Excel file not found at {DEFAULT_FILE_PATH}. Skipping seeding.")
        return

    # Check if performance records are already populated
    if len(performance_repo.get_all()) > 0:
        print("✓ Performance database is already populated. Skipping seeding.")
        return

    print("🌱 Seeding database from default Excel file...")
    try:
        excel_file = excel_processor.load_excel(DEFAULT_FILE_PATH)
        
        # Parse sheets
        inbound_df = excel_processor.process_sheet_inbound(excel_file)
        outbound_df = excel_processor.process_sheet_outbound(excel_file)
        inbound_uae_df = excel_processor.process_sheet_inbound_uae(excel_file)
        preapprovals_df = excel_processor.process_sheet_preapprovals(excel_file)

        all_new_records = []
        all_new_employees = []

        sheet_mappings = [
            ("Inbound", inbound_df, "EmployeeID", "EnglishName"),
            ("Outbound", outbound_df, "SGHCode", "EnglishName"),
            ("Inbound UAE", inbound_uae_df, "HRID", "AgentName"),
            ("Pre-Approvals IP Offshore", preapprovals_df, "HRID", "AgentName")
        ]

        for team_name, df, id_col, name_col in sheet_mappings:
            for _, row in df.iterrows():
                name = str(row.get(name_col, "")).strip()
                emp_id = str(row.get(id_col, "")).strip()
                
                # Remove decimal part from ids parsed as float
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

                # Save Employee record
                employee = Employee(
                    id=emp_id,
                    name=name,
                    team=team_name,
                    status=status
                )
                all_new_employees.append(employee)

                # Fetch AHT raw
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

                # Standard calls mapping
                calls = CallsData(
                    inbound=safe_int(row.get("InboundCalls", 0)) if "InboundCalls" in df.columns else safe_int(row.get("InboundCalls ", 0)) if "InboundCalls " in df.columns else 0,
                    outbound=safe_int(row.get("OutboundCalls", 0)) if "OutboundCalls" in df.columns else 0,
                    total_handled=safe_int(row.get("TotalHandledCalls", 0)) if "TotalHandledCalls" in df.columns else (safe_int(row.get("Reached", 0)) if team_name == "Outbound" else 0),
                    abandoned=safe_int(row.get("AbandonedCalls", 0)) if "AbandonedCalls" in df.columns else 0,
                    aht_raw=aht_raw
                )

                # Geo mapping
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
                    rejection_rate=safe_float(row.get("IPInitialRejection%", 0.0)),
                    initial_error_rate=safe_float(row.get("Error%", 0.0)),
                    submission_rate=safe_float(row.get("NumberApprovalwithin48hrs", 0.0)),
                    quality_rate=safe_float(row.get("A.QualityScore", 0.0)),
                    utz_rate=safe_float(row.get("A.UTZ%", 0.0))
                )

                # Run KPI scoring engine
                score, grade, achievements, weights_used = kpi_service.calculate_performance(team_name, row.to_dict())

                # Populate achievements model
                ach = AchievementMetrics(
                    booking_ach=achievements.get("Booking", 0.0),
                    attend_ach=achievements.get("Attend", 0.0),
                    quality_ach=achievements.get("Quality", 0.0),
                    aht_ach=achievements.get("AHT", 0.0),
                    reachability_ach=achievements.get("Other", 0.0) if team_name == "Outbound" else 0.0,
                    abandon_ach=achievements.get("Other", 0.0) if team_name in ["Inbound", "Inbound UAE"] else 0.0,
                    rejection_ach=achievements.get("Rejection", 0.0),
                    initial_error_ach=achievements.get("InitialError", 0.0),
                    submission_ach=achievements.get("Submission", 0.0)
                )

                root_cause = analysis_service.run_root_cause_analysis(team_name, achievements, weights_used, row.to_dict())
                suggested_action = analysis_service.generate_suggested_action(score, is_new, root_cause)

                note_rec = notes_repo.get_note(emp_id, month)
                action_rec = actions_repo.get_latest_by_employee_and_month(emp_id, month)

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
                    calls=calls,
                    geo=geo,
                    actual=actual,
                    achievement=ach,
                    evaluation=evaluation,
                    raw_data={str(k): safe_value(v) for k, v in row.to_dict().items()}
                )
                all_new_records.append(record)

        # Save all to repositories
        employee_repo.save_all(all_new_employees)
        performance_repo.save_all(all_new_records)

        # Post-Processing: Run Planning classifications and Trends updates
        updated_records = []
        for r in all_new_records:
            history = performance_repo.get_all()
            emp_history = [h for h in history if h.employee_id == r.employee_id]
            from services.planning_service import MONTH_ORDER
            emp_history.sort(key=lambda x: MONTH_ORDER.get(x.month, 0))
            
            curr_idx = -1
            for i, h in enumerate(emp_history):
                if h.month == r.month:
                    curr_idx = i
                    break

            if curr_idx >= 0:
                trend_status = trend_service.calculate_trends(emp_history, curr_idx)
                r.evaluation.trend_status = trend_status

            planning_lists = planning_service.classify_all(r.month)
            r.evaluation.planning_category = []
            for cat, recs in planning_lists.items():
                if any(x.id == r.id for x in recs):
                    r.evaluation.planning_category.append(cat)

            updated_records.append(r)

        performance_repo.save_all(updated_records)
        print("🌱 Seeding completed successfully!")
    except Exception as e:
        print(f"❌ Seeding database failed: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run database seeder on startup
    seed_database()
    yield

app = FastAPI(
    title="PMS Dashboard API",
    description="Backend Clean Architecture API forSaudi German Hospital Performance Management System",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware — allow frontend dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open to all origins for easier dashboard connections
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "api": "PMS Dashboard API - Clean Architecture",
        "version": "2.0.0",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)


# ========== Cloudflare Workers Compatibility Layer ==========
# Export FastAPI app for Workers compatibility
handler = app

try:
    from workers import WorkerEntrypoint
    import asgi

    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            return await asgi.fetch(app, request, self.env)
            
    # Make the entrypoint class available as default export
    default = Default
except ImportError:
    # Local execution or non-worker environment
    pass


