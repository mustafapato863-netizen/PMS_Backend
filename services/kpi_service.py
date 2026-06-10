import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
from models.schemas import PerformanceRecord, KPIWeight, Target
from repositories.base import KPIWeightsRepository, TargetsRepository

def safe_float(val, default=0.0) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

class KPIService:
    def __init__(self, weights_repo: KPIWeightsRepository, targets_repo: TargetsRepository):
        self.weights_repo = weights_repo
        self.targets_repo = targets_repo
        self._initialize_defaults()

    def _initialize_defaults(self):
        # Default weights
        default_weights = {
            "Inbound": {
                "Attend": 0.70,
                "Booking": 0.10,
                "Quality": 0.05,
                "AHT": 0.05,
                "Other": 0.10  # UTZ or Abandon
            },
            "Outbound": {
                "Attend": 0.70,
                "Booking": 0.10,
                "Quality": 0.10,
                "AHT": 0.00,
                "Other": 0.10  # Reachability
            },
            "Inbound UAE": {
                "Attend": 0.70,
                "Booking": 0.20,
                "Quality": 0.00,
                "AHT": 0.00,
                "Other": 0.10  # Abandon
            },
            "Pre-Approvals IP Offshore": {
                "Rejection": 0.50,
                "InitialError": 0.20,
                "Submission": 0.30
            }
        }
        for team, weights in default_weights.items():
            if not self.weights_repo.get_by_team(team):
                self.weights_repo.save(KPIWeight(team=team, weights=weights))

        # Default targets
        default_targets = {
            "Inbound": {
                "Attend": 0.75,
                "Booking": 0.45,
                "Quality": 0.95,
                "AHT": 150.0,  # 2.5 minutes (150 seconds)
                "Abandon": 0.01, # 1%
                "UTZ": 0.85
            },
            "Outbound": {
                "Attend": 0.55,
                "Booking": 0.46,
                "Quality": 0.95,
                "Reachability": 0.75
            },
            "Inbound UAE": {
                "Attend": 0.75,
                "Booking": 0.60,
                "Abandon": 0.01
            },
            "Pre-Approvals IP Offshore": {
                "Rejection": 0.03,  # 3% target initial rejection rate (lower is better)
                "InitialError": 0.03, # 3% target error rate (lower is better)
                "Submission": 0.90 # 90% within due date
            }
        }
        for team, targets in default_targets.items():
            if not self.targets_repo.get_by_team(team):
                self.targets_repo.save(Target(team=team, targets=targets))

    def calculate_performance(self, team: str, row: Dict[str, Any]) -> Tuple[float, str, Dict[str, float], Dict[str, float]]:
        """
        Calculate performance score and grade.
        Returns:
          - score (float): 0-100 range
          - grade (str)
          - achievements (dict): map of KPI name to achievement rate (0-1)
          - weights (dict): KPI weights used for this calculation
        """
        # Load weights and targets (fallback to defaults if repo fails)
        w_record = self.weights_repo.get_by_team(team)
        weights = w_record.weights if w_record else {}

        target_rec = self.targets_repo.get_by_team(team)
        targets = target_rec.targets if target_rec else {}

        achievements = {}
        final_weights = {}

        # Import helper functions
        from utils.helpers import convert_aht_to_minutes, convert_percentage

        if team == "Inbound":
            # 1. Raw Inbound Volumes
            total_handled = safe_float(row.get("TotalHandledCalls"))
            
            dubai_booking = safe_float(row.get("Dubai_Booking"))
            sharjah_booking = safe_float(row.get("Sharjah_Booking"))
            ajman_booking = safe_float(row.get("Ajman_Booking"))
            clinics_booking = safe_float(row.get("Clinics_Booking"))
            total_bookings = dubai_booking + sharjah_booking + ajman_booking + clinics_booking

            dubai_attend = safe_float(row.get("Dubai_Attend"))
            sharjah_attend = safe_float(row.get("Sharjah_Attend"))
            ajman_attend = safe_float(row.get("Ajman_Attend"))
            clinics_attend = safe_float(row.get("Clinics_Attend") or row.get("clinics.Attend") or row.get("clinics_Attend") or row.get("Clinics.Attend"))
            total_attends = dubai_attend + sharjah_attend + ajman_attend + clinics_attend

            inbound_calls = safe_float(row.get("InboundCalls") or row.get("InboundCalls "))
            abandoned_calls = safe_float(row.get("AbandonedCalls"))

            # 2. Actual Rate Calculations
            actual_booking_cr = total_bookings / total_handled if total_handled > 0 else 0.0
            actual_attend_cr = total_attends / total_bookings if total_bookings > 0 else 0.0
            actual_abandon_rate = abandoned_calls / inbound_calls if inbound_calls > 0 else 0.0
            
            # Fetch actual quality
            actual_quality = convert_percentage(row.get("A.QualityScore", 0.0))
            # Fetch actual UTZ
            actual_utz = convert_percentage(row.get("A.UTZ%", 0.0))

            # Fetch target values
            t_booking = targets.get("Booking", 0.45)
            t_attend = targets.get("Attend", 0.75)
            t_aht = targets.get("AHT", 150.0)
            t_quality = targets.get("Quality", 0.95)
            t_utz = targets.get("UTZ", 0.85)
            t_abandon = targets.get("Abandon", 0.01)

            # Get Actual AHT in seconds
            aht_val = row.get("AHT_Minutes")
            if aht_val is None or pd.isna(aht_val):
                raw_aht = row.get("AHT") or row.get("A.AHT") or row.get("A.AHT.1")
                aht_minutes = convert_aht_to_minutes(raw_aht)
            else:
                aht_minutes = safe_float(aht_val)
            actual_aht_seconds = aht_minutes * 60.0

            # 3. Achievement Calculations (Capped at 1.0)
            attend_ach = min(1.0, actual_attend_cr / t_attend) if t_attend > 0 else 0.0
            booking_ach = min(1.0, actual_booking_cr / t_booking) if t_booking > 0 else 0.0
            quality_ach = min(1.0, actual_quality / t_quality) if t_quality > 0 else 0.0
            aht_ach = min(1.0, t_aht / actual_aht_seconds) if actual_aht_seconds > 0 else 0.0
            utz_ach = min(1.0, actual_utz / t_utz) if t_utz > 0 else 0.0
            
            # Abandon achievement is Target / Actual (inverse metric)
            if actual_abandon_rate <= t_abandon:
                abandon_ach = 1.0
            else:
                abandon_ach = min(1.0, t_abandon / actual_abandon_rate) if actual_abandon_rate > 0 else 1.0

            # 4. Swappable UTZ / Abandon metric logic
            utz_raw = row.get("A.UTZ%")
            if utz_raw is None or (isinstance(utz_raw, float) and np.isnan(utz_raw)) or pd.isna(utz_raw):
                other_ach = abandon_ach
            else:
                other_ach = utz_ach

            achievements = {
                "Attend": attend_ach,
                "Booking": booking_ach,
                "Quality": quality_ach,
                "AHT": aht_ach,
                "Other": other_ach
            }
            final_weights = weights

            # Inject computed values back to row for backward compatibility
            row["A.Booking%"] = actual_booking_cr
            row["A.Attend%"] = actual_attend_cr
            row["A.AbandonRate%"] = actual_abandon_rate
            row["A.UTZ%"] = actual_utz
            row["A.QualityScore"] = actual_quality
            row["AHT_Minutes"] = aht_minutes
            row["Booking%Ach%"] = booking_ach
            row["Attend%Ach%"] = attend_ach
            row["QualityTargetAch%"] = quality_ach
            row["AHTAch%"] = aht_ach
            row["UTZ%Ach%"] = utz_ach
            row["AbandonRate%Ach%"] = abandon_ach

        elif team == "Outbound":
            # 1. Raw Outbound Volumes
            reached = safe_float(row.get("Reached"))
            num_leads = safe_float(row.get("NumOfLeads") or row.get("NumOfLeads "))
            
            dubai_booking = safe_float(row.get("Dubai_Booking") or row.get("Dubai _Booking"))
            sharjah_booking = safe_float(row.get("Sharjah_Booking") or row.get("Sharjah_Booking "))
            ajman_booking = safe_float(row.get("Ajman_Booking") or row.get("Ajman_Booking "))
            clinics_booking = safe_float(row.get("Clinics_Booking") or row.get("Clinics _Booking") or row.get("clinics_Booking") or row.get("clinics.Booking") or 0.0)
            total_bookings = dubai_booking + sharjah_booking + ajman_booking + clinics_booking

            dubai_attend = safe_float(row.get("Dubai_Attend") or row.get("Dubai _Attend"))
            sharjah_attend = safe_float(row.get("Sharjah_Attend") or row.get("Sharjah_Attend "))
            ajman_attend = safe_float(row.get("Ajman_Attend") or row.get("Ajman_Attend "))
            clinics_attend = safe_float(row.get("Clinics_Attend") or row.get("Clinics_Attend ") or row.get("clinics_Attend") or row.get("clinics.Attend") or 0.0)
            total_attends = dubai_attend + sharjah_attend + ajman_attend + clinics_attend

            actual_booking_cr = total_bookings / reached if reached > 0 else 0.0
            actual_attend_cr = total_attends / total_bookings if total_bookings > 0 else 0.0
            actual_reachability = reached / num_leads if num_leads > 0 else 0.0
            actual_quality = convert_percentage(row.get("A.QualityScore", 0.0))

            t_booking = targets.get("Booking", 0.55)
            t_attend = targets.get("Attend", 0.75)
            t_quality = targets.get("Quality", 0.95)
            t_reachability = targets.get("Reachability", 0.95)

            booking_ach = min(1.0, actual_booking_cr / t_booking) if t_booking > 0 else 0.0
            attend_ach = min(1.0, actual_attend_cr / t_attend) if t_attend > 0 else 0.0
            quality_ach = min(1.0, actual_quality / t_quality) if t_quality > 0 else 0.0
            reachability_ach = min(1.0, actual_reachability / t_reachability) if t_reachability > 0 else 0.0

            achievements = {
                "Attend": attend_ach,
                "Booking": booking_ach,
                "Quality": quality_ach,
                "Other": reachability_ach
            }
            final_weights = {
                "Attend": weights.get("Attend", 0.70),
                "Booking": weights.get("Booking", 0.10),
                "Quality": weights.get("Quality", 0.10),
                "Other": weights.get("Other", 0.10)
            }

            row["A.Booking%"] = actual_booking_cr
            row["A.Attend%"] = actual_attend_cr
            row["A.Reachability%"] = actual_reachability
            row["A.QualityScore"] = actual_quality
            row["BookingC.RAch%"] = booking_ach
            row["AttendC.RAch%"] = attend_ach
            row["QualityAch%"] = quality_ach
            row["Reachability%Ach%"] = reachability_ach

        elif team == "Inbound UAE":
            # 1. Raw UAE Inbound Volumes
            total_handled = safe_float(row.get("TotalHandledCalls"))
            inbound_calls = safe_float(row.get("InboundCalls") or row.get("InboundCalls "))
            abandoned_calls = safe_float(row.get("AbandonedCalls"))
            
            dubai_booking = safe_float(row.get("Dubai_Booking") or row.get("Dubai _Booking"))
            sharjah_booking = safe_float(row.get("Sharjah_Booking") or row.get("Sharjah_Booking "))
            ajman_booking = safe_float(row.get("Ajman_Booking") or row.get("Ajman_Booking "))
            clinics_booking = safe_float(row.get("Clinics_Booking") or row.get("Clinics _Booking"))
            total_bookings = dubai_booking + sharjah_booking + ajman_booking + clinics_booking

            dubai_attend = safe_float(row.get("Dubai_Attend") or row.get("Dubai _Attend"))
            sharjah_attend = safe_float(row.get("Sharjah_Attend") or safe_float(row.get("Sharjah_Attend ")))
            ajman_attend = safe_float(row.get("Ajman_Attend") or safe_float(row.get("Ajman_Attend ")))
            clinics_attend = safe_float(row.get("Clinics_Attend") or safe_float(row.get("Clinics_Attend ")))
            total_attends = dubai_attend + sharjah_attend + ajman_attend + clinics_attend

            actual_booking_cr = total_bookings / total_handled if total_handled > 0 else 0.0
            actual_attend_cr = total_attends / total_bookings if total_bookings > 0 else 0.0
            actual_abandon_rate = abandoned_calls / inbound_calls if inbound_calls > 0 else 0.0

            t_booking = targets.get("Booking", 0.60)
            t_attend = targets.get("Attend", 0.75)
            t_abandon = targets.get("Abandon", 0.01)

            booking_ach = min(1.0, actual_booking_cr / t_booking) if t_booking > 0 else 0.0
            attend_ach = min(1.0, actual_attend_cr / t_attend) if t_attend > 0 else 0.0
            
            if actual_abandon_rate <= t_abandon:
                abandon_ach = 1.0
            else:
                abandon_ach = min(1.0, t_abandon / actual_abandon_rate) if actual_abandon_rate > 0 else 1.0

            achievements = {
                "Attend": attend_ach,
                "Booking": booking_ach,
                "Other": abandon_ach
            }
            final_weights = {
                "Attend": weights.get("Attend", 0.70),
                "Booking": weights.get("Booking", 0.20),
                "Other": weights.get("Other", 0.10)
            }

            row["A.Booking%"] = actual_booking_cr
            row["A.Attend%"] = actual_attend_cr
            row["A.AbandonRate%"] = actual_abandon_rate
            row["BookingC.RAch%"] = booking_ach
            row["AttendC.RAch%"] = attend_ach
            row["AbandonRateAch%"] = abandon_ach

        elif team == "Pre-Approvals IP Offshore":
            actual_rejection = convert_percentage(row.get("IPInitialRejection%", 0.0))
            actual_error = convert_percentage(row.get("Error%", 0.0))
            actual_submission = convert_percentage(row.get("NumberApprovalwithin48hrs") or row.get("NumberApprovalwithin48hrs ") or 0.0)

            t_rej = targets.get("Rejection", 0.03)
            t_err = targets.get("InitialError", 0.03)
            t_sub = targets.get("Submission", 0.90)

            claims = safe_float(row.get("SubmittedClaims"))
            
            # Rejection achievement is inverse
            if actual_rejection <= t_rej:
                rejection_ach = 1.0
            else:
                rejection_ach = min(1.0, t_rej / actual_rejection) if actual_rejection > 0 else 1.0
            
            # Error achievement is inverse, 0 if no claims
            if claims == 0:
                initial_error_ach = 0.0
            else:
                if actual_error <= t_err:
                    initial_error_ach = 1.0
                else:
                    initial_error_ach = min(1.0, t_err / actual_error) if actual_error > 0 else 1.0
            
            # Submission achievement (uncapped)
            submission_ach = actual_submission / t_sub if t_sub > 0 else 0.0

            # Dynamic weights logic
            if claims == 0:
                w_rej = 0.60
                w_err = 0.00
                w_sub = 0.40
            else:
                w_rej = 0.50
                w_err = 0.20
                w_sub = 0.30

            achievements = {
                "Rejection": rejection_ach,
                "InitialError": initial_error_ach,
                "Submission": submission_ach
            }
            final_weights = {
                "Rejection": w_rej,
                "InitialError": w_err,
                "Submission": w_sub
            }

            row["IPInitialRejection%"] = actual_rejection
            row["Error%"] = actual_error
            row["NumberApprovalwithin48hrs"] = actual_submission
            row["RejectionRate"] = rejection_ach
            row["InitialError%"] = initial_error_ach
            row["%ofSubmissionWithinDuedate"] = submission_ach

        # Calculate score (normalized to 0-100)
        raw_score = 0.0
        for kpi, ach in achievements.items():
            wt = final_weights.get(kpi, 0.0)
            raw_score += ach * wt

        score = float(round(raw_score * 100.0, 2))
        grade = self.assign_grade(score)

        # Write score back to row
        if team == "Inbound":
            row["PerformanceScore%"] = score
        elif team in ["Outbound", "Pre-Approvals IP Offshore"]:
            row["PerformanceScor%"] = score
        elif team == "Inbound UAE":
            row["PerformanceScore%"] = score

        return score, grade, achievements, final_weights

    @staticmethod
    def assign_grade(score: float) -> str:
        """Assign performance grade based on picture ranges."""
        if score >= 100.0:
            return "A"
        elif score >= 90.0:
            return "B"
        elif score >= 80.0:
            return "C"
        elif score >= 70.0:
            return "D"
        else:
            return "E"
