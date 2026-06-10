from typing import List, Dict, Any
from models.schemas import PerformanceRecord
from repositories.base import PerformanceRepository
from services.planning_service import PlanningService, MONTH_ORDER

class InsightsService:
    def __init__(self, performance_repo: PerformanceRepository, planning_service: PlanningService):
        self.performance_repo = performance_repo
        self.planning_service = planning_service

    def generate_insights(self, month: str) -> List[Dict[str, str]]:
        """Generates dynamic executive insights for the selected month."""
        insights = []

        all_records = self.performance_repo.get_all()
        curr_records = [r for r in all_records if r.month == month]
        
        if not curr_records:
            return [{"type": "warning", "message": f"No performance records available for {month} to compile insights."}]

        # 1. Team Performance Comparison
        # Resolve previous month name
        prev_month = None
        curr_order = MONTH_ORDER.get(month, 0)
        for m, o in MONTH_ORDER.items():
            if o == curr_order - 1:
                prev_month = m
                break

        prev_records = [r for r in all_records if r.month == prev_month] if prev_month else []

        teams = list(set(r.team for r in curr_records))
        team_averages = {}

        for team in teams:
            team_curr = [r.evaluation.score for r in curr_records if r.team == team]
            team_prev = [r.evaluation.score for r in prev_records if r.team == team]
            
            avg_curr = sum(team_curr) / len(team_curr) if team_curr else 0.0
            avg_prev = sum(team_prev) / len(team_prev) if team_prev else 0.0
            team_averages[team] = (avg_curr, avg_prev)

            if team_curr and team_prev:
                diff = avg_curr - avg_prev
                if diff > 1.0:
                    insights.append({
                        "type": "positive",
                        "message": f"{team} team improved by {diff:.1f}% compared to last month."
                    })
                elif diff < -3.0:
                    insights.append({
                        "type": "warning",
                        "message": f"{team} team performance declined by {abs(diff):.1f}% compared to last month."
                    })

        # 2. Attendance Impact on Low Performers
        low_performers = [r for r in curr_records if r.evaluation.score < 70.0]
        if low_performers:
            attend_rc_cnt = sum(1 for r in low_performers if r.evaluation.root_cause and r.evaluation.root_cause.kpi == "Attend")
            pct = int(round((attend_rc_cnt / len(low_performers)) * 100))
            if pct > 30:
                insights.append({
                    "type": "warning",
                    "message": f"Attendance contributes to {pct}% of low performer cases."
                })

        # 3. Planning categories counts
        planning_lists = self.planning_service.classify_all(month)
        
        training_cnt = len(planning_lists.get("Training Candidate", []))
        if training_cnt > 0:
            insights.append({
                "type": "warning",
                "message": f"{training_cnt} employees are recommended for training."
            })

        promo_cnt = len(planning_lists.get("Promotion Candidate", []))
        if promo_cnt > 0:
            insights.append({
                "type": "positive",
                "message": f"{promo_cnt} employees qualify for promotion review."
            })

        attrition_cnt = len(planning_lists.get("Attrition Risk", []))
        if attrition_cnt > 0:
            insights.append({
                "type": "warning",
                "message": f"{attrition_cnt} employees show high attrition risk characteristics."
            })

        # 4. Highest Quality Score
        team_quality = {}
        for team in teams:
            team_curr_recs = [r for r in curr_records if r.team == team]
            quality_scores = []
            for r in team_curr_recs:
                val = r.achievement.quality_ach if r.achievement.quality_ach > 0 else r.raw_data.get("A.QualityScore", 0.0)
                if val:
                    quality_scores.append(float(val))
            if quality_scores:
                team_quality[team] = sum(quality_scores) / len(quality_scores)

        if team_quality:
            top_quality_team = max(team_quality, key=team_quality.get)
            top_quality_score = team_quality[top_quality_team] * 100.0
            insights.append({
                "type": "positive",
                "message": f"{top_quality_team} achieved the highest quality score averaging {top_quality_score:.1f}%."
            })

        # Default fallback if list is empty
        if not insights:
            insights.append({
                "type": "positive",
                "message": "All team metrics are performing stable within expectations."
            })

        return insights
