import json

with open(r'C:\Users\seatr\.gemini\antigravity\brain\640ae6a7-e6d5-40f0-8a7c-f97f614e138f\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        si = data.get('step_index', 0)
        if 10741 <= si <= 10760:
            if data.get('source') == 'MODEL' and data.get('content'):
                print(f"=== Step {si} ===")
                print(data.get('content')[:1200])
                print("\n" + "="*40 + "\n")
