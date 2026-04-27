#!/usr/bin/env python3
"""
Supervisor: runs translate.py in a loop, auto-restarts on crash,
and auto-commits+pushes every COMMIT_EVERY files.
"""

import subprocess
import sys
import time
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "translation_progress.json"
TOTAL_FILES = 349
COMMIT_EVERY = 1
RESTART_DELAY = 5  # seconds before restarting after crash
BRANCH = "claude/translate-vietnamese-auto-retry-cBckl"


def log(msg: str) -> None:
    print(f"[supervisor {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def count_done() -> int:
    if not PROGRESS_FILE.exists():
        return 0
    try:
        d = json.loads(PROGRESS_FILE.read_text())
        return len([v for v in d.values() if v != "ERROR"])
    except Exception:
        return 0


def git_commit_push(done: int) -> None:
    # Stage all modified/new SRT files and progress
    subprocess.run(["git", "add", "-u"], cwd=BASE_DIR, capture_output=True)
    subprocess.run(["git", "add", "translation_progress.json"], cwd=BASE_DIR, capture_output=True)

    # Check if there's anything staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=BASE_DIR, capture_output=True, text=True
    )
    if not result.stdout.strip():
        log("Nothing to commit.")
        return

    msg = (
        f"Translate SRT files to Vietnamese (progress: {done}/{TOTAL_FILES})\n\n"
        f"https://claude.ai/code/session_01KrZ5QHyC1i87HuE4MDrwaP"
    )
    subprocess.run(["git", "commit", "-m", msg], cwd=BASE_DIR, capture_output=True)
    log(f"Committed ({done}/{TOTAL_FILES} done). Pushing...")

    # Push with exponential backoff
    for attempt in range(1, 5):
        r = subprocess.run(
            ["git", "push", "-u", "origin", BRANCH],
            cwd=BASE_DIR, capture_output=True, text=True
        )
        if r.returncode == 0:
            log("Pushed OK.")
            return
        wait = 2 ** attempt
        log(f"Push failed (attempt {attempt}), retrying in {wait}s...")
        time.sleep(wait)
    log("WARNING: Push failed after 4 attempts.")


def main():
    log(f"=== Supervisor started. Target: {TOTAL_FILES} files ===")

    last_commit_at = count_done()
    run_count = 0

    while True:
      try:
        done = count_done()
        if done >= TOTAL_FILES:
            log(f"All {TOTAL_FILES} files translated!")
            git_commit_push(done)
            log("=== COMPLETE ===")
            break

        run_count += 1
        log(f"Run #{run_count}: {done}/{TOTAL_FILES} done, starting translate.py...")

        proc = subprocess.Popen(
            [sys.executable, "-u", str(BASE_DIR / "translate.py")],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output and watch for commit triggers
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()

            # Check if we should commit (every COMMIT_EVERY files)
            current_done = count_done()
            if current_done - last_commit_at >= COMMIT_EVERY:
                log(f"Threshold reached ({current_done} done). Committing...")
                git_commit_push(current_done)
                last_commit_at = current_done

        proc.wait()
        exit_code = proc.returncode
        done_after = count_done()

        log(f"translate.py exited (code={exit_code}). Progress: {done_after}/{TOTAL_FILES}")

        # Commit whatever was done in this run
        if done_after > last_commit_at:
            git_commit_push(done_after)
            last_commit_at = done_after

        if done_after >= TOTAL_FILES:
            log("=== All files done! ===")
            break

        if exit_code == 0:
            log(f"Unexpected normal exit with {done_after} files done. Restarting...")
            time.sleep(2)
        else:
            log(f"Crashed (exit={exit_code}). Restarting in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)

      except Exception as e:
          log(f"Supervisor error: {e}. Recovering in {RESTART_DELAY}s...")
          time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
