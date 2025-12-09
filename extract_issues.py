import json
import sys
import codecs

sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')

data = json.load(open('D:\\AI\\coderabbit_comments.json', encoding='utf-8-sig'))

# Files we've already fixed
fixed_files = [
    'settings.json', 'settings.local.json', 'coderabbit.yaml',
    'coderabbit-autofix.yml', 'ClaudePanel.tsx', 'ModelsPage.tsx',
    'useModels.ts', 'useSocket.ts'
]

# Categorize by severity
potential_issues = []
nitpicks = []

for c in data:
    path = c['path']
    body = c['body']
    line = c.get('line', '?')

    # Skip already fixed files
    if any(f in path for f in fixed_files):
        continue

    # Categorize
    if 'Potential issue' in body or '_Major_' in body:
        potential_issues.append({'path': path, 'line': line, 'body': body})
    else:
        nitpicks.append({'path': path, 'line': line, 'body': body})

print(f"=== POTENTIAL ISSUES ({len(potential_issues)}) ===\n")
for issue in potential_issues:
    print(f"FILE: {issue['path']}:{issue['line']}")
    # Print first meaningful lines
    lines = issue['body'].split('\n')
    for i, line in enumerate(lines[:8]):
        if line.strip():
            print(f"  {line[:120]}")
    print()

print(f"\n=== NITPICKS ({len(nitpicks)}) ===\n")
for issue in nitpicks[:20]:  # Limit to first 20
    print(f"FILE: {issue['path']}:{issue['line']}")
    lines = issue['body'].split('\n')
    for i, line in enumerate(lines[:3]):
        if line.strip():
            print(f"  {line[:120]}")
    print()
