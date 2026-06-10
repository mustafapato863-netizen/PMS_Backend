from typing import List, Dict, Any
from models.schemas import PerformanceRecord
from repositories.base import PerformanceRepository

MONTH_ORDER = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
}

class PlanningService:
    def __init__(self, performance_repo: PerformanceRepository):
        self.performance_repo = performance_repo

    def classify_all(self, month: str) -> Dict[str, List[PerformanceRecord]]:
        """
        Classifies all employee performance records for the target month into planning categories.
        Returns:
          - categories (dict): Map of category name to list of PerformanceRecord
        """
        all_records = self.performance_repo.get_all()
        month_records = [r for r in all_records if r.month == month]
        
        # Group records by employee to analyze history
        employee_history: Dict[str, List[PerformanceRecord]] = {}
        for r in all_records:
            employee_history.setdefault(r.employee_id, []).append(r)

        # Sort each employee's history chronologically
        for emp_id in employee_history:
            employee_history[emp_id].sort(key=lambda x: MONTH_ORDER.get(x.month, 0))

        categories = {
            "Reward Candidate": [],
            "Promotion Candidate": [],
            "Training Candidate": [],
            "PI Candidate": [],
            "SIP Candidate": [],
            "Attrition Risk": []
        }

        for r in month_records:
            emp_id = r.employee_id
            history = employee_history.get(emp_id, [])
            
            # Find current index in history
            curr_idx = -1
            for idx, hist_r in enumerate(history):
                if hist_r.month == month:
                    curr_idx = idx
                    break

            # 1. Reward Candidate: Score >= 95 and Attendance >= 95%
            # attend_rate is actual.attend_rate (0-1)
            if r.evaluation.score >= 95.0 and r.actual.attend_rate >= 0.95:
                categories["Reward Candidate"].append(r)

            # 2. Promotion Candidate: Score >= 90 maintained for 3 consecutive months
            # Check if this month and preceding 2 months are all >= 90
            if r.evaluation.score >= 90.0:
                if curr_idx >= 2:
                    h_prev1 = history[curr_idx - 1]
                    h_prev2 = history[curr_idx - 2]
                    if h_prev1.evaluation.score >= 90.0 and h_prev2.evaluation.score >= 90.0:
                        categories["Promotion Candidate"].append(r)
                elif len(history) == 1:
                    # Fallback: if we only have 1 month and it's >= 90, but to be safe we require 3 months
                    pass

            # 3. Training Candidate: Score between 70 and 80, and Root Cause exists
            if 70.0 <= r.evaluation.score <= 80.0 and r.evaluation.root_cause is not None:
                categories["Training Candidate"].append(r)

            # 4. PI Candidate: Score between 50 and 60
            if 50.0 <= r.evaluation.score < 60.0:
                categories["PI Candidate"].append(r)

            # 5. SIP Candidate: Score below 50
            if r.evaluation.score < 50.0:
                categories["SIP Candidate"].append(r)

            # 6. Attrition Risk:
            # - Attendance decline > 20% MoM
            # - Performance decline > 15% MoM
            # - Continuous deterioration for 3 months (Month N-2 > Month N-1 > Month N)
            is_attrition = False
            
            if curr_idx >= 1:
                prev_r = history[curr_idx - 1]
                # Attendance decline (absolute difference, e.g. 0.95 to 0.70 is 0.25 decline)
                attend_decline = prev_r.actual.attend_rate - r.actual.attend_rate
                # Performance decline (absolute difference, e.g. 85.0 to 65.0 is 20.0 decline)
                perf_decline = prev_r.evaluation.score - r.evaluation.score
                
                if attend_decline > 0.20 or perf_decline > 15.0:
                    is_attrition = True

            # Continuous deterioration for 3 months (i.e. score decreasing over 3 consecutive data points)
            if not is_attrition and curr_idx >= 2:
                prev1 = history[curr_idx - 1]
                prev2 = history[curr_idx - 2]
                if prev2.evaluation.score > prev1.evaluation.score > r.evaluation.score:
                    is_attrition = True

            if is_attrition:
                categories["Attrition Risk"].append(r)

        return categories
