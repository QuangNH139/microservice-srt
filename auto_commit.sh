#!/bin/bash
# Auto-commit and push translated _vi.srt files every 20 newly translated files
REPO="/home/user/microservice-srt"
BATCH=20
LAST_COMMITTED=0

while ps aux | grep "[t]ranslate.py" > /dev/null; do
    NEW_FILES=$(git -C "$REPO" ls-files --others --exclude-standard -- '**/*_vi.srt' | wc -l)

    if [ "$NEW_FILES" -ge "$BATCH" ]; then
        echo "[auto_commit] $(date): Committing $NEW_FILES new translated files..."
        git -C "$REPO" add -- '**/*_vi.srt' translation_progress.json 2>/dev/null
        git -C "$REPO" add -- '*_vi.srt' translation_progress.json 2>/dev/null
        COUNT=$(git -C "$REPO" diff --cached --name-only | grep '_vi\.srt' | wc -l)
        if [ "$COUNT" -gt 0 ]; then
            git -C "$REPO" commit -m "Add $COUNT Vietnamese translated SRT files (auto-batch)

https://claude.ai/code/session_01KrZ5QHyC1i87HuE4MDrwaP"
            git -C "$REPO" push origin claude/translate-vietnamese-auto-retry-cBckl 2>&1
        fi
    fi

    sleep 30
done

# Final commit after translation finishes
echo "[auto_commit] Translation process ended. Final commit..."
git -C "$REPO" add -- '**/*_vi.srt' '*_vi.srt' translation_progress.json 2>/dev/null
COUNT=$(git -C "$REPO" diff --cached --name-only | grep '_vi\.srt' | wc -l)
if [ "$COUNT" -gt 0 ]; then
    git -C "$REPO" commit -m "Add $COUNT Vietnamese translated SRT files (final batch)

https://claude.ai/code/session_01KrZ5QHyC1i87HuE4MDrwaP"
    git -C "$REPO" push origin claude/translate-vietnamese-auto-retry-cBckl 2>&1
fi
echo "[auto_commit] Done."
