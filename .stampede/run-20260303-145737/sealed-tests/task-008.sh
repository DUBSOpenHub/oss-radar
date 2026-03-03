#!/bin/bash
RF=~/dev/oss-radar/.stampede/run-20260303-145737/results/task-008.json
P=0; F=0
[ ! -f "$RF" ] && echo "FAIL: No results" && exit 1
S=$(python3 -c "import json; print(json.load(open('$RF')).get('summary',''))" 2>/dev/null)
[ -z "$S" ] && echo "FAIL: No summary" && exit 1; echo "PASS: exists"; ((P++))
echo "$S" | grep -iqE 'workflow.permission|permission' && { echo "PASS: permissions"; ((P++)); } || { echo "FAIL: no permissions"; ((F++)); }
echo "$S" | grep -iqE 'pin|SHA|tag|hash' && { echo "PASS: action pinning"; ((P++)); } || { echo "FAIL: no action pinning"; ((F++)); }
echo "P=$P F=$F"; [ $F -eq 0 ]
