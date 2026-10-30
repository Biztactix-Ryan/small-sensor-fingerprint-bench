#!/bin/bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Watchdog for queued big_eval runs: prints queue lines (start/done), errors in
# logs, stalls (>15 min without log output) and a dead queue, plus a heartbeat
# after ~29 min, then exits so it can be re-armed.
# Usage: bench_watch.sh QUEUE_OUTPUT_FILE "FINAL_DONE_LINE" LOG_GLOB
OUT=$1
FINAL=$2
LOGS=$3
cd "$(dirname "$0")/.." || exit 1
start=$(date +%s)
seen=$(wc -l < "$OUT")
errs=""
while true; do
  now=$(date +%s)
  n=$(wc -l < "$OUT")
  if [ "$n" -gt "$seen" ]; then sed -n "$((seen + 1)),${n}p" "$OUT"; seen=$n; fi
  for f in $LOGS; do
    [ -f "$f" ] || continue
    if ! echo "$errs" | grep -qF "$f" &&
       grep -qE "Traceback|Error|Killed|Segmentation|core dumped|MemoryError" "$f"; then
      echo "ERROR in $f: $(grep -E 'Traceback|Error|Killed|Segmentation|core dumped|MemoryError' "$f" | tail -1)"
      errs="$errs $f"
    fi
  done
  if grep -qF "$FINAL" "$OUT"; then echo "ALL DONE"; exit 0; fi
  latest=$(ls -t $LOGS 2>/dev/null | head -1)
  running=$(pgrep -f "big_eval.py" | wc -l)
  waiting=$(pgrep -f "until grep -q" | wc -l)
  if [ "$running" -eq 0 ] && [ "$waiting" -eq 0 ]; then
    echo "DEAD: no big_eval process and no queue waiting; last log $latest: $(tail -1 "$latest" 2>/dev/null)"
    exit 1
  fi
  if [ -n "$latest" ] && [ "$running" -gt 0 ]; then
    age=$((now - $(stat -c %Y "$latest")))
    if [ "$age" -gt 900 ]; then echo "STALL: $latest unchanged for $((age / 60)) min: $(tail -1 "$latest")"; fi
  fi
  if [ $((now - start)) -gt 1740 ]; then
    echo "HEARTBEAT $(date +%T): $(basename "${latest:-none}" .log) -> $(tail -1 "$latest" 2>/dev/null | sed 's/^ *//'); load $(cut -d' ' -f1 /proc/loadavg), mem avail $(free -g | awk '/Mem/{print $7}')G"
    exit 0
  fi
  sleep 30
done
