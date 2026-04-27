#!/bin/bash
# Watchdog: restart translate.py if it crashes, commit every BATCH files
REPO="/home/user/microservice-srt"
BRANCH="claude/translate-vietnamese-auto-retry-cBckl"
BATCH=20

log() { echo "[$(date '+%H:%M:%S')] $*"; }

commit_push() {
    git -C "$REPO" add -- '*.srt' translation_progress.json 2>/dev/null
    local count
    count=$(git -C "$REPO" diff --cached --name-only | grep -c '\.srt$' || echo 0)
    if [ "$count" -gt 0 ]; then
        local done
        done=$(cat "$REPO/translation_progress.json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d))" 2>/dev/null || echo "?")
        log "Committing $count files ($done/349 done)..."
        git -C "$REPO" commit -m "Translate $count SRT files to Vietnamese (progress: $done/349)

https://claude.ai/code/session_01KrZ5QHyC1i87HuE4MDrwaP"
        local attempt=0
        while [ $attempt -lt 4 ]; do
            git -C "$REPO" push -u origin "$BRANCH" 2>&1 && log "Pushed OK" && return
            attempt=$((attempt + 1))
            sleep $((2 ** attempt))
            log "Push retry $attempt..."
        done
    fi
}

log "=== Watchdog started ==="

while true; do
    # Check if done
    DONE=$(cat "$REPO/translation_progress.json" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len([v for v in d.values() if v != 'ERROR']))" 2>/dev/null || echo 0)
    if [ "$DONE" -ge 349 ]; then
        log "All 349 files done!"
        commit_push
        log "=== COMPLETE ==="
        exit 0
    fi

    # Start translate.py if not running
    if ! ps aux | grep "[t]ranslate.py" > /dev/null; then
        log "Starting translate.py ($DONE/349 done)..."
        python3 -u "$REPO/translate.py" >> "$REPO/translation.log" 2>&1 &
        TRANSLATE_PID=$!
        log "PID: $TRANSLATE_PID"
    fi

    # Commit every BATCH newly translated files
    CHANGED=$(git -C "$REPO" diff --name-only -- '*.srt' | wc -l)
    if [ "$CHANGED" -ge "$BATCH" ]; then
        commit_push
    fi

    sleep 45
done
