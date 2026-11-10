# Глубокое ревью GPT Mini — 2026-11-01

## Вывод

Workflow применим, но прежние зелёные проверки не доказывали готовность
ассистента. Исходные 15 Rust-тестов не покрывали реальный HA HTTP-контракт,
разрешения executor, deployment errors и ключевые события/ошибки аудио.
Ревью выявило воспроизводимые дефекты; ограниченные исправления и новые
проверки внесены. Полный голосовой цикл по-прежнему не готов к deployment.

Изменения в этом ревью не запускались на Mini, не меняли её питание,
маршрутизацию, NAT, DNS, SSH, firmware или аккаунты. Loopback fixtures и
Docker build не обращались к настоящему HA, микрофону или облачным API.

## Исходное состояние и метод

Root HEAD перед ревью: `cab9e6f`; приложение: `6b93d20`.
Уже существовавшие dirty-файлы: `src/audio/playback.rs`,
`config.example.toml`, `docs/experiments/2026-11-01-initial-device-smoke-test.md`.
Их изменения сохранены; к журналу добавлены явно отделённые уточнения.

Три независимых направления: audio/Live, HA/config, workflow/deployment.
Подтверждения получены unit/contract tests, настоящими loopback HTTP fixtures,
fake Docker/SSH/SCP и отдельной копией исходников. Второе ревью проверило
новые HA/deployment исправления. Приложенный пользователем журнал разобран
как историческое сообщение автора, не как результат сегодняшнего запуска.

## Исправленные дефекты

| Область | Подтверждённая проблема | Результат |
|---|---|---|
| VQE parser | `offset + length`/varint overflow, panic на повреждённом payload | Checked arithmetic, bounded wire reader и regression tests |
| VQE selection | Неправильный rate/format и нечётные/пустые данные принимались как нужный PCM | Явные16000 Hz/PCM1, размер/выравнивание; неизвестные wire fields безопасно пропускаются |
| Gemini | Interruption читался на верхнем уровне вместо `serverContent.interrupted`; binary JSON игнорировался | Исправлены декодирование и fixtures text/binary |
| Логи | Transcript, raw JSON, tool arguments, roster/payload попадали в log | Убраны чувствительные payload; оставлены структурные события |
| HA policy | Модель могла выбрать произвольный домен/сервис/target с полным токеном | Explicit entity allowlist, допустимые light/switch/climate services, typed parameters и запрет широких selectors |
| HA history | Unix seconds вместо ISO, HTTP error мог стать успешным ответом | RFC3339, явное окно1–168 ч, status checks,5 s timeout и1 MiB response cap |
| HA action result | Changed states вне разрешённого списка могли уйти в LLM | Минимальный `{accepted:true}`; это приём сервером, не доказательство физического действия |
| Deployment | `source .env` исполнял command substitution | Dotenv разбирается как данные, без source/eval |
| Deployment | Отказ upload маскировался под отсутствие файла и общий успех | Fail-fast на upload/chmod, remote directory0700 и env0600 |
| Секреты | Вложенный Git не игнорировал `.env.local/.env.production` | Добавлено `.env.*`, сохранён безопасный `.env.example` |

В отдельной копии старого audio-кода четыре дополнительные проверки
воспроизвели реальные отказы до исправления. Они не являлись падением
базовых 15 тестов: именно поэтому одного зелёного baseline было недостаточно.

## Выполненные проверки

| Проверка | Фактический результат |
|---|---|
| `mini-assistant/scripts/check.sh`: rustfmt | PASS |
| Clippy `--locked --all-targets -- -D warnings` | PASS |
| Rust unit/contract/loopback HTTP tests |32 passed |
| Python fake-deployment tests |8 passed |
| Root workflow guard tests |8 passed |
| Research runtime Python suite |80 passed,1 Linux-only skip на Mac |
| Research lab/tools Python suite |18 passed |
| Strict host C core/CLI tests |15 групп passed |
| Shell syntax и CI YAML | PASS |
| ARM32 release build | PASS, Docker network=none, cargo --locked --offline |

`bind` loopback в песочнице первоначально запрещён средой. HTTP fixtures
затем реально выполнены с разрешением локального bind; этот отказ не
объявлялся ошибкой HA и не заменялся успешным skip. Сетевых HA-действий нет.
GitHub runners и реальный Linux/ALSA runtime в этой итерации не запускались.

## ARM-артефакт

Чистая временная копия содержала только Cargo manifests/lock, `src/` и
публичный config template — без `.env` и приватных ключей. После сборки
подтверждено побайтовое совпадение snapshot с проверенным деревом исходников.

- Target: `armv7-unknown-linux-musleabihf`.
- Формат: ELF32 little-endian ARM, EABI5, static, stripped.
- Размер:2 404 964байта; не измерение RSS.
- SHA256: `816c7f599db5483e3e05b28a9745b7adc64cbc249771226b2ef7708b5b7655b0`.
- ELF inspection: PT_INTERP/DT_NEEDED отсутствуют, ABI_VFP_args=AAPCS VFP.
- Local Docker image ID: `16708215d78d5859dffa0429267808c91c11a834f227cbb742727f189cfe1365`.
- Manifest исходных hashes и бинарь сохранены приватно в
  `.private/alice-mini/reviews/2026-11-01/`; на Mini не копировались.

Совместимость syscalls с её конкретным ядром, RAM, стабильность, качество
акустики и задержка диалога этой сборкой не доказаны.

## Открытые blockers и следующие шаги

1. **P1 — playback cancel.** `interrupt()` ставит atomic flag, но worker может
   ждать следующий chunk или блокироваться на pipe write; следующий `play()`
   сбрасывает flag. Fake-aplay опыт показал живой дочерний процесс через 150 мс
   после interrupt без новых данных. Нужны отдельная control queue, cancellation
   priority, очистка старой очереди/turn IDs, bounded write и проверка cleanup.
2. **P1 — setup handshake.** До отправки микрофона нужно дождаться
   `setupComplete` с deadline и обработкой отказа. Сейчас отправка начинается
   после записи setup, без подтверждения его принятия.
3. **P1 — input privacy/gate.** Wake/VAD не подключён в main: capture идёт
   в облачный маршрут после старта. Нужен явный режим/локальный gate и тест,
   доказывающий отсутствие отправки речи до выбранного условия активации.
4. **Контракт VQE PCM.** Rate16000/format1 не доказывают signedness/endian/mono.
   До реальной передачи речи подтвердить sample representation и при
   необходимости добавить преобразование. Переименование канала это не решает.
5. **P2 — supervision.** Detached WebSocket tasks не управляют readiness/main;
   EOF/error, reconnect и остановка capture/playback нуждаются в одном lifecycle.
6. **P2 — tool wait.** Ожидание HA tool reply в reader блокирует приём новых
   interruption/cancellation events. Нужны отдельный dispatcher и deadlines.
7. **Deployment.** Теперь ошибку видно, но rollout ещё не атомарный: отказ
   после замены бинаря может оставить смешанный набор. Staging, hashes,
   backup/rollback и проверка установленного набора — отдельный следующий шаг.

Для нового HA-клиента требуются реальные `ha.allowed_entities` в локальном
config. Без списка tools отключены. Локальные credentials/config в ревью
не переписывались. До закрытия blockers автоматический deployment не выполнять.

## Коррекции Markdown и работа агентов

AGENTS/WORKFLOW/CODE_REVIEW сохранены и уточнены: единственный владелец Git
при параллельной работе; никакого общего checkout чужого src; безопасный dotenv;
loopback fixtures отделены от настоящих API; учитываются все сетевые side effects.
Шаблон опыта требует действительный hash/исход/откат, не словесное «проверено».

README/SETUP теперь показывают реальный статус: wake-word, Spotify, LED,
кнопки, OpenAI/вход в ChatGPT, долговременная память и замена maind не выданы
за готовые функции. Добавлена отсутствовавшая архитектурная документация.
Исторический эксперимент отдельно помечает недостаток сетевого rollback,
конфликт версии ядра и недоказанность гарантированного восстановления SSH.

Markdown задаёт правила, а не гарантирует их исполнение. Hook/CI помогают
обеспечить часть правил; обязательные contract tests, независимое ревью и
свежий hardware evidence остаются необходимыми. Корневой guard проверяет
свой Git-индекс и не является secret scanner вложенного репозитория.

## Первичные контракты

- [Gemini Live API](https://ai.google.dev/api/live) — setupComplete и вложенное interruption.
- [Текущая модель Gemini](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live) — ID в конфиге документирован; квота/доступ аккаунта не проверялись.
- [Home Assistant REST API](https://contributors.home-assistant.io/core/internals/rest-api/) — история ISO и service response semantics.
- Локальный `research/alice-mini-2019/voice-pipeline-2026-10-25/AUDIO_IPC_CONTRACT_RU.md` — поля VQE из извлечённого protobuf descriptor; это не доказательство sample representation.
