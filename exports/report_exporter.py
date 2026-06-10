import pandas as pd
import io
from typing import List
from models.schemas import PerformanceRecord

class ReportExporter:
    @staticmethod
    def export_to_excel(records: List[PerformanceRecord]) -> bytes:
        """Converts performance records to a formatted Excel file binary."""
        flat_records = []
        for r in records:
            flat_records.append({
                "Employee ID": r.employee_id,
                "Employee Name": r.employee_name,
                "Team": r.team,
                "Month": r.month,
                "Performance Score": r.evaluation.score,
                "Grade": r.evaluation.grade,
                "Root Cause": r.evaluation.root_cause.kpi if r.evaluation.root_cause else "None",
                "Root Cause Gap": r.evaluation.root_cause.impact_pct if r.evaluation.root_cause else 0.0,
                "AI Suggested Action": r.evaluation.suggested_action or "None",
                "Manager Corrective Action": r.evaluation.corrective_action or "None",
                "Manager Notes": r.evaluation.manager_notes or "None",
                "Booking Rate (%)": round(r.actual.booking_rate * 100, 2),
                "Attendance Rate (%)": round(r.actual.attend_rate * 100, 2),
                "Abandon Rate (%)": round(r.actual.abandon_rate * 100, 2),
                "Inbound Calls": r.calls.inbound,
                "Outbound Calls": r.calls.outbound,
                "AHT": r.calls.aht_raw
            })

        df = pd.DataFrame(flat_records)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="Performance Summary", index=False)
        return output.getvalue()

    @staticmethod
    def export_to_csv(records: List[PerformanceRecord]) -> bytes:
        """Converts performance records to CSV binary."""
        flat_records = []
        for r in records:
            flat_records.append({
                "Employee ID": r.employee_id,
                "Employee Name": r.employee_name,
                "Team": r.team,
                "Month": r.month,
                "Performance Score": r.evaluation.score,
                "Grade": r.evaluation.grade,
                "Root Cause": r.evaluation.root_cause.kpi if r.evaluation.root_cause else "None",
                "AI Suggested Action": r.evaluation.suggested_action or "None",
                "Manager Corrective Action": r.evaluation.corrective_action or "None",
                "Booking Rate (%)": round(r.actual.booking_rate * 100, 2),
                "Attendance Rate (%)": round(r.actual.attend_rate * 100, 2),
                "Abandon Rate (%)": round(r.actual.abandon_rate * 100, 2),
                "Inbound Calls": r.calls.inbound,
                "Outbound Calls": r.calls.outbound,
                "AHT": r.calls.aht_raw
            })

        df = pd.DataFrame(flat_records)
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        return output.getvalue()
