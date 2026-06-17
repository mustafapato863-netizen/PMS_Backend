import json

with open("data/performance_records.json", "r", encoding="utf-8") as f:
    records = json.load(f)

months = set()
for r in records:
    months.add(r.get("month"))

print("Unique months in performance_records.json:", months)

# Print count per month
from collections import Counter
counts = Counter(r.get("month") for r in records)
print("Count per month:", counts)
