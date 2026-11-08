#!/bin/bash
# Convert one file through a running server, as the upload form does, and download the results.
# usage: scripts/try_server.sh <server url> <pdf or image> <out dir>
#   scripts/try_server.sh https://readablemusic-production.up.railway.app score.pdf out/
#   scripts/try_server.sh http://127.0.0.1:8000 score.pdf out/
# Each run counts toward the server's 10 conversions an hour from one address.
base=${1%/}; input=$2; out=$3
mkdir -p "$out"
start=$(date +%s)
resp=$(curl -sS -o "$out/post-body.txt" -w '%{http_code} %{redirect_url}' -F "files=@$input" "$base/jobs")
echo "POST /jobs -> $resp"
loc=${resp#* }; job=${loc##*/}
[ -z "$job" ] && { cat "$out/post-body.txt"; exit 1; }
last=""
while :; do
  body=$(curl -sS "$base/api/jobs/$job")
  [ "$body" != "$last" ] && { echo "$(( $(date +%s) - start ))s $body"; last=$body; }
  case "$body" in *'"done"'*|*'"failed"'*) break;; esac
  [ $(( $(date +%s) - start )) -gt 1800 ] && { echo timeout; exit 1; }
  sleep 5
done
for ext in musicxml pdf; do
  curl -sS -o "$out/score.$ext" -w "score.$ext %{http_code} %{size_download} bytes\n" "$base/jobs/$job/score.$ext"
done
echo "$job" > "$out/job.txt"
rm -f "$out/post-body.txt"
