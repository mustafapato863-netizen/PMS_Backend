from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


InsightSeverity = Literal["critical", "risk", "opportunity", "information"]
InsightType = Literal["performance", "kpi_driver", "employee_risk", "opportunity", "data_quality"]


class InsightPeriod(BaseModel):
    year: int
    month: str
    key: str


class InsightEvidence(BaseModel):
    label: str
    value: str


class InsightDetail(BaseModel):
    current_value: float | None = None
    previous_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    direction: str | None = None
    impact_points: float | None = None
    affected_teams: list[str] = Field(default_factory=list)
    affected_positions: list[str] = Field(default_factory=list)
    affected_employees: list[str] = Field(default_factory=list)
    evidence: list[InsightEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_focus: str


class InsightItem(BaseModel):
    id: str
    severity: InsightSeverity
    insight_type: InsightType
    title: str
    explanation: str
    scope: str
    impact_points: float | None = None
    trend_label: str
    priority_reason: str
    status: str = "open"
    team: str | None = None
    performance_level: str | None = None
    position: str | None = None
    employee_id: str | None = None
    kpi_key: str | None = None
    included_in_score: bool = True
    weight: float | None = None
    evidence_classification: str | None = None
    detail: InsightDetail
    planning_context: dict[str, str | float | None] = Field(default_factory=dict)


class InsightDriver(BaseModel):
    id: str
    driver: str
    scope: str
    impact_points: float
    direction: Literal["positive", "negative"]
    insight_id: str


class InsightRisk(BaseModel):
    key: str
    label: str
    count: int
    explanation: str
    filter_type: str


class InsightSummary(BaseModel):
    critical: int = 0
    at_risk: int = 0
    opportunities: int = 0
    data_issues: int = 0
    critical_issues: int = 0
    negative_weighted_drivers: int = 0
    positive_weighted_drivers: int = 0
    weighted_negative_impact: float = 0
    weighted_positive_impact: float = 0
    weighted_net_impact: float = 0
    analyzed_kpis: int = 0
    expected_kpis: int = 0
    coverage_percent: float | None = None


class InsightTeamSummary(BaseModel):
    team: str
    current_score: float | None = None
    previous_score: float | None = None
    score_change: float | None = None
    impacted_employees: int = 0
    total_employees: int = 0
    critical: int = 0
    at_risk: int = 0
    opportunities: int = 0
    main_insight_id: str | None = None
    main_cause: str | None = None


class InsightFilterOptions(BaseModel):
    periods: list[InsightPeriod] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    performance_levels: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    employees: list[dict[str, str]] = Field(default_factory=list)
    kpis: list[dict[str, str]] = Field(default_factory=list)
    severities: list[str] = Field(default_factory=lambda: ["critical", "risk", "opportunity", "information"])
    insight_types: list[str] = Field(default_factory=lambda: ["performance", "kpi_driver", "employee_risk", "opportunity", "data_quality"])
    statuses: list[str] = Field(default_factory=lambda: ["open"])


class InsightComparison(BaseModel):
    current: InsightPeriod | None = None
    previous: InsightPeriod | None = None
    is_adjacent: bool = False
    note: str | None = None


class InsightsWorkspace(BaseModel):
    summary: InsightSummary
    priority_insights: list[InsightItem]
    team_analyses: list[InsightItem] = Field(default_factory=list)
    performance_drivers: list[InsightDriver]
    risks: list[InsightRisk]
    opportunities: list[InsightItem]
    data_issues: list[InsightItem]
    team_summaries: list[InsightTeamSummary] = Field(default_factory=list)
    options: InsightFilterOptions
    comparison: InsightComparison
    deferred_capabilities: list[str] = Field(default_factory=list)


class InsightsWorkspaceResponse(BaseModel):
    success: bool
    message: str
    data: InsightsWorkspace
