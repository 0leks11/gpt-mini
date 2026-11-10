# Сверка нового отчёта и исправлений R1/R3/R4/R6/R7

Дата: 02.11.2026. Снимок исходников: **15:42:01 Asia/Tbilisi**, 32 публичных
файла. Manifest SHA256:
`cc07e6ab5e0764125115009c3b60c71ca42be85a766802e024a39f0b578b2fc7`.
Архив: `.private/alice-mini/reviews/2026-11-02/current-report-recheck/`.
Требования владельца закреплены в [целевой архитектуре](TARGET_ARCHITECTURE.md).

## Результат

Изменения реально улучшают код, но перечисленные R1/R3/R4/R6/R7 пока нельзя
считать полностью закрытыми. Дополнительные fixtures воспроизвели старый timer
на обычных ответах, новую потерю END и утечку startup error payload.
Рабочий runtime-код и Mini в этой сверке не изменялись.

| Пункт | Что улучшено | Что остаётся |
|---|---|---|
| R1 | Убраны обычные raw frame/transcript/text INFO logs | Startup rejection JSON и Close reason возвращаются в Error и попадают в stderr main |
| R2 | Изменений KWS не обнаружено | VAD активируется на любую достаточно громкую речь |
| R3 | Добавлен active_turn guard и тест с разными IDs | В production IDs одинаковые для обычных ответов; старый timer всё ещё снимает flag; новый dedup теряет END |
| R4 | HA reply вынесен из reader в spawn | Нет cancellation registry/deadlines/in-flight limits; reader может ждать заполненную audio queue |
| R5 | Существенных изменений supervision не обнаружено | WS tasks по-прежнему detached; EOF не обеспечивает завершение всей сессии |
| R6 | Добавлен поиск/upload helper | Helper необязателен; hash/ABI/preflight отсутствуют |
| R7 | Непустой несовпадающий SHA отвергается до binary rename | Пустой SHA пропускается, helper не проверяется, bundle rollback отсутствует |
| R8 | Не исправлено | Лабораторные duration limits helper не согласованы с ответами |

## P1: END и одинаковый cancellation epoch

`mini-assistant/src/gemini/live_client.rs:326,353,379–392`:
turn_counter увеличивается только на interruption. Два обычных ответа A/B
имеют одинаковый ID=0. Последствия:

1. Guard `active_turn == turn_id` в `playback.rs:192–195` пропускает старый
   timer A во время B. Новый штатный тест вручную назначает B ID=1 и не
   воспроизводит обычный production путь.
2. `last_completed_turn=Some(0)` подавляет END второго и следующих ответов
   до interruption. Loopback actual-client fixture получил события
   `[(0,2), (0,0), (0,2)]`: audio A, END A, audio B, **нет END B**.

Fake-renderer regression с A/B epoch0 завершился ожидаемым FAIL101:
`A timer cleared active B with same cancellation epoch=0`.
Тест actual client с двумя ответами также FAIL101. Настоящих звук/микрофон/
cloud/HA не использовали; fake процессы и loopback servers очищены.

Исправление: отдельные response IDs и cancellation epoch; идемпотентное
завершение конкретного ответа; renderer drain/exit acknowledgment и владение
Child. Простое увеличение turn_counter без согласования с playback.generation
не является достаточным протоколом. Fixed 350 ms timer остаётся эвристикой.

## P1: error surface тоже относится к приватности логов

`live_client.rs:234,244,249–251` возвращает сырые setup error/Close детали.
Result-returning main выводит цепочку ошибки в stderr. Fixture подтвердил
synthetic private marker и в rejected setup, и в Close reason.

Отдельный regression FAIL101 подтверждает незакрытый error path, а не возврат
удалённых обычных INFO payload logs. Нужны redaction до формирования Error и
capture-log/error tests для отказов. «Полная конфиденциальность» пока не доказана;
VAD дополнительно остаётся отдельным ограничением фоновой отправки речи.

## P2: delivery стала лучше, но всё ещё не fail-closed bundle

`scripts/deploy.sh:150–156`: remote sha256sum обёрнут в `|| true`; проверяется
только непустой hash. Fake SSH с пустым hash дал exit0/Deploy complete.
На реальном хосте последняя проверка может вернуть ошибку уже после активации;
пустой/некорректный hash нужно отвергать до rename.

`deploy.sh:160–173`: поиск helper завершается без ошибки, даже если файла нет.
Независимый fake с корректным binary SHA и отсутствующим helper также завершился
успешно, без единой загрузки helper. Его hash/ABI/limits не проверяются.

Отказ config upload возвращает23, но binary rename/chmod уже выполнены:
нет транзакции всего набора и возврата прежних binary/config/helper/env.
Добавить отдельные fixtures для пустого/невалидного hash, missing/corrupt helper,
частичного upload, отказа прав и rollback.

## Проверки и доказательства

- В изолированной сборке снимка: **45 Rust + 9 deployment tests PASS**,
  fmt/clippy без замечаний. Корневые workflow/init tests: **12 PASS**.
- Дополнительные три regressions: **FAIL101**, каждый демонстрирует дефект;
  они не входят в45 штатных тестов. Fake deployment probes подтверждают
  отдельные пробелы, несмотря на9 зелёных обычных тестов.
- Первый общий прогон подхватил диагностический binary из общего Cargo cache;
  три HA fixtures также получили sandbox bind denial. Этот прогон не принят
  как baseline. Копии затем изолированы по CARGO_TARGET_DIR, пакет пересобран,
  loopback разрешён; итоговый baseline содержит именно45 тестов исходного снимка.
- Локальный ARM ELF: 2 454 348 bytes, ELF32, machine40/ARM, PT_INTERP отсутствует,
  DT_NEEDED=0. SHA256 совпал с присланным отчётом:
  `46dce23ed4bfc3205aaabc12dd9349b8287aa91633453f512d3482b4a6014856`.
  Это проверка файла на Mac, не новое измерение установленного Mini runtime.
- PID2247, успешное подключение модели, RMS и отсутствие просадки питания —
  данные присланного отчёта; независимый SSH/акустический опыт здесь не выполнялся.

Evidence:
`.private/alice-mini/reviews/2026-11-02/current-playback-verification/`
и `.private/alice-mini/reviews/2026-11-02/current-ws-deploy-review/`.
В них команды, source hashes и результаты fake/loopback fixtures без секретов.

## Следующая очередь

1. Исправить response/epoch/END state machine и закрепить оба негативных tests.
2. Закрыть redaction startup failures; убрать утверждение абсолютной приватности.
3. Обязательные manifest/hash проверки полного release и точечный rollback.
4. Bounded tool dispatcher/cancellation/supervisor и безопасная активация.
5. Параллельно выполнить H0 из целевой архитектуры: карта независимого audio I/O
   как основа полной замены platformd. Не объявлять локальный Rust API-client
   уже выполненным удалением компонентов Яндекса.
