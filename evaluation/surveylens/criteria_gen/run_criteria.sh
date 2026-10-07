#!/usr/bin/env bash
# Regenerate discipline criteria with the released (adapted) scripts: expand per survey, then merge.
cd "$(dirname "$0")"
d="$1"
python3 expand_aspects.py "$d" > "logs/expand_${d// /_}.log" 2>&1 && python3 merge_aspects.py "$d" > "logs/merge_${d// /_}.log" 2>&1
echo "$(date +%T) $d exit=$? expanded=$(ls "outputs/criteria/$d"/expanded_aspects_*.json 2>/dev/null | wc -l) merged=$(test -f "outputs/criteria/$d/merged_aspects.json" && echo y || echo n)"
