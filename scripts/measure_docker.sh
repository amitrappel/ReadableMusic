#!/bin/bash
# Time each file in a fresh container with Railway's limits, and record its memory use.
# usage: scripts/measure_docker.sh <image> <cpus> <memory> <file> ...
#   docker build -t readablemusic . && scripts/measure_docker.sh readablemusic 2 4g score.pdf
# This produced the sizing table in docs/deployment.md.
image=$1; cpus=$2; mem=$3; shift 3
port=8765
# Git Bash rewrites paths like /sys/... in arguments; docker must get them as they are,
# while curl needs them rewritten to read local files.
dk() { MSYS_NO_PATHCONV=1 docker "$@"; }
for input in "$@"; do
  dk rm -f rm-measure >/dev/null 2>&1
  dk run -d --name rm-measure --cpus="$cpus" --memory="$mem" --memory-swap="$mem" -p $port:8000 "$image" >/dev/null
  for i in $(seq 60); do curl -fs -o /dev/null "http://127.0.0.1:$port/" && break; sleep 1; done
  idle=$(dk exec rm-measure cat /sys/fs/cgroup/memory.current)
  start=$(date +%s)
  loc=$(curl -s -o /dev/null -w '%{redirect_url}' -F "files=@$input" "http://127.0.0.1:$port/jobs")
  job=${loc##*/}
  while :; do
    body=$(curl -s "http://127.0.0.1:$port/api/jobs/$job")
    case "$body" in *'"done"'*|*'"failed"'*) break;; "") body=server-gone; break;; esac
    [ $(( $(date +%s) - start )) -gt 1800 ] && { body=timeout; break; }
    sleep 3
  done
  secs=$(( $(date +%s) - start ))
  peak=$(dk exec rm-measure cat /sys/fs/cgroup/memory.peak 2>/dev/null)
  after=$(dk exec rm-measure cat /sys/fs/cgroup/memory.current 2>/dev/null)
  oom=$(dk inspect rm-measure --format '{{.State.OOMKilled}}')
  printf '%-34s cpus=%s mem=%s %ss idle=%sMB peak=%sMB after=%sMB oom=%s %s\n' \
    "$(basename "$input" | cut -c1-34)" "$cpus" "$mem" "$secs" \
    "$(( ${idle:-0} / 1048576 ))" "$(( ${peak:-0} / 1048576 ))" "$(( ${after:-0} / 1048576 ))" "$oom" "$body"
done
dk rm -f rm-measure >/dev/null 2>&1
