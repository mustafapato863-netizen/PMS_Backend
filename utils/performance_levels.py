PERFORMANCE_LEVELS = ("Employee", "Managerial", "Corporate")
PERFORMANCE_LEVEL_ALIASES = {
    "emp": "Employee",
    "employee": "Employee",
    "manager": "Managerial",
    "managerial": "Managerial",
    "corp": "Corporate",
    "corporate": "Corporate",
}


def normalize_performance_level(value, *, allow_all: bool = False) -> str:
    normalized = "" if value is None else str(value).strip().lower()
    if allow_all and (not normalized or normalized == "all"):
        return "All"
    try:
        return PERFORMANCE_LEVEL_ALIASES[normalized]
    except KeyError as exc:
        accepted = ", ".join(PERFORMANCE_LEVEL_ALIASES)
        raise ValueError(f"Invalid performance level {value!r}. Accepted values: {accepted}") from exc
