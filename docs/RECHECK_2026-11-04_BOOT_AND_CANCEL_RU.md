# Приёмка новых отчётов: boot, supervisor и cancellation

Дата: 04.11.2026, после вечернего развёртывания. Сверены отчёты Antigravity
16:40 и 19:15, текущий dirty-код, host tests и read-only snapshot Mini.

**Прогресс подтверждён: Mini доступна по SSH, установлен ожидаемый бинарник,
83 штатных Rust-теста проходят, прежний рассинхрон epochs исправлен. Весь
план миграции и надёжность stop/boot/voice пока не приняты.**

## Что проверено непосредственно

- Mac: `192.168.1.69`; свежий прямой root SSH к `192.168.1.110:2222`
  с `StrictHostKeyChecking=yes` и прежним pinned host key выполнен успешно.
- Установленный бинарник прочитан через `sha256sum`; совпадает с локальным:
  `c77b598c87604f41741af9cb0c0f27f12401b99ec785b190fd5496f4bd816e3a`.
  Локальный размер — 2,594,020 байт. Новая ARM-сборка здесь не выполнялась.
- Uptime в момент чтения — 1289.65 с. Это не определяет способ предыдущего reset.
- С Mini сохранены актуальные init и supervisor, без их исполнения/изменения:
  - `S99mini_assistant`: SHA256 `fef407430798061334898a6cae3340fd378e2768acdee3dd7bc256960a7dc208`;
  - `run-supervisor.sh`: SHA256 `2c0b3783cc16a4c9237887dc0deb6b40d981778280b8b7673be9b15c09ab65af`.
- Начальная попытка разрешения read-only SSH истекла на автоматической
  проверке, не выполнив команду; единственный повтор завершился успешно.

Никакие новые restart/reboot, записи I2C, изменения Wi-Fi/DNS, запись речи,
проигрывание звука или HA-действия в этой сверке не выполнялись.

## Результаты host-проверок

| Проверка | Результат и граница |
| --- | --- |
| `cargo test --offline --locked --all-targets` | **83 PASS**, 1.13 с; fixtures/Mock/loopback, без устройства |
| `cargo clippy --offline --locked --all-targets -- -D warnings` | PASS |
| Python deployment fixtures | **13 PASS**, около 10 с; fake SSH/Docker, не деплой |
| Корневые workflow/init tests | **12 PASS** |
| `./scripts/check.sh` с offline Cargo | **FAIL на rustfmt**: `main.rs` и `audio/playback.rs`; следующие проверки script не запустил, они выполнены отдельно |
| Независимый test прежнего epoch drift | PASS, meaningful assert сохранён |
| Новый test позднего PCM после local cancel | **FAIL**: старый ответ снова достигает Mock-worker |
| Negative fixtures установленного init/supervisor | Воспроизведены wrong-PID kill и незавершённый child после успешного stop |

Штатные 83 PASS не включают новые отрицательные сценарии. Их успех не
опровергает найденные дефекты. Рабочие исходники не форматировались и не менялись.

## P1: поздний PCM отменённого ответа снова включает звук

Старый дефект решён корректно: main передаёт общий epoch handle, а облачная
обработка не дублирует его увеличение поверх callback. Исходный audit-test
действительно проходит; проверка принятия следующего PCM не была ослаблена.

Но `src/gemini/live_client.rs:488` берёт **текущий** epoch для каждого пакета
продолжающегося старого ответа. После local cancel такой пакет получает новую
метку и проходит `play()` вместо отбрасывания.

Воспроизведение на настоящем клиенте с synthetic PCM и Mock renderer:

```text
response 1: epoch 0 принят
local cancel: shared epoch стал 1
поздний PCM response 1: помечен epoch 1 → снова принят worker
cloud interrupted: shared epoch стал 2
следующий response 2: epoch 2 принят правильно
```

Прогон: **1 PASS / 1 FAIL / 82 filtered, exit 101**. Ошибка находится в окне
до cloud acknowledgement; тест, который сразу присылает `interrupted`, его
не проверяет.

В приватной копии проверен узкий вариант: фиксировать epoch за ответом,
применять его к PCM/END и обновлять только на границе новой реплики/сессии.
Четыре последовательных контракта прошли: старый drift, поздний старый PCM,
completion без interrupted → новая реплика, настоящий PCM после reconnect.
**Это кандидат коррекции, не применённый в рабочем коде и не готовый деплой.**

Отдельный статический риск остаётся и у этого кандидата: `play()` проверяет
epoch, затем ставит `is_playing`, а `interrupt()` между этими действиями может
изменить epoch/сбросить флаги. Worker отбрасывает stale chunk без снятия ошибочно
выставленного флага. Нужен согласованный lifecycle/единый владелец состояния
и отдельная concurrency regression; четыре последовательных теста этого
свойства не доказывают.

## P1: stop доверяет чужому PID

В установленном `S99mini_assistant` строки 12/32 проверяют только `kill -0`,
а строки 24–27 используют PID из файла для `pkill -P`/`kill` без проверки
executable, command identity или start-time.

На изолированной копии с уникальными paths и посторонним **тестовым** sleep:
status ошибочно показал работающую службу, start отказался запускать её,
а stop завершил чужой процесс SIGTERM (`returncode=-15`). На Mini такой
опыт не выполнялся.

Требуется строгая проверка владельца PID непосредственно перед каждым signal,
валидация числового PID, исключение PID reuse и блокировка параллельных start.
Широкий `pkill -f` следует заменить управлением только своими процессами.

## P1: успешный stop не гарантирует прекращение работы child

Init посылает TERM, сразу удаляет PID-файл и возвращает 0; supervisor не имеет
signal/exit traps. В отрицательной fixture child, игнорирующий TERM, остался
жив после stop при уже удалённом PID-файле. Все наши тестовые процессы очищены.
Это не утверждение, что нынешний Rust-процесс игнорирует TERM.

Нужны forwarding, bounded TERM/wait с безопасной эскалацией только для своего
child, reaping и запрет respawn во время stop. Также сейчас daemon перезапускается
всегда, включая exit 0, через постоянные 2 с; лог без ограничений дописывается
на persistent storage. Требуются restart budget/backoff и ограничение логов.
Положительно: supervisor не исполняет .env как shell.

## Остальные замечания к готовности

- **DNS deadline:** `src/main.rs:700–725` делает 15 `lookup_host().await`
  без timeout. Сам resolver может задержаться; 2-секундная пауза есть только
  между ошибками. `Ok(empty)` повторяется без паузы. Лога «после 30 с» недостаточно:
  нужен реальный общий deadline и ограниченные попытки с fixtures.
- **VAD/KWS/AEC:** `wake_words` по-прежнему не используются для локального
  распознавания. Порог 400 — калибровка RMS, а не распознавание «стоп» или AEC.
  Надёжность при разной дистанции/громкости и при музыке не подтверждена здесь.
- **LED/readiness:** погашение LED после WS setup происходит до проверки
  capture. Ошибка capture остаётся warning, после которого логируется общий
  active pipeline. LED/живой PID не доказывают готовность микрофона/всего тракта.
  Записи I2C из присланного отчёта здесь не повторялись.
- **Питание:** в отчёте 19:15 явно выполнена команда `reboot`. Это свидетельство
  warm reboot, не cold power-cycle. Нет evidence двух candidate cold boots,
  реального выбора rescue и финального commit.

## Существующие boot-зависимости: не удалять вслепую

В свежем сохранённом baseline `S05linkplay.sh:22–47` source-ит Linkplay env,
добавляет `/system/vendor/quasar/libs` и запускает `rootApp`. `S90wait_lplay`
без deadline ждёт rootApp, mv_ioguard и `new_nvram_config` **до S99-служб**.
Удаление этих компонентов без изменения dependency graph может заблокировать
и SSH. Это статический вывод по backup, не новый опыт отключения служб.

`S03datamount` содержит `ubiformat` в fallback и `mkfs.ext4` в ext4-ветке.
Не использовать его как безопасный generic rescue и не провоцировать ошибки
mount на настоящей NAND. Это существующий код, а не внесённое здесь изменение.

Ноль выбранных PID Яндекса — полезное наблюдение из отчёта, но не доказательство
отсутствия файлов/библиотек, предварительной vendor инициализации или egress.
Происхождение Linkplay/driver/firmware проверяется отдельно; не считать весь
нижний слой автоматически кодом Яндекса или уже заменённым нашим кодом.

## Статус плана после сверки

| Гейт | Приёмка |
| --- | --- |
| G0/G1 | Правильный LAN/роутер подтверждён присланным отчётом; root SSH повторён в этой сверке |
| G2 | Backup есть; актуальные init/supervisor теперь тоже сохранены. Полный manifest/проверенный rollback требуют завершения |
| G3 | Частично: код и тесты есть; lifecycle дефекты и воспроизводимый безопасный boot bundle остаются |
| G4 | Есть работающая сеть; renew/AP-loss и независимый rescue не представлены |
| G5 | Warm reboot подтверждён отчётом; cold boot/trial→rescue→commit не приняты |
| G6 | Старый drift исправлен; late PCM/stop lifecycle, KWS/AEC и акустическая приёмка остаются |
| G7 | Полная миграция/provenance/egress не приняты |

Пересоздавать уже работающие S03/S40/S41 с нуля не требуется. Следующая работа:
согласованный cancellation lifecycle → безопасный supervisor → настоящий DNS
deadline → offline regressions → отдельный контролируемый cold-power опыт
при сохранённом SSH/recovery. Не начинать с удаления нижнего vendor слоя.

## Evidence и исходный снимок

Root HEAD `cab9e6f301664d3594e6ccdbb9cefc8e7c930e56`, app HEAD
`6b93d201ff73b04023e821cae2246f182825494d` плюс исходные dirty-файлы.
Все проверяемые runtime-модули уже были изменены до этой сверки.

- main.rs SHA256: `1de9f4761158808cdc9da68abfae9b92579ec367821ceef5d68526e02c078fe9`;
- live_client.rs: `99c504dd31112ad2b1f8afd7ea1344390ecf7cfaa880e574e31410bf3e81f5ec`;
- playback.rs: `6db1697613be8a59e99aa2dabdc3138ec81364976534adb24dc6940565cab0cd`.

Приватно: `.private/alice-mini/reviews/2026-11-04-post-deploy/` содержит
SOURCE_MANIFEST, host outputs, LIVE_METADATA, текущие init/supervisor и
`supervisor-audit/`. Отрицательный fixture SHA256:
`6c215de520ae80fa186116e4516a5996c5d30e29bc647fd0ec06b872a9e2e52f`.

Отдельные package/target для PCM-регрессий:
`.private/alice-mini/reviews/2026-11-04-vad-review/shared-epoch-recheck/`
и `response-epoch-candidate/`. Первый test binary SHA256:
`1d685aadf3d941c0c0a2c3ea158aeb83d03219355cb35ccedcf60b4c7ad76dcc`.
Точные команды, source hashes, fixtures и cleanup записаны в EVIDENCE/README.
Кандидат не изменял production; до его применения нужна проверка оставшейся
гонки и полный review, а затем отдельный безопасный deployment.

Документация: guard индекса PASS (16 файлов), отдельно проверены пять рабочих
Markdown-документов — ссылки, ограниченный secret guard и whitespace PASS;
`git diff --check` PASS. Private snapshots/candidate остаются git-ignored.

Candidate test binary SHA256:
`bcfb958e52f92e44f1398a17b56c0e0de9d01a09dacca63807c1b73c2c48e0ac`;
candidate live_client.rs SHA256:
`2069f5d6713c1fdbe4f9b0060bcfb15bfbe7698a156889f4417a6c8a10619d13`.
