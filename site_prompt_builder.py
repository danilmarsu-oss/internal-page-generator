#!/usr/bin/env python3
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class SitePromptConfig:
    brand: str
    language_name: str
    lang_code: str
    h1_text: str
    logo_path: str
    homepage_banner_path: str
    game_images_dir: str
    payment_methods_dir: str
    trust_badges_dir: str
    game_providers_dir: str
    extra_images_dir: str
    homepage_text_source: str
    texts_dir: str
    favicon_path: str
    header_footer_color: str
    header_button_color: str
    cta_color: str
    main_background_color: str
    cta_text: str
    login_button_text: str
    register_button_text: str
    header_links_text: str
    footer_policy_links: str
    redirect_path: str
    redirect_target_url: str
    copyright_year: str
    github_repo_name: str
    trust_links: str
    cf_account_id: str
    cf_zone_id: str
    cf_api_token: str
    custom_domain: str


def build_codex_prompt_pack(config: SitePromptConfig) -> List[Tuple[str, str]]:
    prompt_1 = (
        "Привіт! Мені треба, щоб ти зробив домашню сторінку сайту казино.\n\n"
        f"Змінні:\n"
        f"- Brand: {config.brand}\n"
        f"- Мова інтерфейсу: {config.language_name}\n"
        f"- Lang код HTML: {config.lang_code}\n"
        f"- H1: {config.h1_text}\n"
        f"- Лого: {config.logo_path}\n"
        f"- Банер першого екрану: {config.homepage_banner_path}\n"
        f"- Папка ігор: {config.game_images_dir}\n"
        f"- Папка методів оплати: {config.payment_methods_dir}\n"
        f"- Папка trust badges: {config.trust_badges_dir}\n"
        f"- Папка game providers: {config.game_providers_dir}\n"
        f"- Фавікон: {config.favicon_path}\n"
        f"- Колір хедера/футера: {config.header_footer_color}\n"
        f"- Колір кнопок у хедері: {config.header_button_color}\n"
        f"- Колір CTA кнопки: {config.cta_color}\n"
        f"- Main background: {config.main_background_color}\n"
        f"- Текст CTA: {config.cta_text}\n"
        f"- Текст кнопки Login: {config.login_button_text}\n"
        f"- Текст кнопки Registration: {config.register_button_text}\n"
        f"- Лінки в хедері: {config.header_links_text}\n"
        f"- Лінки в футері: {config.footer_policy_links}\n"
        f"- Лінки trust організацій: {config.trust_links}\n\n"
        "Вимоги до home page:\n"
        "1. Зроби хедер і футер у заданому кольорі.\n"
        "2. У хедері додай кнопки логіну і реєстрації у заданому кольорі.\n"
        "3. У хедері додай лого.\n"
        "4. На першому екрані постав H1 і банер.\n"
        "5. Під банером по центру додай пульсуючу CTA кнопку заданого кольору.\n"
        "6. Додай блок ігор: 2 ряди по 5 квадратів, картинки бери з папки ігор.\n"
        "7. Додай SEO блок з h2/h3, bulleted list, numbered list і table.\n"
        "8. Додай блок з картинками payment methods.\n"
        "9. Додай блок з 3 відгуками.\n"
        "10. Додай FAQ accordion.\n"
        "11. Над футером додай блок 'Page updated:' мовою сайту + сьогоднішня дата.\n"
        "12. У футері додай trust badges з клікабельними лінками trust організацій.\n"
        "13. У футері додай policy лінки.\n"
        "14. У футері нижче додай картинки провайдерів з папки game providers.\n"
        f"15. Додай copyright: {config.copyright_year} {config.brand} Casino. All rights reserved. "
        "переклади мовою сайту.\n"
        "16. Зроби адаптивно (desktop/mobile), чистий HTML/CSS/JS без сторонніх бібліотек.\n"
        "17. Для мобільної версії зроби компактний хедер: сховай внутрішні навігаційні лінки, "
        "залиш тільки маленьке лого та кнопки Login/Register; хедер має займати мінімум місця по висоті."
    )

    prompt_2 = (
        "Тепер візьми текст із джерела home page і опублікуй його на головній сторінці замість поточного SEO-контенту.\n"
        f"Джерело тексту: {config.homepage_text_source}\n"
        f"Додаткові картинки для вставки в релевантні місця: {config.extra_images_dir}\n\n"
        "Критично важливо:\n"
        "1. Опублікуй весь текст повністю, не обрізай.\n"
        "2. Не видаляй уже наявні блоки: банер, CTA, grid ігор, payment methods, reviews, FAQ.\n"
        "3. Інтегруй новий текст в існуючу структуру й стилі, без ламання верстки.\n"
        "4. Reviews і FAQ блоки мають бути заповнені контентом саме з документа "
        f"`{config.homepage_text_source}` (тобто з `{config.brand} homepage.txt`, якщо так названо файл).\n"
        "5. Не дублюй reviews і FAQ: на сторінці має бути тільки один reviews-блок і один FAQ-блок.\n"
        "6. Контент, який ти виніс у reviews/FAQ блоки з джерела, не повторюй вдруге в SEO-блоці."
    )

    prompt_3 = (
        "Тепер зроби окрему сторінку під кожен текст із папки текстів і простав посилання в релевантні кнопки хедера/футера.\n"
        f"Папка з текстами: {config.texts_dir}\n"
        f"Lang код сторінок: {config.lang_code}\n\n"
        "Правила:\n"
        "1. Не створюй сторінку для homepage (він уже на головній).\n"
        "2. Кожна сторінка має мати таку саму стилістику як home, включно з хедером і футером.\n"
        "3. Структура файлів: `page-slug/index.html`.\n"
        "4. На кожній сторінці canonical має бути self-referencing.\n"
        "5. Додай коректні внутрішні лінки між сторінками через відповідні елементи меню."
    )

    prompt_4 = (
        "Зроби фінальні технічні задачі:\n"
        "1. Додай форму логіну на сторінку login.\n"
        "2. Додай форму контактів на сторінку contact us.\n"
        "3. Створи файл `_redirects` з 301 редіректом:\n"
        f"   {config.redirect_path} {config.redirect_target_url} 301\n"
        f"4. Простав посилання `{config.redirect_path}` на кнопку реєстрації та головну CTA кнопку.\n"
        "5. Перевір, щоб усі сторінки збирались без помилок, а всі лінки відкривались."
    )

    prompt_5 = (
        "Опублікуй готовий сайт на GitHub.\n"
        f"Назва репозиторію: {config.github_repo_name}\n\n"
        "Кроки:\n"
        "1. Ініціалізуй git репозиторій (якщо ще нема).\n"
        "2. Додай усі файли, зроби змістовний коміт.\n"
        "3. Створи віддалений GitHub repo з назвою вище.\n"
        "4. Запуш основну гілку.\n"
        "5. Поверни URL репозиторію та короткий changelog."
    )

    prompt_6 = (
        "Тепер виконай деплой у production через Cloudflare Pages.\n\n"
        "Змінні для Cloudflare API:\n"
        f"- Cloudflare Account ID: {config.cf_account_id}\n"
        f"- Cloudflare Zone ID: {config.cf_zone_id}\n"
        f"- Cloudflare API Token: {config.cf_api_token}\n"
        f"- Custom Domain: {config.custom_domain}\n"
        f"- GitHub repository: {config.github_repo_name}\n\n"
        "Задача:\n"
        "1. Підключись до Cloudflare по API.\n"
        "2. Створи або онови Cloudflare Pages project для цього репозиторію.\n"
        "3. Залий сайт із GitHub repo (production deploy).\n"
        "4. Підключи custom domain до цього Pages project.\n"
        "5. Додай/перевір DNS записи в зоні (через Zone ID), щоб домен вів на Pages.\n"
        "6. Перевір, що сайт відкривається по кастомному домену.\n"
        "7. Поверни у відповіді: Pages project name, production URL, custom domain status, "
        "що саме було створено/оновлено в Cloudflare."
    )

    return [
        ("Prompt 1 - Build Homepage", prompt_1),
        ("Prompt 2 - Inject Homepage Content", prompt_2),
        ("Prompt 3 - Create Internal Pages", prompt_3),
        ("Prompt 4 - Forms and Redirects", prompt_4),
        ("Prompt 5 - Publish to GitHub", prompt_5),
        ("Prompt 6 - Deploy to Cloudflare Pages", prompt_6),
    ]


def as_markdown(prompt_pack: List[Tuple[str, str]]) -> str:
    blocks = []
    for idx, (title, prompt) in enumerate(prompt_pack, start=1):
        blocks.append(f"## {idx}. {title}\n\n{prompt}")
    return "\n\n".join(blocks) + "\n"
