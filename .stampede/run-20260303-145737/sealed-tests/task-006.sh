#!/bin/bash
RF=~/dev/oss-radar/.stampede/run-20260303-145737/results/task-006.json
P=0; F=0
[ ! -f "$RF" ] && echo "FAIL: No results" && exit 1
S=$(python3 -c "import json; print(json.load(open('$RF')).get('summary',''))" 2>/dev/null)
[ -z "$S" ] && echo "FAIL: No summary" && exit 1; echo "PASS: exists"; ((P++))
echo "$S" | grep -iqE 'SSL|TLS|verify|certificate' && { echo "PASS: SSL/TLS"; ((P++)); } || { echo "FAIL: no SSL/TLS"; ((F++)); }
echo "$S" | grep -iqE 'timeout|rate.limit' && { echo "PASS: timeout/rate"; ((P++)); } || { echo "FAIL: no timeout/rate"; ((F++)); }
echo "P=$P F=$F"; [ $F -eq 0 ]
