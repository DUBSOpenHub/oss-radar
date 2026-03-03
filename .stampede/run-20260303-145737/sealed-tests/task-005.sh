#!/bin/bash
RF=~/dev/oss-radar/.stampede/run-20260303-145737/results/task-005.json
P=0; F=0
[ ! -f "$RF" ] && echo "FAIL: No results" && exit 1
S=$(python3 -c "import json; print(json.load(open('$RF')).get('summary',''))" 2>/dev/null)
[ -z "$S" ] && echo "FAIL: No summary" && exit 1; echo "PASS: exists"; ((P++))
echo "$S" | grep -iqE 'requests|beautifulsoup|lxml|vaderSentiment|textblob|typer|jinja|praw' && { echo "PASS: packages"; ((P++)); } || { echo "FAIL: no packages"; ((F++)); }
echo "$S" | grep -iqE 'pin|version' && { echo "PASS: pinning"; ((P++)); } || { echo "FAIL: no pinning"; ((F++)); }
echo "P=$P F=$F"; [ $F -eq 0 ]
