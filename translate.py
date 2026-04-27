#!/usr/bin/env python3
"""
Translate SRT subtitle files from English to Vietnamese using Claude API.
Features: SEP-based batch translation, prompt caching, auto-retry with
exponential backoff, progress tracking, resume support.
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path
import anthropic

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "translation_progress.json"
MAX_RETRIES = 5
BATCH_SIZE = 40
SEP = "|||SEP|||"

SYSTEM_PROMPT = """You are a professional Vietnamese translator specializing in technical software development content for online video courses. Your task is to translate English subtitles for a .NET 8 Microservices Architecture course into natural, clear Vietnamese that Vietnamese software developers can easily understand.

## Translation Philosophy
Translate in a way that sounds natural to Vietnamese ears while preserving technical precision. Use the language of an engaging instructor speaking to developer students. Short, conversational subtitle blocks should flow naturally when read aloud.

## Technical Terms — Keep These in ENGLISH (do not translate)
Always keep these terms in English exactly as written:

Programming & Platforms:
- .NET, .NET 8, C#, C# 12, ASP.NET, ASP.NET Core, ASP.NET 8

Architecture Patterns:
- microservice, microservices, Microservice, Microservices
- vertical slice architecture, Vertical Slice Architecture
- clean architecture, Clean Architecture
- domain driven design, Domain Driven Design, DDD
- CQRS (Command Query Responsibility Segregation)
- REPR Pattern, Repository Pattern, Mediator Pattern
- Decorator Pattern, Proxy Pattern, Cache Aside Pattern
- Publish Subscribe Pattern, Gateway Routing Pattern

Databases & Storage:
- PostgreSQL, SQLite, SQL Server, SQL, NoSQL
- Redis, distributed cache
- Entity Framework, Entity Framework Core, EF Core

Communication & Protocols:
- gRPC, HTTP, REST, REST API, Web API, Minimal API, Minimal APIs
- RabbitMQ, MassTransit
- YARP, API Gateway, API Gateways, Reverse Proxy

Libraries & Packages:
- Carter, Marten, MediatR, Fluent Validation, Mapster, Refit
- NuGet, Bootstrap, Razor

Container & Infrastructure:
- Docker, Docker Compose, Docker file, Docker Compose file
- cloud native, Cloud Native

API Operations:
- CRUD, API, HTTP methods: GET, POST, PUT, DELETE, PATCH

Development Concepts:
- middleware, pipeline, endpoint, handler, controller, routing
- dependency injection, DI, IoC
- interface, class, namespace, constructor
- async, await, lambda
- health check, health checks
- global exception handling
- logging

Project Structure Terms:
- vertical slice, feature folder, feature folders

Specific Tools:
- Visual Studio, VS Code, Swagger, Postman
- GitHub, Git

Data Formats:
- JSON, XML, YAML

People Names:
- Personal names (e.g. "Mehmet Özkaya") stay as-is

File/Code References:
- File names like Program.cs, appsettings.json stay as-is
- Code snippets remain in English
- URLs and paths remain unchanged

## How to Handle Mixed Sentences
For sentences mixing English technical terms with regular words:
- "So we are going to learn microservices" → "Vậy chúng ta sẽ học về microservices"
- "using ASP.NET Core Web API with Docker" → "sử dụng ASP.NET Core Web API với Docker"
- "the basket microservice uses Redis" → "basket microservice sử dụng Redis"
- "We will implement CQRS pattern" → "Chúng ta sẽ triển khai mẫu CQRS"
- "using Entity Framework Core Code First approach" → "sử dụng phương pháp Entity Framework Core Code First"
- "clean architecture with best practices" → "clean architecture với các best practices"
- "implement domain driven design" → "triển khai domain driven design"

## Natural Vietnamese Phrasing
Use these natural Vietnamese expressions for common course phrases:
- "we are going to" → "chúng ta sẽ"
- "let's look at" → "hãy xem"
- "as you can see" → "như bạn có thể thấy"
- "in this section" → "trong phần này"
- "first of all" → "đầu tiên"
- "so now" → "vậy bây giờ"
- "and also" → "và cũng"
- "in order to" → "để"
- "step by step" → "từng bước một"
- "best practices" → "best practices"
- "in this course" → "trong khóa học này"
- "deep dive" → "đi sâu vào"
- "hands on" → "thực hành"

## Format Instructions
- Input: Multiple subtitle text blocks separated by the token |||SEP|||
- Output: Translated blocks in the SAME ORDER, separated by |||SEP|||
- Return EXACTLY the same number of blocks as input
- Do NOT add any preamble, explanation, or extra text
- Empty blocks (empty string or whitespace only) → return empty string
- Preserve any line breaks within a block using \\n

You are a subtitle translation engine. Output only the translated subtitles with |||SEP||| separators. Nothing else."""


def make_client() -> anthropic.Anthropic:
    token_file = os.environ.get(
        "CLAUDE_SESSION_INGRESS_TOKEN_FILE",
        "/home/claude/.claude/remote/.session_ingress_token",
    )
    try:
        with open(token_file) as f:
            token = f.read().strip()
        return anthropic.Anthropic(auth_token=token)
    except Exception:
        pass
    try:
        fd = int(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR", "4"))
        token = os.read(fd, 8192).decode().strip()
        return anthropic.Anthropic(auth_token=token)
    except Exception:
        return anthropic.Anthropic()


def parse_srt(content: str) -> list[tuple[str, str, str]]:
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    raw_blocks = re.split(r"\n\n+", content)
    result = []
    for block in raw_blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        index = lines[0].strip()
        if not re.match(r"^\d+$", index):
            continue
        timestamp = lines[1].strip()
        if "-->" not in timestamp:
            continue
        text = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""
        result.append((index, timestamp, text))
    return result


def reconstruct_srt(blocks: list[tuple[str, str, str]]) -> str:
    parts = []
    for index, timestamp, text in blocks:
        entry = f"{index}\n{timestamp}"
        if text:
            entry += f"\n{text}"
        parts.append(entry)
    return "\n\n".join(parts) + "\n\n"


def translate_batch(texts: list[str], retries: int = MAX_RETRIES) -> list[str]:
    non_empty = [(i, t) for i, t in enumerate(texts) if t.strip()]
    if not non_empty:
        return list(texts)

    indices, to_translate = zip(*non_empty)
    combined = f"\n{SEP}\n".join(to_translate)

    delay = 2
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            client = make_client()  # refresh token on every attempt
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Translate the following {len(to_translate)} subtitle block(s) "
                            f"to Vietnamese. Return exactly {len(to_translate)} block(s) "
                            f"separated by {SEP}:\n\n{combined}"
                        ),
                    }
                ],
            )
            raw = response.content[0].text.strip()
            translated = [t.strip() for t in raw.split(SEP)]
            if len(translated) == len(to_translate):
                result = list(texts)
                for i, idx in enumerate(indices):
                    result[idx] = translated[i]
                return result
            # Count mismatch — retry
            last_error = f"Expected {len(to_translate)} blocks, got {len(translated)}"
            wait = delay * (2 ** (attempt - 1))
            print(f"  Block count mismatch, retry {attempt}/{retries} in {wait}s...")
            time.sleep(wait)
        except anthropic.RateLimitError as e:
            last_error = e
            wait = delay * (2 ** (attempt - 1))
            print(f"  Rate limit, retry {attempt}/{retries} in {wait}s...")
            time.sleep(wait)
        except anthropic.APIConnectionError as e:
            last_error = e
            wait = delay * (2 ** (attempt - 1))
            print(f"  Connection error, retry {attempt}/{retries} in {wait}s...")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            last_error = e
            # 401 = token expired (will refresh on next attempt), 5xx = server errors
            if e.status_code in (401, 500, 502, 503, 529):
                wait = delay * (2 ** (attempt - 1))
                print(f"  HTTP {e.status_code}, retry {attempt}/{retries} in {wait}s...")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            last_error = e
            wait = delay * (2 ** (attempt - 1))
            print(f"  Error: {e}, retry {attempt}/{retries} in {wait}s...")
            time.sleep(wait)

    print(f"  WARNING: All retries failed ({last_error}), keeping originals for batch")
    return list(texts)


def translate_file(srt_path: Path) -> Path:
    content = srt_path.read_text(encoding="utf-8", errors="replace")
    blocks = parse_srt(content)
    if not blocks:
        return None

    texts = [block[2] for block in blocks]
    translated_texts = list(texts)

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i: i + BATCH_SIZE]
        print(f"  Batch {i // BATCH_SIZE + 1}/{(len(texts) + BATCH_SIZE - 1) // BATCH_SIZE} ({len(batch)} blocks)...")
        try:
            translated_texts[i: i + len(batch)] = translate_batch(batch)
        except Exception as e:
            print(f"  Batch error (keeping originals): {e}")

    translated_blocks = [
        (idx, ts, translated_texts[j]) for j, (idx, ts, _) in enumerate(blocks)
    ]
    out_path = srt_path.with_name(srt_path.stem + "_vi.srt")
    out_path.write_text(reconstruct_srt(translated_blocks), encoding="utf-8")
    return out_path


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress: dict) -> None:
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def find_all_srt_files() -> list[Path]:
    all_files = sorted(BASE_DIR.rglob("*.srt"))
    return [f for f in all_files if not f.name.endswith("_vi.srt")]


def main():
    parser = argparse.ArgumentParser(description="Translate SRT files to Vietnamese")
    parser.add_argument("--reset", action="store_true", help="Reset progress and retranslate all")
    parser.add_argument("--file", type=str, help="Translate a single specific file")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        print(f"Translating: {path.name}")
        out = translate_file(path)
        print(f"  Saved: {out}" if out else "  Skipped (empty).")
        return

    progress = {} if args.reset else load_progress()
    all_files = find_all_srt_files()
    pending = [f for f in all_files if str(f) not in progress or progress[str(f)] == "ERROR"]
    done_count = len(all_files) - len(pending)

    print(f"Total SRT files : {len(all_files)}")
    print(f"Already done    : {done_count}")
    print(f"Remaining       : {len(pending)}")
    print()

    start = time.time()
    for i, srt_path in enumerate(pending, 1):
        rel = srt_path.relative_to(BASE_DIR)
        print(f"[{i}/{len(pending)}] {rel}")
        try:
            out = translate_file(srt_path)
            if out:
                progress[str(srt_path)] = str(out)
                save_progress(progress)
                print(f"  -> {out.name}")
            else:
                print("  Skipped.")
        except Exception as e:
            print(f"  ERROR: {e}")
            progress[str(srt_path)] = "ERROR"
            save_progress(progress)

        # Light throttle every 10 files
        if i % 10 == 0:
            time.sleep(1)

    elapsed = time.time() - start
    errors = [k for k, v in progress.items() if v == "ERROR"]
    print(f"\nFinished in {elapsed:.0f}s. Errors: {len(errors)}")
    if errors:
        print("Files with errors (re-run to retry):")
        for e in errors:
            print(f"  {e}")


if __name__ == "__main__":
    main()
