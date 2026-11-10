# План: Подготовка публичного GitHub-релиза и оформление портфолио проекта GPT Mini

- Статус: planned
- Дата: 2026-11-10
- Владелец: gpt-mini team

## Цель

Оформить репозиторий `gpt-mini` как эталонный open-source проект уровня Senior Systems / Embedded / AI Engineer для публикации в персональном GitHub-аккаунте пользователя. Проект должен демонстрировать высший уровень инженерной культуры: глубокий реверс-инжиниринг железа, чистую архитектуру на Rust, абсолютную безопасность от утечек приватных данных и исчерпывающую документацию на двух языках (английском и русском).

---

## 1. Аудит безопасности и очистка секретов (Zero-Leak Policy)

Перед любой публичной публикацией или демонстрацией репозитория:
1. **Проверка `.gitignore`:**
   - Строгая изоляция `.env`, `*.env.*`, `*.rpw`, `*.key`, `*.pem`, `id_rsa*`, `client_ed25519*`, `*.log`, `*.pcap`, `*.dump`, кэшей `target/`, `soloist-data/`, `spotify_cache/`.
2. **Глубокий аудит истории Git (Secret Scrubbing):**
   - Проверка всей истории коммитов с помощью автоматических сканеров (типа `gitleaks`) на предмет случайного попадания токенов Home Assistant, API-ключей Google AI Studio, паролей Spotify или приватных IP-адресов.
   - При обнаружении исторических артефактов — чистка истории через `git-filter-repo` с заменой на плейсхолдеры.
3. **Эталонные шаблоны конфигурации:**
   - `.env.example` — содержит только безопасные описательные переменные-заглушки с инструкцией, как получить токен.
   - `config.example.toml` — чистый документированный TOML со всеми дефолтными значениями.

---

## 2. Презентабельный README.md (English & Russian)

Файл `README.md` формируется как визитная карточка проекта:
1. **Hero-секция:**
   - Название: **`GPT Mini` — Fully Autonomous Open-Source Rust Voice Assistant Firmware for Yandex Station Mini 1**.
   - Бейджи: `Rust 2021`, `Target: armv7-unknown-linux-musleabihf`, `Gemini Live API`, `OpenAI Realtime`, `Spotify Connect`, `Home Assistant`, `License: MIT/Apache-2.0`.
2. **Ключевые инженерные достижения (Highlights):**
   - **Pure Rust Userspace:** Полная замена проприетарного стека без vendor blob-демонов в runtime.
   - **Direct Hardware Interfacing:**
     - Собственный загрузчик Broadcom BCM43430 firmware и аттачер дисциплины ядра `N_HCI` (`bcm-attach`) на чистом Rust.
     - 8-канальный PDM аудио-дециматор микрофонов (`hw:0,2` S32_LE $\to$ 16 кГц PCM16).
     - Драйвер I2C LED контроллера SN3236 и ToF радара жестов VL53L0.
   - **Мульти-модельный голосовой движок:** Двусторонние WebSockets с потоковым аудио 24 кГц к Gemini Live и OpenAI Realtime API.
   - **Acoustic Barge-in & Proportional Ducking:** Прерывание речи и динамическое приглушение фоновой музыки без эха.
   - **Control Center & Telegram Mini App:** Управление голосом, цветом светодиода и обучением wake word прямо с телефона.
   - **Deep Research & Telegram Forum Topics:** Длительный веб-поиск цен и новостей с отправкой отчётов в Telegram-форум.
3. **Архитектурные диаграммы (Mermaid):**
   - Схема слоёв: Железо $\to$ Linux 4.9.68 $\to$ Rust Runtime $\to$ Облачные API $\to$ Telegram/Web UI.
4. **Спецификация железа (Hardware Architecture):**
   - SoC: Amlogic A113X (4x Cortex-A53, 32-bit armhf userspace, 236 MiB RAM).
   - Audio: PDM mic array + Texas Instruments TAS5707 I2S amp.
   - Radio: Broadcom BCM43430 (Wi-Fi 802.11n + Bluetooth 4.1).
   - Sensors: ST VL53L0X ToF proximity, SN3236 LED matrix.
5. **Инструкция по сборке и установке:**
   - Кросс-компиляция в одну команду через Docker (`messense/rust-musl-cross:armv7-musleabihf`).
   - Деплой по сети через `./scripts/deploy.sh`.

---

## 3. GitHub Actions CI/CD Workflow (`.github/workflows/ci.yml`)

Для подтверждения профессионального качества кода на GitHub:
1. `cargo test --locked` (все 198+ юнит-тестов зеленые).
2. `cargo clippy --all-targets -- -D warnings` (zero warnings policy).
3. `cargo fmt -- --check` (идеальное форматирование).
4. `cargo build --target armv7-unknown-linux-musleabihf --release` (кросс-сборка артефактов в GitHub Actions).
