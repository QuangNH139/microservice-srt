#!/bin/bash
# Watchdog: runs translation, auto-commits every 20 files, restarts on crash
set -euo pipefail

REPO=/home/user/microservice-srt
BRANCH=claude/translate-srt-vietnamese-mtmBC
INITIAL_COMMIT=810b301
LOG=/tmp/translate_watchdog.log
COMMIT_EVERY=20

cd "$REPO"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

rebuild_skip_list() {
    git diff "$INITIAL_COMMIT"..HEAD --name-only | grep '\.srt$' > /tmp/translated.txt
    local done
    done=$(wc -l < /tmp/translated.txt)
    log "Already done: $done/349"
}

commit_and_push() {
    local changed
    changed=$(git status --short | grep -c '^ M' || true)
    if [ "$changed" -gt 0 ]; then
        local done
        done=$(git diff "$INITIAL_COMMIT"..HEAD --name-only | grep -c '\.srt$' || true)
        log "Committing $changed files ($done/349 total)..."
        git add -u
        git commit -m "Translate SRT files to Vietnamese (progress: $done/349)

https://claude.ai/code/session_01E3YqtDxq6d2R7rNeL99Lis"
        git push -u origin "$BRANCH" && log "Pushed OK" || {
            log "Push failed, retrying in 2s..."
            sleep 2
            git push -u origin "$BRANCH" && log "Pushed OK (retry 1)" || {
                sleep 4
                git push -u origin "$BRANCH" && log "Pushed OK (retry 2)" || log "Push failed after 3 tries"
            }
        }
    fi
}

log "=== Translation watchdog started ==="

while true; do
    rebuild_skip_list
    remaining=$(python3 -c "
from pathlib import Path
skip = set(l.strip() for l in open('/tmp/translated.txt'))
total = sorted(Path('$REPO').rglob('*.srt'))
remaining = [f for f in total if str(f.relative_to('$REPO')) not in skip]
print(len(remaining))
" 2>/dev/null || echo 0)

    if [ "$remaining" -eq 0 ]; then
        log "All 349 files translated! Doing final commit..."
        commit_and_push
        log "=== DONE ==="
        break
    fi

    log "Starting translation of $remaining remaining files..."

    # Run translation, capturing output and monitoring for commits
    python3 -u translate.py /tmp/translated.txt 2>&1 | while IFS= read -r line; do
        echo "$line" | tee -a "$LOG"
        # Commit every COMMIT_EVERY completions
        count=$(grep -c "✓" "$LOG" 2>/dev/null || echo 0)
        if [ $(( count % COMMIT_EVERY )) -eq 0 ] && [ "$count" -gt 0 ]; then
            commit_and_push 2>>"$LOG" || true
            rebuild_skip_list 2>>"$LOG" || true
        fi
    done || true

    log "Translation process ended. Checking for uncommitted work..."
    commit_and_push || true

    # Check if still files remain
    rebuild_skip_list
    remaining=$(python3 -c "
from pathlib import Path
skip = set(l.strip() for l in open('/tmp/translated.txt'))
total = sorted(Path('$REPO').rglob('*.srt'))
remaining = [f for f in total if str(f.relative_to('$REPO')) not in skip]
print(len(remaining))
" 2>/dev/null || echo 0)

    if [ "$remaining" -gt 0 ]; then
        log "Restarting... ($remaining files left)"
        sleep 2
    fi
done
