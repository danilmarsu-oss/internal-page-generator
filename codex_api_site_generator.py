#!/usr/bin/env python3
import json
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


RESPONSES_URL = "https://api.openai.com/v1/responses"

RunProgressCallback = Callable[[int, int, str, bool, str], None]


@dataclass(frozen=True)
class CodexStepResult:
    step_number: int
    title: str
    changed_files: List[str]
    deleted_files: List[str]
    notes: str
    raw_response_excerpt: str


@dataclass(frozen=True)
class CodexRunResult:
    files: Dict[str, str]
    step_results: List[CodexStepResult]
    prompts_used: List[Tuple[str, str]]


def _normalize_rel_path(path: str) -> str:
    p = path.strip().replace("\\", "/")
    if not p:
        raise ValueError("Empty path is not allowed.")
    if p.startswith("/") or p.startswith("../") or "/../" in p or p == "..":
        raise ValueError(f"Unsafe path: {path}")
    return p


def _render_files_snapshot(files: Dict[str, str], max_chars_per_file: int = 20000) -> str:
    if not files:
        return "(project is empty)"

    blocks: List[str] = []
    for path in sorted(files):
        content = files[path]
        if len(content) > max_chars_per_file:
            shown = content[:max_chars_per_file]
            suffix = f"\n\n<!-- TRUNCATED: {len(content) - max_chars_per_file} chars omitted -->"
            content_to_show = shown + suffix
        else:
            content_to_show = content
        blocks.append(f"FILE: {path}\n```text\n{content_to_show}\n```")
    return "\n\n".join(blocks)


def _extract_text_from_response(response_json: Dict[str, object]) -> str:
    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    fragments: List[str] = []
    output = response_json.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                text_value = c.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    fragments.append(text_value.strip())
    return "\n\n".join(fragments).strip()


def _extract_json_block(text: str) -> str:
    stripped = text.strip()
    fence_match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", stripped, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        return stripped[first : last + 1]

    raise ValueError("Model response does not contain JSON object.")


def _parse_patch_payload(text: str) -> Dict[str, object]:
    raw_json = _extract_json_block(text)
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError("Patch payload must be a JSON object.")

    files_value = payload.get("files", [])
    delete_value = payload.get("delete_paths", [])
    notes_value = payload.get("notes", "")

    if not isinstance(files_value, list):
        raise ValueError("`files` must be an array.")
    if not isinstance(delete_value, list):
        raise ValueError("`delete_paths` must be an array.")
    if not isinstance(notes_value, str):
        notes_value = str(notes_value)

    normalized_files: List[Dict[str, str]] = []
    for item in files_value:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            continue
        normalized_files.append({"path": _normalize_rel_path(path), "content": content})

    normalized_delete_paths: List[str] = []
    for p in delete_value:
        if isinstance(p, str):
            normalized_delete_paths.append(_normalize_rel_path(p))

    return {
        "files": normalized_files,
        "delete_paths": normalized_delete_paths,
        "notes": notes_value.strip(),
    }


def _call_responses_api(
    api_key: str,
    model: str,
    prompt: str,
    timeout: int,
    ssl_context: ssl.SSLContext,
) -> Dict[str, object]:
    payload = {
        "model": model,
        "input": prompt,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESPONSES_URL,
        data=data,
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise RuntimeError("Unexpected API response format.")
        return parsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(str(e)) from e


def run_codex_prompt_pack_via_api(
    prompt_pack: List[Tuple[str, str]],
    api_key: str,
    model: str,
    timeout: int,
    ssl_context: ssl.SSLContext,
    progress_callback: Optional[RunProgressCallback] = None,
) -> CodexRunResult:
    files: Dict[str, str] = {}
    step_results: List[CodexStepResult] = []

    total = len(prompt_pack)
    for idx, (title, step_prompt) in enumerate(prompt_pack, start=1):
        snapshot = _render_files_snapshot(files)
        instruction = (
            "You are Codex, a senior web engineer. "
            "Apply the requested step to the current project files.\n\n"
            "Return only JSON object with this exact schema:\n"
            "{\n"
            '  "files": [{"path":"relative/path.ext","content":"full file content"}],\n'
            '  "delete_paths": ["relative/path/to/delete.ext"],\n'
            '  "notes": "short summary"\n'
            "}\n\n"
            "Rules:\n"
            "- Include only files that were created or changed in this step.\n"
            "- For each changed file provide full file content, not partial diff.\n"
            "- Keep previously created working functionality unless step explicitly changes it.\n"
            "- Use relative paths only.\n"
            "- No markdown, no prose outside JSON.\n\n"
            f"STEP {idx}/{total}: {title}\n\n"
            f"STEP INSTRUCTION:\n{step_prompt}\n\n"
            f"CURRENT PROJECT FILES:\n{snapshot}\n"
        )

        try:
            api_response = _call_responses_api(
                api_key=api_key,
                model=model,
                prompt=instruction,
                timeout=timeout,
                ssl_context=ssl_context,
            )
            response_text = _extract_text_from_response(api_response)
            patch = _parse_patch_payload(response_text)

            changed_files: List[str] = []
            deleted_files: List[str] = []

            for p in patch["delete_paths"]:
                if p in files:
                    del files[p]
                    deleted_files.append(p)

            for item in patch["files"]:
                path = item["path"]
                files[path] = item["content"]
                changed_files.append(path)

            notes = patch["notes"]
            step_results.append(
                CodexStepResult(
                    step_number=idx,
                    title=title,
                    changed_files=sorted(changed_files),
                    deleted_files=sorted(deleted_files),
                    notes=notes,
                    raw_response_excerpt=response_text[:4000],
                )
            )
            if progress_callback:
                progress_callback(
                    idx,
                    total,
                    title,
                    True,
                    f"{len(changed_files)} changed, {len(deleted_files)} deleted",
                )
        except Exception as e:
            if progress_callback:
                progress_callback(idx, total, title, False, str(e))
            raise

    return CodexRunResult(files=files, step_results=step_results, prompts_used=prompt_pack)


def write_generated_project(
    files: Dict[str, str],
    target_dir: Path,
) -> None:
    for rel_path, content in files.items():
        safe_path = _normalize_rel_path(rel_path)
        out_path = target_dir / safe_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
