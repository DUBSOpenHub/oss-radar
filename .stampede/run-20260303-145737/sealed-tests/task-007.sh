#!/bin/bash
RF=~/dev/oss-radar/.stampede/run-20260303-145737/results/task-007.json
P=0; F=0
[ ! -f "$RF" ] && echo "FAIL: No results" && exit 1
S=$(python3 -c "import json; print(json.load(open('$RF')).get('summary',''))" 2>/dev/null)
[ -z "$S" ] && echo "FAIL: No summary" && exit 1; echo "PASS: exists"; ((P++))
echo "$S" | grep -iqE 'prompt.injection|prompt.inject' && { echo "PASS: prompt injection"; ((P++)); } || { echo "FAIL: no prompt injection"; ((F++)); }
echo "$S" | grep -iqE 'subprocess|command.injection|shell' && { echo "PASS: subprocess"; ((P++)); } || { echo "FAIL: no subprocess"; ((F++)); }
echo "P=$P F=$F"; [ $F -eq 0 ]
