"""
Team configuration loader.
Discovers and loads team configurations from /config/teams/*.json files.
Validates configurations for correctness and consistency.
"""

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from utils.performance_levels import PERFORMANCE_LEVELS, normalize_performance_level

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Base exception for configuration errors."""
    pass


class WeightValidationError(ConfigurationError):
    """Exception raised when KPI weights don't sum to 1.0."""
    pass


class ThresholdValidationError(ConfigurationError):
    """Exception raised when grade thresholds are not in descending order."""
    pass


def _validate_weights(kpis: List[Dict[str, Any]], context: str = "configuration") -> Tuple[bool, List[str]]:
    """
    Validate that KPI weights sum to 1.0 within 0.001 tolerance.
    
    Args:
        kpis: List of KPI definitions from config
        
    Returns:
        Tuple of (is_valid, [error_messages])
    """
    errors = []
    
    if not kpis:
        errors.append("No KPIs defined in configuration")
        return False, errors
    
    total_weight = sum(float(kpi.get('weight', 0)) for kpi in kpis)
    if total_weight > 1.001:
        errors.append(
            f"KPI weights for {context} sum to {total_weight:.4f}; the maximum is 1.0"
        )
        return False, errors
    
    return True, errors


def _validate_thresholds(thresholds: Dict[str, int]) -> Tuple[bool, List[str]]:
    """
    Validate that grade thresholds are in descending order (A > B > C > D).
    
    Args:
        thresholds: Grade threshold dictionary
        
    Returns:
        Tuple of (is_valid, [error_messages])
    """
    errors = []
    required_grades = ['A', 'B', 'C', 'D']
    
    # Check all required grades present
    for grade in required_grades:
        if grade not in thresholds:
            errors.append(f"Missing grade threshold for '{grade}'")
    
    if errors:
        return False, errors
    
    # Check descending order
    grades_and_values = [(grade, thresholds[grade]) for grade in required_grades]
    for i in range(len(grades_and_values) - 1):
        current_grade, current_value = grades_and_values[i]
        next_grade, next_value = grades_and_values[i + 1]
        
        if current_value <= next_value:
            errors.append(
                f"Grade thresholds not in descending order: "
                f"{current_grade}({current_value}) should be > {next_grade}({next_value})"
            )
    
    return len(errors) == 0, errors


def _validate_required_fields(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that all required fields are present in configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, [error_messages])
    """
    errors = []
    required_top_level = ['team', 'db_name', 'region', 'employee_id_col', 'employee_name_col', 'grade_thresholds']
    
    for field in required_top_level:
        if field not in config:
            errors.append(f"Missing required field: '{field}'")
    
    if 'kpis' not in config and 'performance_levels' not in config:
        errors.append("Missing required field: 'kpis' or 'performance_levels'")

    required_kpi_fields = ['key', 'label', 'weight', 'direction', 'unit', 'color', 'actual_col', 'target_col']
    groups = [("Employee", config.get('kpis', []))]
    groups.extend((level, value.get('kpis', [])) for level, value in config.get('performance_levels', {}).items())
    for level, kpis in groups:
        for idx, kpi in enumerate(kpis):
            for field in required_kpi_fields:
                if field not in kpi:
                    errors.append(f"{level} KPI {idx} ({kpi.get('key', 'unknown')}): missing field '{field}'")
    
    return len(errors) == 0, errors


def validate_team_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a team configuration for correctness and consistency.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, [error_messages])
    """
    all_errors = []
    
    # Check required fields
    is_valid, errors = _validate_required_fields(config)
    all_errors.extend(errors)
    
    if not is_valid:
        # Can't continue validation without required fields
        return False, all_errors
    
    if config.get('kpis'):
        _, errors = _validate_weights(config['kpis'], "Employee")
        all_errors.extend(errors)

    for raw_level, level_config in config.get('performance_levels', {}).items():
        try:
            level = normalize_performance_level(raw_level)
        except ValueError as exc:
            all_errors.append(str(exc))
            continue
        _, errors = _validate_weights(level_config.get('kpis', []), level)
        all_errors.extend(errors)
    
    # Validate grade thresholds
    is_valid, errors = _validate_thresholds(config.get('grade_thresholds', {}))
    all_errors.extend(errors)
    
    return len(all_errors) == 0, all_errors


def resolve_team_config(config: Dict[str, Any], performance_level: str = "Employee") -> Dict[str, Any]:
    """Return one level's KPI config while treating legacy flat KPIs as Employee."""
    level = normalize_performance_level(performance_level)
    resolved = deepcopy(config)
    level_config = config.get("performance_levels", {}).get(level)
    if level_config:
        resolved.update(level_config)
    elif level != "Employee":
        raise ConfigurationError(f"No {level} KPI configuration for team {config.get('team', 'unknown')}")
    resolved["performance_level"] = level
    return resolved


def get_configured_performance_levels(config: Dict[str, Any]) -> List[str]:
    levels = {"Employee"} if config.get("kpis") else set()
    for raw_level, level_config in config.get("performance_levels", {}).items():
        if level_config.get("kpis"):
            levels.add(normalize_performance_level(raw_level))
    return [level for level in PERFORMANCE_LEVELS if level in levels]


def load_team_config(team_name: str) -> Dict[str, Any]:
    """
    Load a single team configuration by name.
    
    Validates the configuration and raises appropriate exceptions if validation fails.
    
    Args:
        team_name: Name of the team (e.g., "Pharmacy", "Coding", "CSR")
        
    Returns:
        Dict containing validated team config
        
    Raises:
        ConfigurationError: If config file not found or invalid
        WeightValidationError: If weights don't sum to 1.0
        ThresholdValidationError: If thresholds are invalid
    """
    config_dir = Path(__file__).parent / "teams"
    
    # Normalize team name to filename (snake_case)
    filename = team_name.lower().replace(" ", "_") + ".json"
    config_path = config_dir / filename
    
    if not config_path.exists():
        raise ConfigurationError(f"Team configuration not found: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in {config_path}: {e}")
    except IOError as e:
        raise ConfigurationError(f"Failed to read {config_path}: {e}")
    
    # Validate configuration
    is_valid, errors = validate_team_config(config)
    
    if not is_valid:
        # Categorize errors
        weight_errors = [e for e in errors if 'weight' in e.lower()]
        threshold_errors = [e for e in errors if 'threshold' in e.lower() or 'grade' in e.lower()]
        other_errors = [e for e in errors if e not in weight_errors and e not in threshold_errors]
        
        # Raise specific exception types
        if weight_errors:
            raise WeightValidationError(f"Weight validation failed for {team_name}:\n" + "\n".join(weight_errors))
        elif threshold_errors:
            raise ThresholdValidationError(f"Threshold validation failed for {team_name}:\n" + "\n".join(threshold_errors))
        else:
            raise ConfigurationError(f"Configuration validation failed for {team_name}:\n" + "\n".join(other_errors))
    
    logger.info(f"Successfully loaded and validated configuration for team: {team_name}")
    return config


def load_all_team_configs() -> List[Dict[str, Any]]:
    """
    Load all team configurations from the /config/teams/ directory.
    
    Returns:
        List of validated team config dictionaries
        
    Raises:
        ConfigurationError: If config directory doesn't exist or configs are invalid
    """
    config_dir = Path(__file__).parent / "teams"
    
    if not config_dir.exists():
        raise ConfigurationError(f"Config directory not found: {config_dir}")
    
    configs = []
    json_files = sorted(config_dir.glob("*.json"))
    
    if not json_files:
        logger.warning(f"No team configs found in {config_dir}")
        return configs
    
    for config_file in json_files:
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Validate before adding to list
            is_valid, errors = validate_team_config(config)
            if not is_valid:
                logger.error(f"Skipping invalid config {config_file.name}: {errors}")
                continue
            
            configs.append(config)
            logger.info(f"Loaded configuration: {config_file.name}")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config from {config_file.name}: {e}")
            continue
    
    return configs


def get_team_names() -> List[str]:
    """
    Get list of all available team names.
    
    Returns:
        List of team names (as they appear in the config files)
    """
    configs = load_all_team_configs()
    return [config['team'] for config in configs]


def find_team_config_by_db_name(db_name: str) -> Optional[Dict[str, Any]]:
    """
    Find a team config by database name.
    Useful when you have the database name but need to find the team config.
    
    Args:
        db_name: Database name (e.g., "Pharmacy", "Coding", "CSR")
        
    Returns:
        Team config dict, or None if not found
    """
    configs = load_all_team_configs()
    for config in configs:
        if config.get('db_name') == db_name:
            return config
    return None
