import datetime
import uuid

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.database import Base
from models.models import (
    Employee,
    EmployeeUploadBatch,
    PerformanceRecord,
    Team,
    UploadLog,
)
from repositories.employee_upload_repository import EmployeeUploadRepository
from services.kpi_service import KPIService


class _EmptyConfigRepository:
    def get_by_team(self, _team):
        return None


def _kpi_service():
    empty = _EmptyConfigRepository()
    return KPIService(empty, empty)


def test_inbound_june_missing_quality_does_not_poison_reweighted_score():
    row = {
        "Date": datetime.datetime(2026, 6, 1),
        "TotalHandledCalls": 100,
        "Dubai_Booking": 45,
        "Dubai_Attend": 33.75,
        "InboundCalls": 100,
        "AbandonedCalls": 0,
        "A.QualityScore": np.nan,
        "A.UTZ%": 0.85,
        "AHT_Minutes": 2.5,
    }

    score, grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)

    assert score == 100
    assert grade == "A"
    assert achievements["Quality"] == 0
    assert weights["Quality"] == 0
    assert weights["Other"] == 0.15


def test_outbound_june_missing_quality_uses_reachability_weight():
    row = {
        "Date": datetime.datetime(2026, 6, 1),
        "Reached": 100,
        "NumOfLeads": 100 / 0.75,
        "Dubai_Booking": 46,
        "Dubai_Attend": 25.3,
        "A.QualityScore": np.nan,
    }

    score, grade, achievements, weights = _kpi_service().calculate_performance("Outbound", row)

    assert score == 100
    assert grade == "A"
    assert achievements["Quality"] == 0
    assert weights["Quality"] == 0
    assert weights["Other"] == 0.20


def test_preapprovals_without_claims_excludes_error_and_uses_60_40_weights():
    row = {
        "SubmittedClaims": 0,
        "IPInitialRejection%": 0.06,
        "Error%": 0.99,
        "NumberApprovalwithin48hrs": 0.90,
    }

    score, grade, _achievements, weights = _kpi_service().calculate_performance(
        "Pre-Approvals IP Offshore", row
    )

    assert score == 70
    assert grade == "D"
    assert weights == {"Rejection": 0.60, "InitialError": 0, "Submission": 0.40}


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_upload_history_is_grouped_by_workbook_and_delete_respects_current_version():
    db = _db()
    team = Team(id=uuid.uuid4(), name="Inbound", db_name="Inbound", region="EGY")
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-1",
        name="Employee One",
        team=team,
        region="EGY",
    )
    old_batch = EmployeeUploadBatch(
        id=uuid.uuid4(), filename="PMS_v1.xlsx", record_count=1, team_count=1, status="success"
    )
    new_batch = EmployeeUploadBatch(
        id=uuid.uuid4(), filename="PMS_v2.xlsx", record_count=1, team_count=1, status="success"
    )
    old_log = UploadLog(
        id=uuid.uuid4(), batch=old_batch, team=team, month="May", year=2026, record_count=1, status="success"
    )
    new_log = UploadLog(
        id=uuid.uuid4(), batch=new_batch, team=team, month="May", year=2026, record_count=1, status="success"
    )
    current = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee=employee,
        team_id=team.id,
        month="May",
        score=91,
        grade="B",
        status="Meets",
        upload_id=new_log.id,
    )
    db.add_all([team, employee, old_batch, new_batch, old_log, new_log, current])
    db.commit()

    repository = EmployeeUploadRepository(db)
    history = repository.list_batches()

    assert {item["filename"] for item in history} == {"PMS_v1.xlsx", "PMS_v2.xlsx"}
    assert all(item["teams"] == ["Inbound"] for item in history)
    assert all(item["periods"] == ["May 2026"] for item in history)

    assert repository.delete_batch(old_batch.id) == (1, 0)
    db.commit()
    assert db.query(PerformanceRecord).count() == 1

    assert repository.delete_batch(new_batch.id) == (1, 1)
    db.commit()
    assert db.query(PerformanceRecord).count() == 0
