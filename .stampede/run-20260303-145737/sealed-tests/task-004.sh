#!/bin/bash
RF=~/dev/oss-radar/.stampede/run-20260303-145737/results/task-004.json
P=0; F=0
[ ! -f "$RF" ] && echo "FAIL: No results" && exit 1
S=$(python3 -c "import json; print(json.load(open('$RF')).get('summary',''))" 2>/dev/null)
[ -z "$S" ] && echo "FAIL: No summary" && exit 1; echo "PASS: exists"; ((P++))
echo "$S" | grep -iqE '\.env' && { echo "PASS: .env"; ((P++)); } || { echo "FAIL: no .env"; ((F++)); }
echo "$S" | grep -iqE 'hardcoded' && { echo "PASS: hardcoded"; ((P++)); } || { echo "FAIL: no hardcoded"; ((F++)); }
echo "$S" | grep -iqE 'gitignore' && { echo "PASS: gitignore"; ((P++)); } || { echo "FAIL: no gitignore"; ((F++)); }
echo "P=$P F=$F"; [ $F -eq 0 ]
