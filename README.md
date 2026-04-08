# Internal Page Generator (Claude API)

Інструмент генерує HTML-контент для внутрішніх сторінок:
- bonus
- app
- login
- contact us
- about us
- bonus policy
- privacy policy
- terms and conditions
- responsible gambling

## Що змінилось

- Прибрано інтеграції з Google Drive та Google Sheets.
- Додано зручний веб-інтерфейс для завантаження CSV і скачування результату одним ZIP.

## 1) Встановлення

```bash
cd "/Users/daniltarasenko/Documents/tonyspins-main/internal page generator"
pip install -r requirements.txt
```

## 2) API ключ

```bash
export ANTHROPIC_API_KEY="your_api_key_here"
```

## 3) Формат CSV

Обов'язкові колонки:
- `brand`
- `geo`

Опційна колонка:
- `page type`

Правила для `page type`:
- `all` або порожньо -> згенерує всі 9 стандартних сторінок
- можна список через `,` `;` `|` (наприклад: `bonus|app|privacy policy`)

Приклад є у файлі `sites.example.csv`.

## 4) Запуск веб-інтерфейсу

```bash
streamlit run streamlit_app.py
```

Після запуску:
- вставляєш Anthropic API key в UI
- обираєш режим вводу: `CSV Upload` або `Manual Input`
- або завантажуєш CSV, або вводиш рядки вручну в таблиці (`brand`, `geo`, `page type`)
- у вкладці `HTML Content Generator` натискаєш `Generate HTML`
- скачуєш `generated_pages.zip`

## 5) Генератор 5 промптів для Codex (нове)

У вкладці `Codex Site Generator`:
- можна зберігати пресети налаштувань (`Save`), завантажувати (`Load`) і видаляти (`Delete`)
- заповнюєш змінні (brand, H1, мова, кольори, шляхи до картинок/папок, redirect URL, repo name)
- натискаєш `Generate 5 Prompts`
- отримуєш 5 готових промптів для workflow генерації сайту
- можеш скачати все одним файлом `prompt-pack.md`

Пресети зберігаються локально у файлі:
- `site_prompt_presets.json` (в корені цього проєкту)

## 6) Автозапуск цих кроків через Codex API

У тій самій вкладці `Codex Site Generator`:
- після генерації prompt pack введи `OpenAI API key`
- задай модель (дефолт `gpt-5-codex`)
- обери кроки, які запускати (1-5)
- натисни `Run via Codex API`

На виході:
- ZIP `generated_site.zip` з файлами сайту
- `codex_step_log.json` з логом змін по кроках
- `prompts_used.md` з фактичними промптами, які були виконані

## 7) Що в ZIP (для HTML Content Generator)

```text
generated_pages/{brand}__{geo}__{task-id}/{page-type}.html
```

Якщо були помилки, всередині також буде:

```text
generated_pages/failed_jobs.json
```

## 8) CLI (опційно)

```bash
python3 generate_internal_pages.py \
  --csv sites.example.csv \
  --output-dir ./generated_pages \
  --max-workers 8
```

Або для одного бренду:

```bash
python3 generate_internal_pages.py \
  --brand "TonySpins" \
  --geo "Ukrainian"
```

За замовчуванням `--model auto`: скрипт сам підбирає модель, яка реально доступна у твоєму Anthropic-акаунті.

Якщо контент обрізається:
- збільш `--max-tokens` (наприклад до `3500-5000`)
- використовуй `--max-continuations 3` або більше (скрипт автоматично дозапитує продовження і склеює текст)

## 9) Якщо бачиш `CERTIFICATE_VERIFY_FAILED`

1. Онови залежності:

```bash
pip install -r requirements.txt --upgrade
```

2. Запусти з кастомним CA bundle (найбезпечніше):

```bash
python3 generate_internal_pages.py \
  --csv sites.example.csv \
  --ca-bundle "$(python3 -c 'import certifi; print(certifi.where())')"
```

3. Тимчасовий debug-варіант (небезпечний, тільки для тесту):

```bash
python3 generate_internal_pages.py \
  --csv sites.example.csv \
  --insecure-no-verify
```

## 10) Якщо бачиш `HTTP 404 model not found`

Це означає, що конкретна модель не підключена у твоєму акаунті.

Рішення:
- використовуй дефолт `--model auto` (рекомендовано), або
- передай явно доступну модель через `--model "..."`
