#!/usr/bin/env python3
"""
Translate SRT subtitle files from English to Vietnamese using Claude API.
Features: batch translation, auto-retry with exponential backoff, progress tracking.
"""

import os
import re
import json
import time
import glob
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import anthropic

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "translation_progress.json"
TOKEN_FILE = Path("/home/claude/.claude/remote/.session_ingress_token")
MAX_RETRIES = 5
BATCH_SIZE = 50  # number of text segments per API call


def get_client() -> anthropic.Anthropic:
    """Create Anthropic client using session ingress token."""
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        return anthropic.Anthropic(auth_token=token)
    # Fallback to env var
    return anthropic.Anthropic()


@dataclass
class SrtBlock:
    index: int
    timestamp: str
    lines: list[str]


def parse_srt(content: str) -> list[SrtBlock]:
    blocks = []
    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n').strip()
    raw_blocks = re.split(r'\n\n+', content)
    for raw in raw_blocks:
        parts = raw.strip().split('\n')
        if len(parts) < 3:
            continue
        try:
            idx = int(parts[0].strip())
        except ValueError:
            continue
        timestamp = parts[1].strip()
        text_lines = parts[2:]
        blocks.append(SrtBlock(index=idx, timestamp=timestamp, lines=text_lines))
    return blocks


def blocks_to_srt(blocks: list[SrtBlock]) -> str:
    parts = []
    for b in blocks:
        parts.append(str(b.index))
        parts.append(b.timestamp)
        parts.extend(b.lines)
        parts.append('')
    return '\n'.join(parts).strip() + '\n'


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(progress: dict) -> None:
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def translate_batch(texts: list[str], retries: int = MAX_RETRIES) -> list[str]:
    """Translate a batch of English text segments to Vietnamese with auto-retry."""
    numbered = '\n'.join(f'[{i+1}] {t}' for i, t in enumerate(texts))
    prompt = f"""Translate the following English subtitle lines to Vietnamese.
Keep technical terms (API names, library names, programming terms like CQRS, gRPC, Docker, etc.) in English.
Return ONLY the translations in the same numbered format [1], [2], etc. with no extra text.

{numbered}"""

    delay = 2
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            client = get_client()  # refresh token on every attempt
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            response = message.content[0].text
            translated = parse_numbered_response(response, len(texts))
            return translated
        except anthropic.RateLimitError as e:
            last_error = e
            wait = delay * (2 ** (attempt - 1))
            print(f"  Rate limit hit, retry {attempt}/{retries} in {wait}s...")
            time.sleep(wait)
        except anthropic.APIConnectionError as e:
            last_error = e
            wait = delay * (2 ** (attempt - 1))
            print(f"  Connection error, retry {attempt}/{retries} in {wait}s...")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            last_error = e
            if e.status_code in (401, 500, 502, 503, 529):
                wait = delay * (2 ** (attempt - 1))
                print(f"  HTTP {e.status_code}, retry {attempt}/{retries} in {wait}s (token refresh)...")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            last_error = e
            wait = delay * (2 ** (attempt - 1))
            print(f"  Unexpected error: {e}, retry {attempt}/{retries} in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {retries} retries: {last_error}")


def parse_numbered_response(response: str, expected: int) -> list[str]:
    """Extract numbered translations from Claude response."""
    lines = response.strip().split('\n')
    result = {}
    current_idx = None
    current_parts = []

    for line in lines:
        m = re.match(r'^\[(\d+)\]\s*(.*)', line)
        if m:
            if current_idx is not None:
                result[current_idx] = ' '.join(current_parts).strip()
            current_idx = int(m.group(1))
            current_parts = [m.group(2)]
        elif current_idx is not None:
            current_parts.append(line)

    if current_idx is not None:
        result[current_idx] = ' '.join(current_parts).strip()

    # Fallback: return originals if parsing fails
    return [result.get(i + 1, '') for i in range(expected)]


def translate_file(srt_path: Path) -> Path:
    """Translate a single SRT file and save the Vietnamese version."""
    content = srt_path.read_text(encoding='utf-8', errors='replace')
    blocks = parse_srt(content)

    if not blocks:
        print(f"  Skipping (empty or invalid): {srt_path.name}")
        return None

    # Collect all text segments with their positions
    segments: list[tuple[int, int, str]] = []  # (block_idx, line_idx, text)
    for bi, block in enumerate(blocks):
        for li, line in enumerate(block.lines):
            if line.strip():
                segments.append((bi, li, line.strip()))

    if not segments:
        return None

    # Translate in batches
    all_translated: dict[tuple[int, int], str] = {}
    for start in range(0, len(segments), BATCH_SIZE):
        batch = segments[start:start + BATCH_SIZE]
        texts = [s[2] for s in batch]
        print(f"  Translating segments {start+1}-{start+len(batch)}/{len(segments)}...")
        translated = translate_batch(texts)
        for (bi, li, _), trans in zip(batch, translated):
            all_translated[(bi, li)] = trans if trans else _

    # Reconstruct blocks with translated text
    for bi, block in enumerate(blocks):
        new_lines = []
        for li, line in enumerate(block.lines):
            if (bi, li) in all_translated:
                new_lines.append(all_translated[(bi, li)])
            else:
                new_lines.append(line)
        block.lines = new_lines

    # Save as _vi.srt in same directory
    out_path = srt_path.with_name(srt_path.stem + '_vi.srt')
    out_path.write_text(blocks_to_srt(blocks), encoding='utf-8')
    return out_path


def find_all_srt_files() -> list[Path]:
    pattern = str(BASE_DIR / '**' / '*.srt')
    all_files = sorted(glob.glob(pattern, recursive=True))
    # Exclude already-translated files
    return [Path(f) for f in all_files if not f.endswith('_vi.srt')]


def main():
    parser = argparse.ArgumentParser(description='Translate SRT files to Vietnamese')
    parser.add_argument('--reset', action='store_true', help='Reset progress and retranslate all')
    parser.add_argument('--file', type=str, help='Translate a single specific file')
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        print(f"Translating: {path.name}")
        out = translate_file(path)
        if out:
            print(f"  Saved: {out}")
        return

    progress = {} if args.reset else load_progress()
    all_files = find_all_srt_files()

    pending = [f for f in all_files if str(f) not in progress or progress[str(f)] == "ERROR"]
    done_count = len(all_files) - len(pending)

    print(f"Total SRT files: {len(all_files)}")
    print(f"Already translated: {done_count}")
    print(f"Remaining: {len(pending)}")
    print()

    for i, srt_path in enumerate(pending):
        rel = srt_path.relative_to(BASE_DIR)
        print(f"[{i+1}/{len(pending)}] {rel}")
        try:
            out = translate_file(srt_path)
            if out:
                progress[str(srt_path)] = str(out)
                save_progress(progress)
                print(f"  Done -> {out.name}")
            else:
                print(f"  Skipped.")
        except Exception as e:
            print(f"  ERROR: {e}")
            print(f"  Skipping and continuing...")
            progress[str(srt_path)] = "ERROR"
            save_progress(progress)

    errors = [k for k, v in progress.items() if v == "ERROR"]
    print(f"\nCompleted. Errors: {len(errors)}")
    if errors:
        print("Files with errors (will retry on next run):")
        for e in errors:
            print(f"  {e}")


if __name__ == '__main__':
    main()
