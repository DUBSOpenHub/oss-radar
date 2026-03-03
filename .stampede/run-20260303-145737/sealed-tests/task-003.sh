#!/bin/bash
RF=~/dev/oss-radar/.stampede/run-20260303-145737/results/task-003.json
P=0; F=0
[ ! -f "$RF" ] && echo "FAIL: No results" && exit 1
S=$(python3 -c "import json; print(json.load(open('$RF')).get('summary',''))" 2>/dev/null)
[ -z "$S" ] && echo "FAIL: No summary" && exit 1; echo "PASS: exists"; ((P++))
echo "$S" | grep -iqE 'SQL injection|parameterized' && { echo "PASS: SQL injection"; ((P++)); } || { echo "FAIL: no SQL injection"; ((F++)); }
echo "$S" | grep -iqE 'radar/db\.py|radar/storage|database\.py' && { echo "PASS: db files"; ((P++)); } || { echo "FAIL: no db files"; ((F++)); }
echo "P=$P F=$F"; [ $F -eq 0 ]
