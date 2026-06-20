"""
Data Cleaner Factory
Dynamically loads and instantiates team-specific cleaners.
Provides a single interface to get the right cleaner for any team.
"""

import sys
import os
from typing import Optional, Dict, Type
from importlib import import_module
from data_cleaning.base_cleaner import BaseDataCleaner


class CleanerFactory:
    """
    Factory for creating team-specific data cleaners.
    
    Usage:
        cleaner = CleanerFactory.get_cleaner('inbound')
        cleaned_data = cleaner.clean(df)
        report = cleaner.get_report()
    """

    _cache: Dict[str, Type[BaseDataCleaner]] = {}
    _loaded = False

    @classmethod
    def get_cleaner(cls, team_name: str) -> BaseDataCleaner:
        """
        Get cleaner instance for team.
        
        Args:
            team_name: Team name (e.g., 'inbound', 'outbound')
            
        Returns:
            Instantiated cleaner
            
        Raises:
            ValueError: If cleaner not found
        """
        team_name_lower = team_name.lower().replace(' ', '_')
        
        # Load all cleaners if not loaded
        if not cls._loaded:
            cls._load_all_cleaners()
        
        # Look for cleaner (case-insensitive)
        cleaner_class = None
        for key, cls_ref in cls._cache.items():
            if key.lower().replace(' ', '_') == team_name_lower:
                cleaner_class = cls_ref
                break
        
        if cleaner_class is None:
            raise ValueError(f"No cleaner found for team: {team_name}")
        
        return cleaner_class()

    @classmethod
    def _load_all_cleaners(cls) -> None:
        """
        Dynamically load all cleaners from Data_Cleaning_Teams directory.
        """
        # Get path to Data_Cleaning_Teams directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cleaners_dir = os.path.join(backend_dir, 'Data_Cleaning_Teams')
        
        if not os.path.exists(cleaners_dir):
            raise RuntimeError(f"Cleaners directory not found: {cleaners_dir}")
        
        # Add directory to path if not already there
        if cleaners_dir not in sys.path:
            sys.path.insert(0, cleaners_dir)
        
        # Expected cleaner modules and their class names
        cleaner_modules = {
            'inbound': 'InboundCleaner',
            'outbound': 'OutboundCleaner',
            'inbound_UAE': 'InboundUAECleaner',
            'pre_approvals_offshore': 'PreApprovalsOffshoreCleaner',
            'sales': 'SalesCleaner',
            'pharmacy': 'PharmacyCleaner',
        }
        
        for module_name, class_name in cleaner_modules.items():
            try:
                # Try to import module
                try:
                    module = import_module(module_name)
                except ImportError:
                    # Try from Data_Cleaning_Teams subdirectory
                    sys.path.insert(0, cleaners_dir)
                    module = __import__(module_name)
                
                # Get class from module
                if hasattr(module, class_name):
                    cleaner_class = getattr(module, class_name)
                    
                    # Verify it's a BaseDataCleaner subclass
                    if issubclass(cleaner_class, BaseDataCleaner):
                        cls._cache[module_name] = cleaner_class
                        print(f"Loaded cleaner: {module_name} → {class_name}")
                else:
                    print(f"Warning: Class {class_name} not found in {module_name}")
            
            except ImportError as e:
                print(f"Warning: Could not load cleaner {module_name}: {e}")
            except Exception as e:
                print(f"Error loading cleaner {module_name}: {e}")
        
        cls._loaded = True

    @classmethod
    def get_available_teams(cls) -> list:
        """
        Get list of available team cleaners.
        
        Returns:
            List of team names
        """
        if not cls._loaded:
            cls._load_all_cleaners()
        
        return list(cls._cache.keys())

    @classmethod
    def reset(cls) -> None:
        """Reset factory (useful for testing)."""
        cls._cache.clear()
        cls._loaded = False

    @classmethod
    def register_cleaner(cls, team_name: str, cleaner_class: Type[BaseDataCleaner]) -> None:
        """
        Manually register a cleaner (useful for testing or custom teams).
        
        Args:
            team_name: Team identifier
            cleaner_class: Cleaner class (must inherit from BaseDataCleaner)
        """
        if not issubclass(cleaner_class, BaseDataCleaner):
            raise TypeError(f"{cleaner_class} must inherit from BaseDataCleaner")
        
        cls._cache[team_name] = cleaner_class


# Convenience function
def get_cleaner(team_name: str) -> BaseDataCleaner:
    """
    Get cleaner for team (convenience function).
    
    Args:
        team_name: Team name
        
    Returns:
        Cleaner instance
    """
    return CleanerFactory.get_cleaner(team_name)


def get_available_teams() -> list:
    """Get list of available teams (convenience function)."""
    return CleanerFactory.get_available_teams()
