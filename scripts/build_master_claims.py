import re
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

files = [
    ('README.md', 'README.md'),
    ('ARCHITECTURE.md', 'docs/ARCHITECTURE.md'),
    ('TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md', 'docs/specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md'),
    ('DECISIONS.md', 'docs/DECISIONS.md')
]

status_keywords = [
    'Verified', 'VERIFIED',
    'Enforced', 'ENFORCED',
    'Implemented & Measured', 'IMPLEMENTED & MEASURED',
    'Implemented & Unit Tested', 'IMPLEMENTED & UNIT TESTED',
    'PASS', 'Passed', 'PASSED',
    'Target', 'Queued', 'QUEUED',
    'Ratified & Enforced', 'Ratified & Measured', 'Ratified',
    'Completed & Superseded', 'Enforced Invariant'
]
# Word boundary check
pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in status_keywords) + r')\b', re.IGNORECASE)

master_list = []

for doc_name, file_path in files:
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line_no, line in enumerate(lines, 1):
        line_clean = line.strip()
        # skip markdown table separators or table headers
        if '---' in line_clean:
            continue
        if '|' in line_clean and any(h in line_clean for h in ['Performance Dimension', 'Stage | Description', 'Spec / Decision', 'Capability / Milestone', 'Hardware Hardware', 'Option / Path', 'Status / Empirical Verdict']):
            continue
        
        # Check table row
        if '|' in line_clean:
            cells = [c.strip() for c in line_clean.split('|')[1:-1]]
            if len(cells) >= 2:
                # Find if any cell matches status
                found_match = False
                for cell_idx, cell in enumerate(cells):
                    m = pattern.search(cell)
                    if m:
                        # Clean markdown bolding
                        clean_cell = cell.replace('**', '').strip()
                        claim_col = cells[0].replace('**', '').strip()
                        if cell_idx == 0 and len(cells) > 1:
                            claim_col = cells[1].replace('**', '').strip()
                        
                        master_list.append({
                            'doc': doc_name,
                            'line': line_no,
                            'claim': claim_col,
                            'raw_line': line_clean,
                            'status': clean_cell
                        })
                        found_match = True
                        break
        elif line_clean.startswith('- **Status:**') or line_clean.startswith('**Status:**'):
            cur = line_no - 1
            heading = ''
            while cur > 0:
                prev = lines[cur - 1].strip()
                if prev.startswith('### ') or prev.startswith('## '):
                    heading = prev.lstrip('#').strip()
                    break
                cur -= 1
            raw_status = line_clean.replace('**Status:**', '').replace('- ', '').strip()
            master_list.append({
                'doc': doc_name,
                'line': line_no,
                'claim': heading if heading else 'Document Metadata',
                'raw_line': line_clean,
                'status': raw_status
            })

print(f"TOTAL CLAIMS FOUND: {len(master_list)}")
with open('data/master_claims_list.json', 'w', encoding='utf-8') as out_f:
    json.dump(master_list, out_f, indent=2)

for idx, item in enumerate(master_list, 1):
    print(f"[{idx:03d}] | {item['doc']} | Line {item['line']} | {item['claim']} | {item['status']}")
