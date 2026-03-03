#!/bin/bash
RF=~/dev/oss-radar/.stampede/run-20260303-145737/results/task-002.json
P=0; F=0
[ ! -f "$RF" ] && echo "FAIL: No results" && exit 1
S=$(python3 -c "import json; print(json.load(open('$RF')).get('summary',''))" 2>/dev/null)
[ -z "$S" ] && echo "FAIL: No summary" && exit 1; echo "PASS: exists"; ((P++))
echo "$S" | grep -iqE 'TLS|STARTTLS' && { echo "PASS: TLS"; ((P++)); } || { echo "FAIL: no TLS"; ((F++)); }
echo "$S" | grep -iqE 'credential|password' && { echo "PASS: credentials"; ((P++)); } || { echo "FAIL: no credentials"; ((F++)); }
echo "$S" | grep -iqE 'radar/email|sender\.py|mailer\.py' && { echo "PASS: email files"; ((P++)); } || { echo "FAIL: no email files"; ((F++)); }
echo "P=$P F=$F"; [ $F -eq 0 ]
