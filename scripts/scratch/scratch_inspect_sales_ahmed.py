import json

with open('data/performance_records.json', 'r') as f:
    data = json.load(f)

ahmed_records = [r for r in data if r['employee_id'] == 'SGHA01398']
print(f"Found {len(ahmed_records)} records for Ahmed Tarek:")
for r in ahmed_records:
    print(f"\nMonth: {r['month']}")
    print(f"  Score: {r['evaluation']['score']}")
    print(f"  Grade: {r['evaluation']['grade']}")
    print(f"  Suggested Action: {r['evaluation']['suggested_action']}")
    print(f"  Planning Category: {r['evaluation'].get('planning_category')}")
    print(f"  Achievements:")
    for kpi, ach in r['achievement'].items():
        print(f"    {kpi}: {ach}")


