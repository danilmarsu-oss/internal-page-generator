#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


PAGE_TYPES = [
    "bonus",
    "app",
    "login",
    "contact us",
    "about us",
    "bonus policy",
    "privacy policy",
    "terms and conditions",
    "responsible gambling",
]

API_URL = "https://api.anthropic.com/v1/messages"
MODELS_URL = "https://api.anthropic.com/v1/models"
API_VERSION = "2023-06-01"


@dataclass(frozen=True)
class SiteTask:
    task_id: str
    brand: str
    geo: str
    page_types: Tuple[str, ...] = field(default_factory=lambda: tuple(PAGE_TYPES))
    source_row: Optional[int] = None


@dataclass(frozen=True)
class PageResult:
    task_id: str
    brand: str
    geo: str
    page_type: str
    html_file: str


ProgressCallback = Callable[[int, int, str, bool, str], None]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "item"


def normalize_text_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def canonicalize_page_type(value: str) -> str:
    aliases = {
        "termsconditions": "terms and conditions",
        "termsandconditions": "terms and conditions",
        "privacy": "privacy policy",
        "responsiblegaming": "responsible gambling",
        "bonuspage": "bonus",
        "signin": "login",
        "logon": "login",
    }
    key = normalize_text_key(value)
    default_map = {normalize_text_key(item): item for item in PAGE_TYPES}
    if key in default_map:
        return default_map[key]
    if key in aliases:
        return aliases[key]
    return value.strip().lower()


def parse_page_types(raw_value: str, fallback_page_types: List[str]) -> Tuple[str, ...]:
    raw = raw_value.strip()
    if not raw:
        return tuple(fallback_page_types)

    lowered = raw.lower()
    if lowered in {"all", "*", "8", "eight", "default"}:
        return tuple(fallback_page_types)

    parts = [p.strip() for p in re.split(r"[,\n;|]+", raw) if p.strip()]
    if not parts:
        return tuple(fallback_page_types)

    seen = set()
    normalized_parts: List[str] = []
    for item in parts:
        canonical = canonicalize_page_type(item)
        key = normalize_text_key(canonical)
        if key in seen:
            continue
        seen.add(key)
        normalized_parts.append(canonical)

    return tuple(normalized_parts) if normalized_parts else tuple(fallback_page_types)


def build_prompt(page_type: str, brand: str, geo: str) -> str:
    return (
        f"Write {page_type} for {brand} casino. "
        f"It must be around 1000 words about this casino brand, in {geo} language. "
        "Use we/our formulations because it's for the official website. "
        f"Mention that this is an official website in {geo}. "
        "Return plain HTML only (no markdown, no code fences). "
        "This must be a text content file in plain HTML format, not a full ready-made web page template "
        "(no complete site layout with html/head/body wrappers unless critically needed for meta tags). "
        "Include meta title and meta description in HTML."
    )


def create_ssl_context(ca_bundle_path: Optional[Path], insecure_no_verify: bool) -> ssl.SSLContext:
    if insecure_no_verify:
        return ssl._create_unverified_context()  # noqa: SLF001

    if ca_bundle_path:
        return ssl.create_default_context(cafile=str(ca_bundle_path))

    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        # Fallback for environments where certifi is unavailable.
        return ssl.create_default_context()


def list_available_models(api_key: str, timeout: int, ssl_context: ssl.SSLContext) -> List[str]:
    req = urllib.request.Request(
        MODELS_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
        body = resp.read().decode("utf-8")

    payload = json.loads(body)
    data = payload.get("data", [])
    model_ids: List[str] = []
    for item in data:
        model_id = str(item.get("id", "")).strip()
        if model_id:
            model_ids.append(model_id)
    return model_ids


def pick_best_model(available_models: List[str]) -> Optional[str]:
    if not available_models:
        return None

    preferred_order = [
        "claude-sonnet-4-5",
        "claude-sonnet-4-0",
        "claude-3-7-sonnet-latest",
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-latest",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-haiku-latest",
    ]
    available_set = set(available_models)
    for candidate in preferred_order:
        if candidate in available_set:
            return candidate

    sonnets = sorted([m for m in available_models if "sonnet" in m], reverse=True)
    if sonnets:
        return sonnets[0]

    return sorted(available_models)[0]


def resolve_model(
    api_key: str,
    requested_model: str,
    timeout: int,
    ssl_context: ssl.SSLContext,
) -> Tuple[str, List[str], Optional[str]]:
    try:
        available_models = list_available_models(api_key=api_key, timeout=timeout, ssl_context=ssl_context)
    except Exception:
        # If we cannot list models, keep user's choice.
        return requested_model, [], None

    if not available_models:
        return requested_model, [], None

    requested = requested_model.strip()
    if requested and requested.lower() != "auto" and requested in available_models:
        return requested, available_models, None

    picked = pick_best_model(available_models)
    if not picked:
        return requested_model, available_models, None

    if requested.lower() == "auto":
        return picked, available_models, f"Auto-selected model: {picked}"

    return picked, available_models, f"Model '{requested}' not available, switched to '{picked}'"


def anthropic_request(
    api_key: str,
    model: str,
    max_tokens: int,
    prompt: str,
    temperature: float,
    timeout: int,
    ssl_context: ssl.SSLContext,
) -> str:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
        body = resp.read().decode("utf-8")

    response = json.loads(body)
    content = response.get("content", [])
    text_blocks: List[str] = []

    for block in content:
        if block.get("type") == "text":
            text_blocks.append(block.get("text", ""))

    return "\n".join(text_blocks).strip()


def clean_html_output(text: str) -> str:
    cleaned = text.strip()
    fence_match = re.match(r"^```(?:html)?\s*([\s\S]*?)\s*```$", cleaned, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return cleaned


def generate_with_retries(
    api_key: str,
    model: str,
    max_tokens: int,
    prompt: str,
    temperature: float,
    timeout: int,
    retries: int,
    retry_base_delay: float,
    ssl_context: ssl.SSLContext,
) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            raw = anthropic_request(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                prompt=prompt,
                temperature=temperature,
                timeout=timeout,
                ssl_context=ssl_context,
            )
            return clean_html_output(raw)
        except urllib.error.HTTPError as e:
            retryable = e.code in {408, 409, 429, 500, 502, 503, 504}
            body = e.read().decode("utf-8", errors="ignore")
            if not retryable or attempt == retries:
                raise RuntimeError(f"HTTP {e.code}: {body}") from e
            last_error = e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries:
                raise RuntimeError(str(e)) from e
            last_error = e

        delay = retry_base_delay * (2 ** (attempt - 1))
        time.sleep(delay)

    raise RuntimeError(f"Request failed after retries: {last_error}")


def parse_csv_tasks(path: Path, fallback_page_types: List[str]) -> List[SiteTask]:
    tasks: List[SiteTask] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV appears empty or missing header row.")

        header_keys = {normalize_text_key(h): h for h in reader.fieldnames}
        if "brand" not in header_keys or "geo" not in header_keys:
            raise ValueError("CSV must contain columns: brand, geo. Optional: page type")

        brand_col = header_keys["brand"]
        geo_col = header_keys["geo"]
        page_type_col = header_keys.get("pagetype")

        for idx, row in enumerate(reader, start=2):
            brand = (row.get(brand_col) or "").strip()
            geo = (row.get(geo_col) or "").strip()
            if not brand or not geo:
                continue

            raw_page_types = (row.get(page_type_col) or "").strip() if page_type_col else ""
            page_types = parse_page_types(raw_page_types, fallback_page_types)
            tasks.append(
                SiteTask(
                    task_id=f"csv-{idx}",
                    brand=brand,
                    geo=geo,
                    page_types=page_types,
                    source_row=idx,
                )
            )

    return tasks


def load_tasks(
    single_brand: Optional[str],
    single_geo: Optional[str],
    csv_path: Optional[Path],
    fallback_page_types: List[str],
) -> List[SiteTask]:
    if csv_path:
        tasks = parse_csv_tasks(csv_path, fallback_page_types=fallback_page_types)
        if not tasks:
            raise ValueError("No valid rows found in CSV.")
        return tasks

    if single_brand and single_geo:
        return [
            SiteTask(
                task_id="single-1",
                brand=single_brand.strip(),
                geo=single_geo.strip(),
                page_types=tuple(fallback_page_types),
                source_row=None,
            )
        ]

    raise ValueError("Provide --csv or both --brand and --geo.")


def save_html(content: str, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content, encoding="utf-8")


def generate_job(
    task: SiteTask,
    page_type: str,
    api_key: str,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout: int,
    retries: int,
    retry_base_delay: float,
    ssl_context: ssl.SSLContext,
    output_dir: Path,
) -> PageResult:
    page_slug = slugify(page_type)
    brand_slug = slugify(task.brand)
    geo_slug = slugify(task.geo)
    task_slug = slugify(task.task_id)
    target_file = output_dir / f"{brand_slug}__{geo_slug}__{task_slug}" / f"{page_slug}.html"
    prompt = build_prompt(page_type=page_type, brand=task.brand, geo=task.geo)

    html = generate_with_retries(
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        prompt=prompt,
        temperature=temperature,
        timeout=timeout,
        retries=retries,
        retry_base_delay=retry_base_delay,
        ssl_context=ssl_context,
    )
    save_html(html, target_file)

    return PageResult(
        task_id=task.task_id,
        brand=task.brand,
        geo=task.geo,
        page_type=page_type,
        html_file=str(target_file),
    )


def run_generation(
    tasks: List[SiteTask],
    output_dir: Path,
    api_key: str,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout: int,
    retries: int,
    retry_base_delay: float,
    max_workers: int,
    ssl_context: ssl.SSLContext,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, object]:
    jobs = [(task, page_type) for task in tasks for page_type in task.page_types]
    total_jobs = len(jobs)

    lock = threading.Lock()
    completed = 0
    success_count = 0
    failures: List[Dict[str, str]] = []
    successful_pages: List[PageResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                generate_job,
                task=task,
                page_type=page_type,
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                retries=retries,
                retry_base_delay=retry_base_delay,
                ssl_context=ssl_context,
                output_dir=output_dir,
            ): (task, page_type)
            for task, page_type in jobs
        }

        for future in as_completed(futures):
            task, page_type = futures[future]
            label = f"{task.brand} | {task.geo} | {page_type}"

            with lock:
                completed += 1
                done_now = completed

            try:
                result = future.result()
                with lock:
                    success_count += 1
                successful_pages.append(result)
                if progress_callback:
                    progress_callback(done_now, total_jobs, label, True, result.html_file)
            except Exception as e:
                error_text = str(e)
                failures.append(
                    {
                        "task_id": task.task_id,
                        "source_row": str(task.source_row) if task.source_row is not None else "",
                        "brand": task.brand,
                        "geo": task.geo,
                        "page_type": page_type,
                        "error": error_text,
                    }
                )
                if progress_callback:
                    progress_callback(done_now, total_jobs, label, False, error_text)

    return {
        "total_jobs": total_jobs,
        "success_count": success_count,
        "failed_count": len(failures),
        "successful_pages": successful_pages,
        "failures": failures,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate internal page HTML content for many brands/geos via Claude API."
    )
    parser.add_argument("--brand", help="Single brand name")
    parser.add_argument("--geo", help="Geo/language (e.g. 'Polish', 'Germany German')")
    parser.add_argument("--csv", type=Path, help="CSV with columns: brand,geo[,page type]")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("generated_pages"),
        help="Directory where HTML files will be written (default: generated_pages)",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ANTHROPIC_API_KEY"),
        help="Anthropic API key (default from ANTHROPIC_API_KEY env)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("CLAUDE_MODEL", "auto"),
        help="Claude model id, or 'auto' to pick available model automatically (default: auto)",
    )
    parser.add_argument("--max-tokens", type=int, default=2500, help="max_tokens for API response")
    parser.add_argument("--temperature", type=float, default=0.6, help="Sampling temperature")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout (seconds)")
    parser.add_argument("--retries", type=int, default=4, help="Retries per request")
    parser.add_argument("--retry-base-delay", type=float, default=1.5, help="Base delay for exponential backoff")
    parser.add_argument(
        "--ca-bundle",
        type=Path,
        help="Path to CA bundle file (PEM). If omitted, certifi bundle is used.",
    )
    parser.add_argument(
        "--insecure-no-verify",
        action="store_true",
        help="Disable SSL certificate verification (unsafe, only for debugging).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Parallel requests (increase if your account limits allow it)",
    )
    parser.add_argument(
        "--page-types",
        nargs="+",
        default=PAGE_TYPES,
        help="Fallback page types (for single-brand mode and CSV rows without page type).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.api_key:
        print("Error: missing API key. Pass --api-key or set ANTHROPIC_API_KEY.", file=sys.stderr)
        return 1

    try:
        tasks = load_tasks(
            single_brand=args.brand,
            single_geo=args.geo,
            csv_path=args.csv,
            fallback_page_types=args.page_types,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(
        f"Generating {sum(len(task.page_types) for task in tasks)} pages "
        f"from {len(tasks)} task(s)..."
    )

    try:
        ssl_context = create_ssl_context(ca_bundle_path=args.ca_bundle, insecure_no_verify=args.insecure_no_verify)
    except Exception as e:
        print(f"Error: failed to initialize SSL context: {e}", file=sys.stderr)
        return 1

    selected_model, available_models, model_note = resolve_model(
        api_key=args.api_key,
        requested_model=args.model,
        timeout=args.timeout,
        ssl_context=ssl_context,
    )
    if model_note:
        print(model_note)
    if available_models:
        print(f"Using model: {selected_model}")

    def cli_progress(completed: int, total: int, label: str, ok: bool, message: str) -> None:
        status = "OK" if ok else "FAIL"
        stream = sys.stdout if ok else sys.stderr
        print(f"[{completed}/{total}] {status:<4} {label} -> {message}", file=stream)

    result = run_generation(
        tasks=tasks,
        output_dir=args.output_dir,
        api_key=args.api_key,
        model=selected_model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        timeout=args.timeout,
        retries=args.retries,
        retry_base_delay=args.retry_base_delay,
        max_workers=args.max_workers,
        ssl_context=ssl_context,
        progress_callback=cli_progress,
    )

    print(
        f"Done. Success: {result['success_count']}/{result['total_jobs']}, "
        f"Failed: {result['failed_count']}"
    )

    if result["failures"]:
        fail_report = args.output_dir / "failed_jobs.json"
        fail_report.parent.mkdir(parents=True, exist_ok=True)
        fail_report.write_text(json.dumps(result["failures"], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Failure report saved to: {fail_report}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
