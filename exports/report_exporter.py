import pandas as pd
import io
from typing import Any, List
from models.schemas import PerformanceRecord

class ReportExporter:
    @staticmethod
    def flatten_record(r: PerformanceRecord) -> dict:
        row = {
            "Employee ID": r.employee_id,
            "Employee Name": r.employee_name,
            "Team": r.team,
            "Position": r.position or "",
            "Region": r.region or "",
            "Performance Level": r.performance_level,
            "Year": r.year,
            "Month": r.month,
            "Performance Score": r.evaluation.score,
            "Grade": r.evaluation.grade,
            "Status": r.status or "",
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
            "AHT": r.calls.aht_raw,
        }
        for value in r.kpi_values or []:
            label = str(value.get("label") or value.get("kpi_key") or "KPI")
            row[f"{label} Actual"] = value.get("actual_value")
            row[f"{label} Target"] = value.get("target_value")
            ratio = value.get("achievement_ratio")
            row[f"{label} Achievement (%)"] = round(float(ratio) * 100, 2) if ratio is not None else None
            contribution = value.get("contribution")
            row[f"{label} Contribution (%)"] = round(float(contribution) * 100, 2) if contribution is not None else None
        return row

    @staticmethod
    def export_to_excel(records: List[PerformanceRecord]) -> bytes:
        """Converts performance records to a formatted Excel file binary."""
        flat_records = [ReportExporter.flatten_record(record) for record in records]

        df = pd.DataFrame(flat_records)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="Performance Summary", index=False)
        return output.getvalue()

    @staticmethod
    def export_workbook(
        *,
        metadata: dict[str, Any],
        sheets: dict[str, list[dict[str, Any]]],
    ) -> bytes:
        """Create an Excel workbook from explicitly selected report sections."""
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame([{"Field": key, "Value": value} for key, value in metadata.items()]).to_excel(
                writer,
                sheet_name="Report Metadata",
                index=False,
            )
            for sheet_name, rows in sheets.items():
                pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name[:31], index=False)
        return output.getvalue()

    @staticmethod
    def export_to_csv(records: List[PerformanceRecord]) -> bytes:
        """Converts performance records to CSV binary."""
        flat_records = [ReportExporter.flatten_record(record) for record in records]

        df = pd.DataFrame(flat_records)
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        return output.getvalue()
