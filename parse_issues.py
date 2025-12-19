import codecs
import json
import sys

# Set stdout to utf-8
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")

data = json.load(open("D:\\AI\\coderabbit_comments.json", encoding="utf-8-sig"))

path_filter = sys.argv[1] if len(sys.argv) > 1 else None

for c in data:
    path = c["path"]
    if path_filter and path_filter not in path:
        continue
    print(f"=== {path}:{c.get('line', '?')} ===")
    body = c["body"]
    # Extract just the first part of the comment
    lines = body.split("\n")[:15]
    for line in lines:
        print(line)
    print()
