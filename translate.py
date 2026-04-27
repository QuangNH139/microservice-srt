#!/usr/bin/env python3
"""
Translate all SRT subtitle files from English to Vietnamese.
Uses Claude Haiku with prompt caching for efficiency.
"""

import os
import re
import time
import anthropic
from pathlib import Path

def _make_client() -> anthropic.Anthropic:
    token_file = os.environ.get(
        "CLAUDE_SESSION_INGRESS_TOKEN_FILE",
        "/home/claude/.claude/remote/.session_ingress_token",
    )
    try:
        with open(token_file) as _f:
            _token = _f.read().strip()
        return anthropic.Anthropic(auth_token=_token)
    except Exception:
        pass
    try:
        _fd = int(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR", "4"))
        _token = os.read(_fd, 8192).decode().strip()
        return anthropic.Anthropic(auth_token=_token)
    except Exception:
        return anthropic.Anthropic()

client = _make_client()

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
- "best practices" → "best practices" (keep in English as it's industry-standard)
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

SEP = "|||SEP|||"


def parse_srt(content: str) -> list[tuple[str, str, str]]:
    """Parse SRT content into list of (index, timestamp, text) tuples."""
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
    """Reconstruct SRT file content from translated blocks."""
    parts = []
    for index, timestamp, text in blocks:
        entry = f"{index}\n{timestamp}"
        if text:
            entry += f"\n{text}"
        parts.append(entry)
    return "\n\n".join(parts) + "\n\n"


def translate_batch(texts: list[str], retries: int = 3) -> list[str]:
    """Translate a batch of subtitle texts to Vietnamese using Claude API."""
    # Only translate non-empty texts
    non_empty = [(i, t) for i, t in enumerate(texts) if t.strip()]
    if not non_empty:
        return list(texts)

    indices, to_translate = zip(*non_empty)
    combined = f"\n{SEP}\n".join(to_translate)

    for attempt in range(retries):
        try:
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
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                return list(texts)

        except anthropic.RateLimitError:
            wait = 4 * (2 ** attempt)  # 4s, 8s, 16s
            print(f"    [rate limit] waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 and attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise

    return list(texts)


def translate_srt_file(filepath: Path, batch_size: int = 40) -> None:
    """Read, translate, and overwrite a single SRT file."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    blocks = parse_srt(content)
    if not blocks:
        return

    texts = [block[2] for block in blocks]
    translated_texts = list(texts)  # fallback: keep originals

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            translated_batch = translate_batch(batch)
            translated_texts[i : i + len(batch)] = translated_batch
        except Exception as e:
            print(f"    [batch {i // batch_size + 1} error] {e}")

    translated_blocks = [
        (idx, ts, translated_texts[j]) for j, (idx, ts, _) in enumerate(blocks)
    ]

    filepath.write_text(reconstruct_srt(translated_blocks), encoding="utf-8")


def main(skip_file: str | None = None) -> None:
    srt_dir = Path("/home/user/microservice-srt")
    all_files = sorted(srt_dir.rglob("*.srt"))

    if skip_file:
        skip_set: set[Path] = set()
        with open(skip_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    skip_set.add(srt_dir / line)
        srt_files = [p for p in all_files if p not in skip_set]
    else:
        srt_files = all_files

    total = len(srt_files)

    print(f"Translating {total} SRT files to Vietnamese")
    print("=" * 65)

    failed: list[tuple[Path, str]] = []
    start = time.time()

    for i, filepath in enumerate(srt_files, 1):
        rel = filepath.relative_to(srt_dir)
        print(f"[{i:3d}/{total}] {rel}", end=" ", flush=True)
        try:
            translate_srt_file(filepath)
            print("✓")
        except Exception as e:
            print(f"✗ {e}")
            failed.append((filepath, str(e)))

        # Light throttle every 10 files to stay within rate limits
        if i % 10 == 0:
            time.sleep(1)

    elapsed = time.time() - start
    print("=" * 65)
    print(f"Done in {elapsed:.0f}s — {total - len(failed)}/{total} files translated")

    if failed:
        print(f"\nFailed ({len(failed)}):")
        for fp, err in failed:
            print(f"  {fp.relative_to(srt_dir)}: {err}")


if __name__ == "__main__":
    import sys
    skip = sys.argv[1] if len(sys.argv) > 1 else None
    main(skip_file=skip)
