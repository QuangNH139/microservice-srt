#!/bin/bash
# Auto-commit and push translated SRT files every BATCH_COUNT files
REPO="/home/user/microservice-srt"
BRANCH="claude/translate-vietnamese-auto-retry-cBckl"
BATCH_COUNT=15

log() { echo "[$(date '+%H:%M:%S')] $*"; }

while ps aux | grep "[t]ranslate.py" > /dev/null; do
    CHANGED=$(git -C "$REPO" diff --name-only -- '*.srt' | wc -l)

    if [ "$CHANGED" -ge "$BATCH_COUNT" ]; then
        log "Committing $CHANGED translated SRT files..."
        git -C "$REPO" add -- '*.srt' translation_progress.json 2>/dev/null
        COUNT=$(git -C "$REPO" diff --cached --name-only | grep '\.srt$' | wc -l)
        if [ "$COUNT" -gt 0 ]; then
            DONE=$(git -C "$REPO" diff --cached --name-only | grep -c '\.srt$' || echo 0)
            git -C "$REPO" commit -m "Translate $COUNT SRT files to Vietnamese (in-place)

https://claude.ai/code/session_01KrZ5QHyC1i87HuE4MDrwaP"

            attempt=0
            while [ $attempt -lt 4 ]; do
                git -C "$REPO" push -u origin "$BRANCH" >> /tmp/auto_commit_push.log 2>&1 && log "Pushed OK" && break
                attempt=$((attempt + 1))
                sleep $((2 ** attempt))
                log "Push retry $attempt..."
            done
        fi
    fi

    sleep 30
done

# Final commit after translation finishes
log "Translation done. Final commit..."
git -C "$REPO" add -- '*.srt' translation_progress.json 2>/dev/null
COUNT=$(git -C "$REPO" diff --cached --name-only | grep '\.srt$' | wc -l)
if [ "$COUNT" -gt 0 ]; then
    git -C "$REPO" commit -m "Final batch: $COUNT SRT files translated to Vietnamese

https://claude.ai/code/session_01KrZ5QHyC1i87HuE4MDrwaP"
    attempt=0
    while [ $attempt -lt 4 ]; do
        git -C "$REPO" push -u origin "$BRANCH" >> /tmp/auto_commit_push.log 2>&1 && log "Final push OK" && break
        attempt=$((attempt + 1))
        sleep $((2 ** attempt))
        log "Push retry $attempt..."
    done
fi
log "=== AUTO-COMMIT COMPLETE ==="
