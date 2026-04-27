#!/bin/bash
# Outer restart loop: restarts supervisor.py if it exits for any reason
REPO="/home/user/microservice-srt"
TOTAL=349

log() { echo "[run.sh $(date '+%H:%M:%S')] $*"; }

log "=== run.sh started ==="

while true; do
    DONE=$(python3 -c "import json; d=json.load(open('$REPO/translation_progress.json')); print(len([v for v in d.values() if v!='ERROR']))" 2>/dev/null || echo 0)

    if [ "$DONE" -ge "$TOTAL" ]; then
        log "All $TOTAL files done! Exiting."
        exit 0
    fi

    log "Starting supervisor.py ($DONE/$TOTAL done)..."
    python3 -u "$REPO/supervisor.py" >> "$REPO/supervisor.log" 2>&1
    EXIT=$?
    log "supervisor.py exited (code=$EXIT). Restarting in 5s..."
    sleep 5
done
