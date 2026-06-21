import json

with open("data/performance_records.json", "r") as f:
    records = json.load(f)

print(f"Total performance records: {len(records)}")

team_counts = {}
for r in records:
    team = r.get("team")
    team_counts[team] = team_counts.get(team, 0) + 1

print("\nRecords per team:")
for team, count in team_counts.items():
    print(f"- {team}: {count}")

# Print first 2 records of Coding, CSR, and Pharmacy to verify their scores, actual, and achievement structures
for target_team in ["Coding", "CSR", "Pharmacy"]:
    team_recs = [r for r in records if r.get("team") == target_team]
    print(f"\n--- Previewing {target_team} (Total: {len(team_recs)}) ---")
    if team_recs:
        for idx in range(min(2, len(team_recs))):
            rec = team_recs[idx]
            print(f"Employee: {rec.get('employee_name')} ({rec.get('employee_id')})")
            print(f"Month: {rec.get('month')}, Score: {rec.get('evaluation', {}).get('score')}, Grade: {rec.get('evaluation', {}).get('grade')}")
            print(f"Actual metrics: {rec.get('actual')}")
            print(f"Achievements: {rec.get('achievement')}")
            print("---")
