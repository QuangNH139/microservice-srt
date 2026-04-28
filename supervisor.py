#!/usr/bin/env python3
"""
supervisor.py — chạy translate.py liên tục, tự restart khi crash,
auto-commit+push mỗi COMMIT_EVERY file xong.
"""

import subprocess, sys, time, json, os, signal
from pathlib import Path

BASE_DIR   = Path(__file__).parent
PROGRESS   = BASE_DIR / "translation_progress.json"
TOTAL      = 349
COMMIT_EVERY = 3
DELAY      = 5
BRANCH     = "claude/translate-vietnamese-auto-retry-cBckl"


def log(msg):
    print(f"[supervisor {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def count_done():
    try:
        d = json.loads(PROGRESS.read_text())
        return len([v for v in d.values() if v != "ERROR"])
    except Exception:
        return 0


def git_run(*args):
    return subprocess.run(["git"] + list(args), cwd=BASE_DIR,
                          capture_output=True, text=True)


def commit_push(done):
    git_run("add", "-u")
    git_run("add", "translation_progress.json", "supervisor.log", "run.log")
    diff = git_run("diff", "--cached", "--name-only")
    if not diff.stdout.strip():
        return
    msg = (f"Translate SRT files to Vietnamese (progress: {done}/{TOTAL})\n\n"
           f"https://claude.ai/code/session_01KrZ5QHyC1i87HuE4MDrwaP")
    git_run("commit", "-m", msg)
    log(f"Committed ({done}/{TOTAL}). Pushing...")
    for attempt in range(1, 6):
        git_run("pull", "--rebase", "origin", BRANCH)
        r = git_run("push", "-u", "origin", BRANCH)
        if r.returncode == 0:
            log("Pushed OK.")
            return
        wait = 2 ** attempt
        log(f"Push failed attempt {attempt}, retry in {wait}s...")
        time.sleep(wait)
    log("WARNING: push failed after 5 attempts.")


def run_once():
    done_before = count_done()
    log(f"Starting translate.py ({done_before}/{TOTAL} done)...")
    proc = subprocess.Popen(
        [sys.executable, "-u", str(BASE_DIR / "translate.py"), "--max-files", "5"],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    last_commit = done_before
    for line in proc.stdout:
        sys.stdout.write(line); sys.stdout.flush()
        cur = count_done()
        if cur - last_commit >= COMMIT_EVERY:
            log(f"Threshold ({cur} done). Committing...")
            commit_push(cur)
            last_commit = cur
    proc.wait()
    done_after = count_done()
    log(f"translate.py exited (code={proc.returncode}). {done_after}/{TOTAL} done.")
    if done_after > last_commit:
        commit_push(done_after)
    return proc.returncode, done_after


def main():
    # Ignore SIGHUP so we survive terminal disconnect
    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except (AttributeError, OSError):
        pass

    log(f"=== Supervisor started. Target: {TOTAL} ===")
    run_n = 0
    while True:
        try:
            done = count_done()
            if done >= TOTAL:
                log("=== ALL DONE ===")
                commit_push(done)
                break
            run_n += 1
            log(f"--- Run #{run_n} ---")
            code, done = run_once()
            if done >= TOTAL:
                log("=== ALL DONE ===")
                break
            wait = DELAY if code != 0 else 2
            log(f"Restarting in {wait}s...")
            time.sleep(wait)
        except Exception as e:
            log(f"Supervisor exception: {e}. Recovering in {DELAY}s...")
            time.sleep(DELAY)


if __name__ == "__main__":
    main()
