# План: Мягкая интеграция OpenAI Realtime и веб-авторизации аккаунтов в GPT Mini

- Статус: done (Фазы 1–3 реализованы и задеплоены; Фаза 4 опционально по итогам живой проверки OAuth пользователем)
- Дата: 2026-11-27
- Репозиторий и владелец: `mini-assistant` (`src/openai/`, `src/web/`, `src/main.rs`, `src/config.rs`, `scripts/verify_deploy.sh`) + `gpt-mini` (`docs/`)

---

## Задача и критерии готовности

Добавить в существующий Rust-рантайм `mini-assistant` полноценную работу с **OpenAI (ChatGPT Voice / Realtime)** и удобный браузерный вход в аккаунты (**OpenAI**, **Google Gemini**, **Spotify**) через Web UI `http://10.77.0.111:8080/`, **не ломая текущий рабочий контур Gemini Live, KWS, M-AEC и Spotify Connect**.

В каждый момент времени на колонке работает строго **один** активный голосовой движок (**Gemini Live** *или* **OpenAI ChatGPT Voice**, одновременная работа двух облачных сессий исключена); на главной странице `http://10.77.0.111:8080/` расположен явный переключатель выбора, кто сейчас отвечает пользователю.

Вместо перепрошивки памяти устройства или переписывания проекта с нуля используется поэтапная доработка уже заложенной в коде мульти-провайдерной архитектуры (`VoiceProvider`, `OpenAiRealtimeClient`, `ControlCenterServer`): все провайдеры скомпилированы в одном бинарнике, а переключение и авторизация происходят через конфигурацию и защищённое хранилище `credentials.json`.

### Критерии готовности:
1. **Паритет OpenAI и Gemini:** при активном `provider = "openai"` голосовой диалог работает без искажения темпа (корректный апсемплинг `16 кГц → 24 кГц`), работают прерывания (barge-in) и все локальные инструменты (Home Assistant, Spotify, громкость, будильники, погода, Bluetooth, `stop_dialogue`).
2. **Неубиваемый Web UI `:8080`:** даже если ключ/токен провайдера отсутствует, истёк или отклонён облаком, `mini-assistant` не уходит в crash-loop до запуска веб-сервера — Web UI `:8080`, будильники и Spotify остаются доступны для входа и восстановления.
3. **Защищённое хранилище учётных данных:** единый `credentials.json` (`chmod 0600`, атомарная запись, в `.gitignore` обоих репо) с обратной совместимостью с существующими `.env`, `config.toml` и `spotify_token.txt`.
4. **Веб-авторизация без SSH:** через `http://<ip>:8080/` пользователь (Owner-only) может подключить OpenAI (OAuth Device Code / PKCE / API Key), Gemini и Spotify; перед сменой провайдера колонка проверяет токен рукопожатием (`verify_handshake`), чтобы не переключаться на нерабочую конфигурацию.
5. **Нулевая регрессия:** после каждой фазы проходит `./scripts/check.sh` (все 5 этапов), `./scripts/verify_deploy.sh` адаптирован под оба провайдера, а возврат на `Gemini Live` работает в один клик.

---

## Исходное состояние и ограничения (результаты аудита кода)

### Что УЖЕ есть в коде (не переписывать с нуля):
- `src/config.rs`: `VoiceProvider::{Gemini, Openai}`, `OpenAiConfig`, `Config::voice_settings()`.
- `src/openai/realtime_client.rs`: базовый `OpenAiRealtimeClient` (`verify_handshake`, `connect`, `stop`, `convert_gemini_tool_to_openai`).
- `src/main.rs`: `enum VoiceClient { Gemini(...), Openai(...) }`, ветвление в `run_preflight_check()` и основном цикле.
- `src/web/dashboard.html` и `src/web/mod.rs`: вкладки **Google Gemini Live / OpenAI ChatGPT Voice**, сетка 8 голосов OpenAI, `handle_api_voice()` с обновлением `config.toml` и рестартом под `run-supervisor.sh`.
- `src/web/mod.rs` и `src/spotify/crypto.rs`: готовая инфраструктура OAuth PKCE (`S256`) для Spotify (`/spotify/login`, `/spotify/callback`).

### Точно выявленные разрывы и баги:
1. **Несовпадение частоты аудио (`src/openai/realtime_client.rs:584`):** локальный `InputGate` в `src/main.rs:1171` отдаёт PCM16 **16 кГц**. Gemini Live принимает `16 кГц`, а OpenAI Realtime (`input_audio_format: "pcm16"`) требует **24 кГц**. Сейчас 16 кГц байты уходят в OpenAI без ресемплинга.
2. **Инструменты отключены для OpenAI и расходятся по схеме (`src/main.rs:163, 412`, `src/openai/realtime_client.rs:369, 382`):**
   - `main.rs:412` жёстко отключает все инструменты: `provider == VoiceProvider::Gemini`.
   - `realtime_client.rs:369` объявляет `"service_data"` вместо `"parameters"` (как ждёт `main.rs:1031`), а `382` объявляет `"hours"` вместо `"hours_ago"` (как ждёт `main.rs:1101`).
   - В `realtime_client.rs` не реализовано прерывание ответа (`response.cancel` + `input_audio_buffer.clear` + `on_interrupted`), не передаётся `suppress_followup` и не обрабатываются альтернативные имена событий `response.output_audio.delta/done`.
3. **Замок Web UI при отсутствии ключа (`src/main.rs:394–406, 571–624, 1785`):** проверка `voice.api_key` и выход при ошибке `connect()` выполняются **до** старта `ControlCenterServer` (`:8080`) или обрывают весь процесс. При переключении на провайдера без валидного ключа пользователь теряет доступ к Web UI.
4. **Ограничение OpenAI OAuth «Use your ChatGPT plan» vs Realtime API и LAN IP:**
   - В OAuth-потоке на LAN-адресе (`http://10.77.0.111:8080/`) провайдеры (OpenAI/Google/Spotify) обычно отклоняют небезопасные `http://<LAN-IP>` в `redirect_uri`, разрешая `http://127.0.0.1/...` или `Device Code Flow`. Если браузер ноутбука редиректнется на `127.0.0.1`, он попадёт на сам ноутбук, а не на колонку. Поэтому в UI нужны **Device Code Flow** и **ручная вставка URL/кода** как резерв, плюс ввод API-ключа.
   - Потребительская подписка ChatGPT (scope `chatgpt.tokens.use.direct`) официально покрывает текстовые/агентные вызовы (Responses API), тогда как OpenAI Realtime WebSocket API исторически тарифицируется через API-биллинг OpenAI Platform. Проверка конкретного аккаунта и режима выполняется рукопожатием в Фазе 3, с опциональным fallback в Фазе 4 при необходимости.
5. **Скрипт проверки деплоя (`scripts/verify_deploy.sh:124`):** жёстко ищет в логе `setupComplete confirmed` (маркер Gemini), что даст ложный `FAIL` при активном OpenAI.
6. **Правило `.gitignore`:** явно внести `*credentials*.json` и `credentials.json` в `.gitignore` обоих репозиториев до создания хранилища на устройстве.

---

## Шаги (4 изолированные фазы по правилу Single-Task)

Каждая фаза оформляется отдельным набором правок, тестом, сборкой и коммитом. Переход к следующей фазе — только после полного прохождения проверок предыдущей.

### Фаза 1: Доводка `OpenAiRealtimeClient` до полного паритета с Gemini (без ломки Gemini)
- [x] **1.1. Ресемплер `16 kHz → 24 kHz` PCM16** внутри `src/openai/realtime_client.rs` (линейная интерполяция `2:3` с сохранением последнего сэмпла между чанками) только для потока в OpenAI; тракт ALSA/M-AEC/KWS/Gemini остаётся нетронутым на 16 кГц.
- [x] **1.2. Выравнивание схемы и обработчика инструментов:**
  - В `src/openai/realtime_client.rs` привести `control_home_device` (`parameters`) и `get_device_history` (`hours_ago`) к точному контракту `src/main.rs` и `src/gemini/live_client.rs`.
  - В `src/main.rs:163` и `src/main.rs:412` убрать ограничение `provider == VoiceProvider::Gemini` для `tools_allowed` и `--check` (учитывая `conversation_only`).
- [x] **1.3. Barge-in, отмена ответа и события протокола:**
  - Обработать отмену хода (`TurnAuthorization::is_current`), вызов `on_interrupted()`, отправку `response.cancel` + `input_audio_buffer.clear` при перебивании/отмене; подключить `suppress_followup` при завершении диалога.
  - Принимать как `response.audio.delta/done`, так и `response.output_audio.delta/done`; санитизировать ошибки (без утечки ключей/токенов в лог).
- [x] **1.4. Адаптация `scripts/verify_deploy.sh`:** определять `provider` из `config.toml` на Mini и проверять релевантный маркер рукопожатия (`setupComplete confirmed` для Gemini или `OpenAI Realtime setup handshake completed successfully` для OpenAI).
- [x] **1.5. Тесты и проверка Фазы 1:** unit-тесты ресемплера `16k→24k`, barge-in/cancel, совпадения имён/полей тулов с диспетчером `main.rs`, mock-WS жизненного цикла `OpenAiRealtimeClient`, `./scripts/check.sh` PASS.

### Фаза 2: Безопасный порядок старта Web UI `:8080` и хранилище `credentials.json`
- [x] **2.1. Изоляция в `.gitignore`:** добавить `*credentials*.json` и `credentials.json` в `gpt-mini/.gitignore` и `mini-assistant/.gitignore`.
- [x] **2.2. Модуль `src/credentials.rs`:**
  - Хранение секретов и OAuth-сессий в `/bkupgrade/data/opt/mini-assistant/credentials.json` (переопределяется через `MINI_CREDENTIALS_PATH` для тестов/локали), атомарная запись (`tmp` → `rename`, права `0600` на Unix).
  - Поддержка провайдеров `gemini`, `openai`, `spotify`: хранение `auth_mode` (`api_key` | `oauth`), `api_key`, `access_token`, `refresh_token`, `client_id`, `expires_at`, несекретной метки `account_label`.
  - Единый приоритет чтения без разрушения старых инсталляций: `credentials.json` → `config.toml` → `.env`.
- [x] **2.3. Неубиваемый старт `:8080` в `src/main.rs`:**
  - Запускать `ControlCenterServer` (`:8080`), LED, громкость, будильники и `SoloistClient` **до** проверки облачных ключей и запуска голосового клиента.
  - При отсутствии ключа или ошибке handshake голосовой контур переходит в наблюдаемое состояние `needs_auth` / `auth_error`, не завершая процесс `mini-assistant` и не отключая Web UI.
  - Публиковать в `GET /api/v1/status` безопасное состояние `voice_status` и маску настроенных провайдеров (без самих ключей/токенов).
- [x] **2.4. Тесты и проверка Фазы 2:** unit-тесты `CredentialsStore` (`0600`, атомарное обновление, чтение с fallback на `.env`), интеграционный HTTP-тест старта Web UI без ключей, `./scripts/check.sh` + деплой + `./scripts/verify_deploy.sh`.

### Фаза 3: Веб-авторизация (OpenAI + Gemini + Spotify) и проверка до переключения
- [x] **3.1. Серверный Auth/OAuth API в `src/web/auth_providers.rs` + `src/web/mod.rs` (строго Owner-only в `src/web/auth.rs`):**
  - `GET /api/v1/auth/status`: статус подключения `openai`, `gemini`, `spotify` (`configured`, `auth_mode`, `account_label`, `expires_at`, статус активной device-code сессии — без секретов).
  - **OpenAI OAuth Device Code Flow** (`POST /api/v1/auth/openai/device/start`, `GET /api/v1/auth/openai/device/poll`): запрос кода на `auth.openai.com`, показ короткого кода пользователю в Web UI и фоновый обмен на `access_token` + `refresh_token`.
  - **OpenAI PKCE Flow + `chatgpt.tokens.use.direct`** (`GET /api/v1/auth/openai/login`, `POST /api/v1/auth/openai/complete`): динамическая регистрация/конфигурируемый `client_id` + резервная вставка финального callback URL/кода в UI для обхода ограничений LAN IP в браузере.
  - **Ручной ввод / обновление ключа и Client ID** (`POST /api/v1/auth/key`): безопасное сохранение `openai` API Key, `gemini` API Key, `spotify.client_id` в `credentials.json`.
  - **Отключение аккаунта** (`POST /api/v1/auth/logout`): очистка записи провайдера в `credentials.json`.
  - **Автообновление OAuth access token** (`refresh_token`) перед подключением `OpenAiRealtimeClient` с сохранением нового токена на диск.
- [x] **3.2. Безопасное переключение провайдера (`POST /api/v1/voice`):**
  - Проверять наличие учётных данных через `CredentialsStore` для **обоих** провайдеров (Gemini и OpenAI).
  - Выполнять пробный `verify_handshake` (таймаут 10 с) **до** перезаписи `config.toml` и рестарта процесса — при отказе (например, неверный ключ или запрет Realtime на подписке) сразу возвращать понятную причину в UI, оставляя работающий сейчас провайдер активным.
  - Обновить карточку Spotify: вывести кнопку входа Spotify PKCE и настройку `client_id` прямо в `dashboard.html` (переиспользуя уже работающие `/spotify/login` и `/spotify/callback`).
- [x] **3.3. Обновление `src/web/dashboard.html`:**
  - Блок «Аккаунты и авторизация» на главной панели и контекстная плашка под переключателем `Google Gemini Live` ⟷ `OpenAI ChatGPT Voice`.
  - Прозрачный статус готовности до нажатия «Сохранить», UI для Device Code («Перейдите по ссылке и введите код XXXX-XXXX»), вставки ключа и выхода.
- [x] **3.4. Тесты и боевая проверка Фазы 3:** тесты прав доступа в `auth.rs` (Calibration/Anonymous получают `401/403` на `/api/v1/auth/*`), mock-OAuth и mock-`verify_handshake` при переключении, проверка на живом Mini входа и переключения `Gemini ⟷ OpenAI`.

### Фаза 4 (опционально, по итогам живой проверки Фазы 3): Pipeline для подписки без Realtime-доступа
- [ ] Выполняется **только если** в Фазе 3 OAuth-токен `chatgpt.tokens.use.direct` будет успешно получен от OpenAI, но `wss://api.openai.com/v1/realtime` отклонит его с `401/403` (требуя отдельный API-биллинг Platform).
- [ ] В этом случае без изменения существующих `GeminiLiveClient` и `OpenAiRealtimeClient` добавляется альтернативный бэкенд `OpenAiPlanPipeline` на `/v1/responses` (речь пользователя ➔ транскрибация ➔ `Responses API` по подписке с общими тулами HA/Spotify ➔ озвучка), включаемый автоматически или в настройках при использовании OAuth подписки без Realtime.

---

## Проверки, результаты и ограничения

- Обязательный локальный gate после каждой фазы: `cd mini-assistant && ./scripts/check.sh` (format, clippy `-D warnings`, unit/integration tests, vendor, python tests).
- Проверка на ARM32-устройстве: `./scripts/build.sh` (Docker `armv7-unknown-linux-musleabihf`) → `./scripts/deploy.sh` → `./scripts/verify_deploy.sh` (`PASS` по всем пунктам + контроль `MemAvailable > 40 MB` при 236 MiB RAM).
- Никаких секретов, токенов и содержимого `.env`/`credentials.json` в Git, логах и отчётах.

---

## Откат и открытые вопросы

- **Откат кода и устройства:** каждая фаза — отдельный атомарный коммит; при проблемах откат выполняется `git revert <sha>` или на колонке через `mv mini-assistant.prev mini-assistant && /etc/init.d/S99mini_assistant restart`. Существующие `.env`, `config.toml`, `keyword.rpw` и `spotify_token.txt` не затрагиваются и не перезаписываются деплоем.
- **Открытый вопрос для проверки на живом стенде в Фазе 3:**
  1. Примет ли `wss://api.openai.com/v1/realtime` OAuth-токен подписки ChatGPT Plus/Pro с scope `chatgpt.tokens.use.direct`, или OpenAI ограничит этот токен только `/v1/responses` (определяет необходимость Фазы 4).
  2. Поддержка Device Code Flow на вашем личном аккаунте ChatGPT требует одноразового включения тумблера `Enable device code sign-in` в `ChatGPT Settings → Security and login` (документируем это прямо в интерфейсе на `:8080`).
