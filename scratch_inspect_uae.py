import json

with open("FrontEnd/src/data/all_months_performance.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for i, r in enumerate(data):
    identity = r.get("identity", {})
    if "team" in identity:
        print(f"Record {i} has team: {identity['team']}")
    else:
        print(f"Record {i} does NOT have team. Name: {identity.get('name')}, Month: {identity.get('month')}")
