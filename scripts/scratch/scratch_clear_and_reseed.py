import os
import sys

# Add Backend folder to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Delete data files to force reseed
files_to_delete = [
    'data/performance_records.json',
    'data/employees.json',
    'data/targets.json',
    'data/kpi_weights.json'
]

for f in files_to_delete:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
    if os.path.exists(path):
        os.remove(path)
        print(f"Cleared {f}")

# Run seeding
from app import seed_database
seed_database()
print("✓ Database successfully cleared and reseeded with all teams, including Sales!")
