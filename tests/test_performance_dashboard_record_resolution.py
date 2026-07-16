from types import SimpleNamespace

from api.routers import performance as performance_router


class _SQLRepositoryStub:
    def __init__(self, _db, _model):
        pass

    def get_dashboard_record_keys(self, **_filters):
        return [
            ("LEGACY-1", "Inbound", "June", 2026),
            ("MARKETING-1", "Marketing", "June", 2026),
        ]


class _JSONRepositoryStub:
    def __init__(self):
        self.records = [
            SimpleNamespace(
                employee_id="LEGACY-1",
                team="Inbound",
                month="June",
                year=None,
                performance_level="Employee",
            ),
            SimpleNamespace(
                employee_id="MARKETING-1",
                team="Marketing",
                month="June",
                year=2026,
                performance_level="Employee",
            ),
        ]

    def get_filtered_by_keys(self, keys):
        return [
            record
            for record in self.records
            if (record.employee_id, record.team, record.month, record.year) in keys
        ]

    def get_filtered(self, **_filters):
        return self.records


def test_unscoped_dashboard_resolves_legacy_yearless_and_current_records(monkeypatch):
    json_repo = _JSONRepositoryStub()
    monkeypatch.setattr(performance_router, "SQLPerformanceRepository", _SQLRepositoryStub)
    monkeypatch.setattr(performance_router, "performance_repo", json_repo)

    records = performance_router._get_dashboard_records(object())

    assert [(record.team, record.year) for record in records] == [
        ("Inbound", None),
        ("Marketing", 2026),
    ]


def test_explicit_year_does_not_include_ambiguous_legacy_yearless_records(monkeypatch):
    json_repo = _JSONRepositoryStub()
    monkeypatch.setattr(performance_router, "SQLPerformanceRepository", _SQLRepositoryStub)
    monkeypatch.setattr(performance_router, "performance_repo", json_repo)

    records = performance_router._get_dashboard_records(object(), year=2026)

    assert [(record.team, record.year) for record in records] == [
        ("Marketing", 2026),
    ]
