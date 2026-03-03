#!/bin/bash
RF=~/dev/oss-radar/.stampede/run-20260303-145737/results/task-001.json
P=0; F=0
[ ! -f "$RF" ] && echo "FAIL: No results" && exit 1
S=$(python3 -c "import json; print(json.load(open('$RF')).get('summary',''))" 2>/dev/null)
[ -z "$S" ] && echo "FAIL: No summary" && exit 1; echo "PASS: exists"; ((P++))
echo "$S" | grep -iqE 'injection|sanitiz|validation' && { echo "PASS: injection keywords"; ((P++)); } || { echo "FAIL: missing injection keywords"; ((F++)); }
echo "$S" | grep -iqE 'severity|critical|high|medium|low' && { echo "PASS: severity"; ((P++)); } || { echo "FAIL: missing severity"; ((F++)); }
FLC=$(echo "$S" | grep -oE '[a-z_]+\.py:[0-9]+' | wc -l)
[ "$FLC" -ge 2 ] && { echo "PASS: $FLC file:line refs"; ((P++)); } || { echo "FAIL: only $FLC file:line refs"; ((F++)); }
echo "P=$P F=$F"; [ $F -eq 0 ]
