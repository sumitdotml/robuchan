#!/bin/sh
while true; do
  echo "$(date '+%H:%M:%S')  $(wc -l data/internal_master.jsonl 2>&1)"
  sleep 60
done
