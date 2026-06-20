"""
Team configuration loader.
Discovers and loads team configurations from /config/teams/*.json files.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

def load_team_config(team_name: str) -> Optional[Dict[str, Any]]:
    """
    Load a single team configuration by name.
    
    Args:
        team_name: Name of the team (e.g., "inbound", "sales")
        
    Returns:
        Dict containing team config, or None if not found
    """
    config_dir = Path(__file__).parent / "teams"
    
    # Normalize team name to filename (snake_case)
    filename = team_name.lower().replace(" ", "_") + ".json"
    config_path = config_dir / filename
    
    if not config_path.exists():
        return None
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config
    except (json.JSONDecodeError, IOError) as e:
        raise ValueError(f"Failed to load team config from {config_path}: {e}")


def load_all_team_configs() -> List[Dict[str, Any]]:
    """
    Load all team configurations from the /config/teams/ directory.
    
    Returns:
        List of team config dictionaries
        
    Raises:
        ValueError: If config directory doesn't exist or configs are invalid
    """
    config_dir = Path(__file__).parent / "teams"
    
    if not config_dir.exists():
        raise ValueError(f"Config directory not found: {config_dir}")
    
    configs = []
    json_files = sorted(config_dir.glob("*.json"))
    
    if not json_files:
        raise ValueError(f"No team configs found in {config_dir}")
    
    for config_file in json_files:
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            # Basic validation: must have 'team' and 'kpis' keys
            if 'team' not in config or 'kpis' not in config:
                raise ValueError(f"Invalid config: missing 'team' or 'kpis' key in {config_file.name}")
            configs.append(config)
        except (json.JSONDecodeError, IOError) as e:
            raise ValueError(f"Failed to load config from {config_file.name}: {e}")
    
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
        db_name: Database name (e.g., "Inbound", "Sales")
        
    Returns:
        Team config dict, or None if not found
    """
    configs = load_all_team_configs()
    for config in configs:
        if config.get('db_name') == db_name:
            return config
    return None
