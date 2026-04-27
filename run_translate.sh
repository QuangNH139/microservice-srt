#!/bin/bash
# Watchdog: runs translation, auto-commits every batch, restarts on crash
REPO=/home/user/microservice-srt
BRANCH=claude/translate-srt-vietnamese-mtmBC
INITIAL_COMMIT=810b301
LOG=/tmp/translate_watchdog.log

cd "$REPO"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

rebuild_skip() {
    git diff "$INITIAL_COMMIT"..HEAD --name-only | grep '\.srt$' > /tmp/translated.txt
    wc -l < /tmp/translated.txt
}

commit_push() {
    git add -u 2>/dev/null || true
    local changed
    changed=$(git diff --cached --name-only | grep -c '\.srt$' || true)
    if [ "$changed" -gt 0 ]; then
        local done
        done=$(git diff "$INITIAL_COMMIT"..HEAD --name-only | grep -c '\.srt$' || true)
        log "Committing $changed new files ($done/349 done)..."
        git commit -m "Translate SRT files to Vietnamese (progress: $done/349)

https://claude.ai/code/session_01E3YqtDxq6d2R7rNeL99Lis" >> "$LOG" 2>&1
        local attempt=0
        while [ $attempt -lt 4 ]; do
            git push -u origin "$BRANCH" >> "$LOG" 2>&1 && log "Pushed OK" && break
            attempt=$((attempt + 1))
            sleep $((2 ** attempt))
            log "Push retry $attempt..."
        done
    fi
}

log "=== Translation watchdog started ==="

while true; do
    done=$(rebuild_skip)
    total=349
    remaining=$((total - done))

    if [ "$remaining" -le 0 ]; then
        log "All $total files done! Final commit..."
        commit_push
        log "=== COMPLETE ==="
        exit 0
    fi

    log "Running: $remaining files remaining ($done/$total done)"

    python3 -u translate.py /tmp/translated.txt >> "$LOG" 2>&1 || true

    log "Translation process exited. Committing progress..."
    commit_push

    # Small pause before restart
    sleep 3
done
