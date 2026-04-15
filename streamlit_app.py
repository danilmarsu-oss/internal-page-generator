#!/usr/bin/env python3
import csv
import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import streamlit as st

from codex_api_site_generator import run_codex_prompt_pack_via_api, write_generated_project
from generate_internal_pages import PAGE_TYPES, create_ssl_context, parse_csv_tasks, resolve_model, run_generation
from site_prompt_builder import SitePromptConfig, as_markdown, build_codex_prompt_pack

PRESETS_FILE = Path(__file__).resolve().parent / "site_prompt_presets.json"

SITE_FIELD_DEFAULTS: Dict[str, str] = {
    "brand": "Casimba",
    "language_name": "Finnish",
    "lang_code": "fi",
    "h1_text": "Casimba Casino",
    "cta_text": "Pelaa nyt!",
    "login_button_text": "Kirjaudu",
    "register_button_text": "Rekisteröidy",
    "header_links_text": "Login, Bonus, App",
    "footer_policy_links": "about us, contact us, bonus policy, privacy policy, responsible gambling",
    "copyright_year": "2026",
    "github_repo_name": "casimba-casino-site",
    "cf_account_id": "",
    "cf_zone_id": "",
    "cf_api_token": "",
    "custom_domain": "casino-example.com",
    "header_footer_color": "#175576",
    "header_button_color": "#c5740e",
    "cta_color": "#f3910c",
    "main_background_color": "#ffffff",
    "logo_path": "casimba.webp",
    "homepage_banner_path": "casimba casino.webp",
    "favicon_path": "favicon.ico",
    "game_images_dir": "game images",
    "payment_methods_dir": "casino payment methods",
    "trust_badges_dir": "trust bages",
    "game_providers_dir": "game providers",
    "extra_images_dir": "nv casino images",
    "homepage_text_source": "casimba homepage",
    "texts_dir": "casimba texts",
    "redirect_path": "/go/",
    "redirect_target_url": "https://sltna.pclira.com/?mid=352177_2029432",
    "trust_links": (
        "https://www.gamstop.co.uk/, "
        "https://www.gamcare.org.uk/, "
        "https://www.egba.eu/, "
        "https://www.begambleaware.org/, "
        "https://www.gamblingcommission.gov.uk/"
    ),
}


def _site_key(field: str) -> str:
    return f"site_{field}"


def ensure_site_defaults() -> None:
    for field, default_value in SITE_FIELD_DEFAULTS.items():
        st.session_state.setdefault(_site_key(field), default_value)


def current_site_values() -> Dict[str, str]:
    values: Dict[str, str] = {}
    for field, default_value in SITE_FIELD_DEFAULTS.items():
        values[field] = str(st.session_state.get(_site_key(field), default_value))
    return values


def apply_site_values(values: Dict[str, str]) -> None:
    for field, default_value in SITE_FIELD_DEFAULTS.items():
        st.session_state[_site_key(field)] = str(values.get(field, default_value))


def load_site_presets() -> Dict[str, Dict[str, str]]:
    if not PRESETS_FILE.exists():
        return {}
    try:
        raw = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    cleaned: Dict[str, Dict[str, str]] = {}
    for preset_name, preset_values in raw.items():
        if not isinstance(preset_name, str) or not isinstance(preset_values, dict):
            continue
        cleaned[preset_name] = {
            field: str(preset_values.get(field, default_value))
            for field, default_value in SITE_FIELD_DEFAULTS.items()
        }
    return cleaned


def save_site_presets(presets: Dict[str, Dict[str, str]]) -> None:
    PRESETS_FILE.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


def build_site_config_from_values(values: Dict[str, str]) -> SitePromptConfig:
    return SitePromptConfig(
        brand=values["brand"].strip(),
        language_name=values["language_name"].strip(),
        lang_code=values["lang_code"].strip(),
        h1_text=values["h1_text"].strip(),
        logo_path=values["logo_path"].strip(),
        homepage_banner_path=values["homepage_banner_path"].strip(),
        game_images_dir=values["game_images_dir"].strip(),
        payment_methods_dir=values["payment_methods_dir"].strip(),
        trust_badges_dir=values["trust_badges_dir"].strip(),
        game_providers_dir=values["game_providers_dir"].strip(),
        extra_images_dir=values["extra_images_dir"].strip(),
        homepage_text_source=values["homepage_text_source"].strip(),
        texts_dir=values["texts_dir"].strip(),
        favicon_path=values["favicon_path"].strip(),
        header_footer_color=values["header_footer_color"].strip(),
        header_button_color=values["header_button_color"].strip(),
        cta_color=values["cta_color"].strip(),
        main_background_color=values["main_background_color"].strip(),
        cta_text=values["cta_text"].strip(),
        login_button_text=values["login_button_text"].strip(),
        register_button_text=values["register_button_text"].strip(),
        header_links_text=values["header_links_text"].strip(),
        footer_policy_links=values["footer_policy_links"].strip(),
        redirect_path=values["redirect_path"].strip(),
        redirect_target_url=values["redirect_target_url"].strip(),
        copyright_year=values["copyright_year"].strip(),
        github_repo_name=values["github_repo_name"].strip(),
        trust_links=values["trust_links"].strip(),
        cf_account_id=values["cf_account_id"].strip(),
        cf_zone_id=values["cf_zone_id"].strip(),
        cf_api_token=values["cf_api_token"].strip(),
        custom_domain=values["custom_domain"].strip(),
    )


def simple_slug(value: str) -> str:
    return "-".join(part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in value).split() if part) or "site"


def preview_csv_rows(csv_bytes: bytes, max_rows: int = 20) -> List[dict]:
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for idx, row in enumerate(reader, start=2):
        if len(rows) >= max_rows:
            break
        row_copy = dict(row)
        row_copy["_row"] = idx
        rows.append(row_copy)
    return rows


def build_zip_archive(source_dir: Path, failures: List[dict]) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
        tmp_zip_path = Path(tmp_zip.name)

    try:
        with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(source_dir.parent))

            if failures:
                zf.writestr("generated_pages/failed_jobs.json", json.dumps(failures, ensure_ascii=False, indent=2))

        return tmp_zip_path.read_bytes()
    finally:
        if tmp_zip_path.exists():
            tmp_zip_path.unlink()


def build_zip_from_folder(source_dir: Path, zip_root: str = "project") -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
        tmp_zip_path = Path(tmp_zip.name)

    try:
        with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    rel = file_path.relative_to(source_dir)
                    zf.write(file_path, Path(zip_root) / rel)
        return tmp_zip_path.read_bytes()
    finally:
        if tmp_zip_path.exists():
            tmp_zip_path.unlink()


def render_content_generator_tab() -> None:
    st.subheader("Internal Pages HTML Generator")
    st.caption("Upload CSV, generate HTML pages via Claude API, download one ZIP archive.")

    settings_col1, settings_col2 = st.columns(2)
    with settings_col1:
        api_key = st.text_input("Anthropic API key", type="password", key="content_api_key")
        model = st.text_input("Model", value="auto", key="content_model")
        max_workers = st.slider("Parallel requests", min_value=1, max_value=20, value=5, key="content_workers")
        max_tokens = st.number_input(
            "Max tokens",
            min_value=500,
            max_value=12000,
            value=3500,
            step=100,
            key="content_max_tokens",
        )
    with settings_col2:
        temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.6, step=0.1, key="content_temperature")
        timeout = st.number_input("Timeout (seconds)", min_value=10, max_value=600, value=120, step=10, key="content_timeout")
        retries = st.number_input("Retries", min_value=1, max_value=10, value=4, step=1, key="content_retries")
        max_continuations = st.number_input(
            "Auto-continue chunks",
            min_value=0,
            max_value=10,
            value=3,
            step=1,
            key="content_max_continuations",
        )
        ca_bundle = st.text_input("CA bundle path (optional)", value="", key="content_ca_bundle")

    insecure_no_verify = st.checkbox("Disable SSL verify (unsafe)", value=False, key="content_insecure")

    st.markdown("Fallback page types (used when `page type` is empty/all):")
    fallback_page_types = st.multiselect(
        "",
        options=PAGE_TYPES,
        default=PAGE_TYPES,
        label_visibility="collapsed",
        key="content_page_types",
    )

    st.markdown("Input requirements: `brand`, `geo`, optional `page type`.")
    st.markdown("If `page type` is empty or `all`, generator creates all 9 default pages.")

    input_mode = st.radio(
        "Input mode",
        options=["CSV Upload", "Manual Input"],
        horizontal=True,
        key="content_input_mode",
    )

    uploaded_file = None
    manual_rows: List[dict] = []

    if input_mode == "CSV Upload":
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="content_csv")
        if uploaded_file is not None:
            preview = preview_csv_rows(uploaded_file.getvalue())
            if preview:
                st.dataframe(preview, use_container_width=True)
            else:
                st.warning("CSV has no data rows.")
    else:
        st.caption("Enter rows manually: brand + geo are required, page type is optional.")
        st.session_state.setdefault(
            "content_manual_seed",
            [{"brand": "", "geo": "", "page type": "all"}],
        )
        manual_table = st.data_editor(
            st.session_state["content_manual_seed"],
            num_rows="dynamic",
            use_container_width=True,
            key="content_manual_table",
            column_config={
                "brand": st.column_config.TextColumn("brand"),
                "geo": st.column_config.TextColumn("geo"),
                "page type": st.column_config.TextColumn("page type"),
            },
        )
        if hasattr(manual_table, "to_dict"):
            manual_rows = manual_table.to_dict(orient="records")
        elif isinstance(manual_table, list):
            manual_rows = manual_table

    is_generate_disabled = (
        uploaded_file is None if input_mode == "CSV Upload" else len(manual_rows) == 0
    )
    generate_clicked = st.button("Generate HTML", type="primary", disabled=is_generate_disabled, key="content_generate")

    if not generate_clicked:
        return

    if not api_key.strip():
        st.error("Enter Anthropic API key.")
        return

    if not fallback_page_types:
        st.error("Choose at least one fallback page type.")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        csv_path = tmp_path / "input.csv"
        output_dir = tmp_path / "generated_pages"
        if input_mode == "CSV Upload":
            csv_path.write_bytes(uploaded_file.getvalue())
        else:
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=["brand", "geo", "page type"])
            writer.writeheader()
            for row in manual_rows:
                writer.writerow(
                    {
                        "brand": str((row or {}).get("brand", "")).strip(),
                        "geo": str((row or {}).get("geo", "")).strip(),
                        "page type": str((row or {}).get("page type", "")).strip(),
                    }
                )
            csv_path.write_text(csv_buffer.getvalue(), encoding="utf-8")

        try:
            tasks = parse_csv_tasks(csv_path, fallback_page_types=fallback_page_types)
        except Exception as e:
            st.error(f"CSV parsing error: {e}")
            return

        if not tasks:
            st.error("No valid rows found in CSV.")
            return

        total_jobs = sum(len(task.page_types) for task in tasks)
        st.info(f"Starting generation: {total_jobs} pages from {len(tasks)} task rows.")

        try:
            ssl_context = create_ssl_context(
                ca_bundle_path=Path(ca_bundle).expanduser() if ca_bundle.strip() else None,
                insecure_no_verify=insecure_no_verify,
            )
        except Exception as e:
            st.error(f"SSL setup error: {e}")
            return

        selected_model, available_models, model_note = resolve_model(
            api_key=api_key.strip(),
            requested_model=model.strip() or "auto",
            timeout=int(timeout),
            ssl_context=ssl_context,
        )
        if model_note:
            st.info(model_note)
        if available_models:
            st.caption(f"Using model: {selected_model}")

        progress_bar = st.progress(0.0)
        log_box = st.empty()
        log_lines: List[str] = []

        def on_progress(completed: int, total: int, label: str, ok: bool, message: str) -> None:
            status = "OK" if ok else "FAIL"
            log_lines.append(f"[{completed}/{total}] {status} {label} -> {message}")
            progress_bar.progress(completed / total)
            log_box.code("\n".join(log_lines[-30:]))

        result = run_generation(
            tasks=tasks,
            output_dir=output_dir,
            api_key=api_key.strip(),
            model=selected_model,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            timeout=int(timeout),
            retries=int(retries),
            retry_base_delay=1.5,
            max_workers=int(max_workers),
            ssl_context=ssl_context,
            max_continuations=int(max_continuations),
            progress_callback=on_progress,
        )

        zip_bytes = build_zip_archive(output_dir, result["failures"])

        st.success(
            f"Done. Success: {result['success_count']}/{result['total_jobs']}, "
            f"Failed: {result['failed_count']}"
        )

        st.download_button(
            label="Download generated_pages.zip",
            data=zip_bytes,
            file_name="generated_pages.zip",
            mime="application/zip",
            key="content_download",
        )

        if result["failures"]:
            st.warning("Some jobs failed. `failed_jobs.json` is included in the ZIP.")


def render_codex_site_generator_tab() -> None:
    st.subheader("Codex Site Generator Prompt Pack")
    st.caption("Fill variables once and get 6 ready-to-send prompts for your Codex website workflow.")
    ensure_site_defaults()
    st.session_state.setdefault("site_selected_preset", "(none)")
    st.session_state.setdefault("site_last_selected_preset", "(none)")
    st.session_state.setdefault("site_preset_name", "")

    presets = load_site_presets()
    preset_names = sorted(presets.keys())
    preset_options = ["(none)"] + preset_names
    if st.session_state["site_selected_preset"] not in preset_options:
        st.session_state["site_selected_preset"] = "(none)"

    st.markdown("### Presets")
    preset_cols = st.columns([2, 2, 1, 1, 1])
    with preset_cols[0]:
        selected_preset = st.selectbox(
            "Choose preset",
            options=preset_options,
            key="site_selected_preset",
        )
    with preset_cols[1]:
        if selected_preset != st.session_state.get("site_last_selected_preset"):
            st.session_state["site_last_selected_preset"] = selected_preset
            if selected_preset != "(none)":
                st.session_state["site_preset_name"] = selected_preset
        st.text_input("Preset name", key="site_preset_name")
    with preset_cols[2]:
        load_clicked = st.button("Load", key="site_preset_load")
    with preset_cols[3]:
        save_clicked = st.button("Save", key="site_preset_save")
    with preset_cols[4]:
        delete_clicked = st.button("Delete", key="site_preset_delete")

    if load_clicked:
        if selected_preset == "(none)":
            st.error("Select a preset to load.")
        else:
            apply_site_values(presets[selected_preset])
            st.success(f"Preset '{selected_preset}' loaded.")
            st.rerun()

    if save_clicked:
        preset_name = st.session_state.get("site_preset_name", "").strip()
        if not preset_name:
            st.error("Enter preset name before saving.")
        else:
            presets[preset_name] = current_site_values()
            save_site_presets(presets)
            st.session_state["site_selected_preset"] = preset_name
            st.session_state["site_last_selected_preset"] = preset_name
            st.success(f"Preset '{preset_name}' saved.")
            st.rerun()

    if delete_clicked:
        if selected_preset == "(none)":
            st.error("Select a preset to delete.")
        else:
            if selected_preset in presets:
                del presets[selected_preset]
                save_site_presets(presets)
            st.session_state["site_selected_preset"] = "(none)"
            st.session_state["site_last_selected_preset"] = "(none)"
            st.session_state["site_preset_name"] = ""
            st.success(f"Preset '{selected_preset}' deleted.")
            st.rerun()

    st.markdown("### Variables")
    col1, col2 = st.columns(2)

    with col1:
        st.text_input("Brand", key=_site_key("brand"))
        st.text_input("Language name", key=_site_key("language_name"))
        st.text_input("Lang code", key=_site_key("lang_code"))
        st.text_input("H1 text", key=_site_key("h1_text"))
        st.text_input("CTA text", key=_site_key("cta_text"))
        st.text_input("Login button text", key=_site_key("login_button_text"))
        st.text_input("Registration button text", key=_site_key("register_button_text"))
        st.text_input("Header links", key=_site_key("header_links_text"))
        st.text_input("Footer policy links", key=_site_key("footer_policy_links"))
        st.text_input("Copyright year", key=_site_key("copyright_year"))
        st.text_input("GitHub repository name", key=_site_key("github_repo_name"))
        st.text_input("Cloudflare Account ID", key=_site_key("cf_account_id"))
        st.text_input("Cloudflare Zone ID", key=_site_key("cf_zone_id"))
        st.text_input("Custom domain", key=_site_key("custom_domain"))
        st.text_input("Cloudflare API token", key=_site_key("cf_api_token"), type="password")

    with col2:
        st.text_input("Header/Footer color", key=_site_key("header_footer_color"))
        st.text_input("Header button color", key=_site_key("header_button_color"))
        st.text_input("CTA color", key=_site_key("cta_color"))
        st.text_input("Main background", key=_site_key("main_background_color"))
        st.text_input("Logo path", key=_site_key("logo_path"))
        st.text_input("Homepage banner path", key=_site_key("homepage_banner_path"))
        st.text_input("Favicon path", key=_site_key("favicon_path"))
        st.text_input("Game images path", key=_site_key("game_images_dir"))
        st.text_input("Payment methods path", key=_site_key("payment_methods_dir"))
        st.text_input("Trust badges path", key=_site_key("trust_badges_dir"))
        st.text_input("Game providers path", key=_site_key("game_providers_dir"))
        st.text_input("Extra images path", key=_site_key("extra_images_dir"))
        st.text_input("Homepage text source", key=_site_key("homepage_text_source"))
        st.text_input("Internal texts source", key=_site_key("texts_dir"))

    st.text_input("Redirect path", key=_site_key("redirect_path"))
    st.text_input("Redirect target URL", key=_site_key("redirect_target_url"))
    st.text_area("Trust links (comma separated)", key=_site_key("trust_links"), height=80)

    generate_clicked = st.button("Generate 6 Prompts", type="primary", key="site_generate_prompts")
    if generate_clicked:
        config = build_site_config_from_values(current_site_values())
        prompt_pack = build_codex_prompt_pack(config)
        st.session_state["site_config"] = config
        st.session_state["site_prompt_pack"] = prompt_pack
        st.session_state["site_prompt_pack_version"] = st.session_state.get("site_prompt_pack_version", 0) + 1
        st.session_state.pop("codex_selected_steps", None)
        st.success("Prompt pack generated.")

    if "site_prompt_pack" not in st.session_state or "site_config" not in st.session_state:
        return

    config = st.session_state["site_config"]
    prompt_pack = st.session_state["site_prompt_pack"]
    prompt_pack_version = st.session_state.get("site_prompt_pack_version", 0)
    markdown_output = as_markdown(prompt_pack)

    for idx, (title, prompt) in enumerate(prompt_pack, start=1):
        st.markdown(f"### {idx}. {title}")
        st.text_area(
            label=f"Prompt {idx}",
            value=prompt,
            height=260,
            key=f"prompt_pack_{prompt_pack_version}_{idx}",
        )

    st.download_button(
        label="Download prompt-pack.md",
        data=markdown_output.encode("utf-8"),
        file_name=f"{simple_slug(config.brand)}-codex-prompt-pack.md",
        mime="text/markdown",
        key="download_prompt_pack",
    )

    st.markdown("---")
    st.markdown("### Run These Steps via Codex API")
    st.caption("This will execute selected prompts sequentially and generate a ready website project.")

    run_col1, run_col2 = st.columns(2)
    with run_col1:
        codex_api_key = st.text_input("OpenAI API key", type="password", key="codex_api_key")
        codex_model = st.text_input("Codex model", value="gpt-5-codex", key="codex_model")
        codex_timeout = st.number_input(
            "API timeout per step (seconds)",
            min_value=30,
            max_value=1200,
            value=240,
            step=10,
            key="codex_timeout",
        )
    with run_col2:
        codex_ca_bundle = st.text_input("CA bundle path (optional)", value="", key="codex_ca_bundle")
        codex_insecure = st.checkbox("Disable SSL verify (unsafe)", value=False, key="codex_insecure")
        step_options = [f"{idx}. {title}" for idx, (title, _) in enumerate(prompt_pack, start=1)]
        selected_step_labels = st.multiselect(
            "Which steps to execute",
            options=step_options,
            default=step_options,
            key="codex_selected_steps",
        )

    run_clicked = st.button("Run via Codex API", type="primary", key="codex_run_button")

    if not run_clicked:
        return

    if not codex_api_key.strip():
        st.error("Enter OpenAI API key for Codex execution.")
        return

    if not selected_step_labels:
        st.error("Select at least one step to execute.")
        return

    selected_indices = [int(label.split(".", 1)[0]) - 1 for label in selected_step_labels]
    selected_prompt_pack = [prompt_pack[i] for i in selected_indices if 0 <= i < len(prompt_pack)]

    try:
        ssl_context = create_ssl_context(
            ca_bundle_path=Path(codex_ca_bundle).expanduser() if codex_ca_bundle.strip() else None,
            insecure_no_verify=codex_insecure,
        )
    except Exception as e:
        st.error(f"SSL setup error: {e}")
        return

    progress = st.progress(0.0)
    run_logs = st.empty()
    lines: List[str] = []

    def on_run_progress(done: int, total: int, step_title: str, ok: bool, message: str) -> None:
        status = "OK" if ok else "FAIL"
        lines.append(f"[{done}/{total}] {status} {step_title} -> {message}")
        progress.progress(done / total)
        run_logs.code("\n".join(lines[-40:]))

    try:
        run_result = run_codex_prompt_pack_via_api(
            prompt_pack=selected_prompt_pack,
            api_key=codex_api_key.strip(),
            model=codex_model.strip(),
            timeout=int(codex_timeout),
            ssl_context=ssl_context,
            progress_callback=on_run_progress,
        )
    except Exception as e:
        st.error(f"Codex API run failed: {e}")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        project_dir = tmp_path / "generated_site"
        write_generated_project(run_result.files, project_dir)

        step_log: List[Dict[str, object]] = []
        for item in run_result.step_results:
            step_log.append(
                {
                    "step_number": item.step_number,
                    "title": item.title,
                    "changed_files": item.changed_files,
                    "deleted_files": item.deleted_files,
                    "notes": item.notes,
                    "raw_response_excerpt": item.raw_response_excerpt,
                }
            )

        (project_dir / "codex_step_log.json").write_text(
            json.dumps(step_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (project_dir / "prompts_used.md").write_text(
            as_markdown(run_result.prompts_used),
            encoding="utf-8",
        )

        zip_bytes = build_zip_from_folder(project_dir, zip_root="generated_site")

    st.success(
        f"Codex API run complete. Files generated: {len(run_result.files)}. "
        "Download the project ZIP below."
    )
    st.download_button(
        label="Download generated_site.zip",
        data=zip_bytes,
        file_name=f"{simple_slug(config.brand)}-generated-site.zip",
        mime="application/zip",
        key="codex_download_site_zip",
    )


def main() -> None:
    st.set_page_config(page_title="Internal Pages and Site Prompt Generator", layout="wide")
    st.title("Internal Pages and Site Prompt Generator")

    tab1, tab2 = st.tabs(["HTML Content Generator", "Codex Site Generator"])

    with tab1:
        render_content_generator_tab()

    with tab2:
        render_codex_site_generator_tab()


if __name__ == "__main__":
    main()
