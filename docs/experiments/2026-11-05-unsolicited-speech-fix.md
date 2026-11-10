# Остановка самопроизвольной речи и новый контракт активации

Дата: 05.11.2026, Asia/Tbilisi. Статус: исправления в работе, голос на паузе.
Основание: владелец просит устранить ответы без обращения и обрывы фраз;
разрешена ограниченная локальная запись образцов «Штучка».

## Preflight и пределы

Mini 1, прошивка `1.372.4.21.4818318323.20261030`, ядро сообщает aarch64,
исследованный прикладной ABI — ARM32/armhf. Питание сейчас от USB Mac;
по сообщению владельца динамик физически отсоединён. Поэтому акустическую
приёмку воспроизведения в этом опыте выполнить нельзя. USB/ADB на Mac не
обнаружен; фактический доступ — Wi-Fi SSH `192.168.1.110:2222`, pinned host key.

Исходный установленный mini-assistant SHA256:
`c77b598c87604f41741af9cb0c0f27f12401b99ec785b190fd5496f4bd816e3a`.
Исходный run-supervisor.sh:
`2c0b3783cc16a4c9237887dc0deb6b40d981778280b8b7673be9b15c09ab65af`.
Исходный S99mini_assistant:
`fef407430798061334898a6cae3340fd378e2768acdee3dd7bc256960a7dc208`.
mini_pcm_source:
`849f6a7a8b8eff573c900b4ab7e4660a7dc26a9fc5a34b8cbc7e6285d71396df`.

Оба Git-дерева изначально dirty: root workflow/STATE/review/планы и вложенный
Rust repository с audio, Gemini, HA, weather, deployment, конфигурацией и tests.
Изменения не приписываются чистому коммиту, staging/коммит не выполнялись.

## Выполненная остановка

Сохранены private backup файлов и точный исходный script. В
`/bkupgrade/data/opt/mini-assistant/run-supervisor.sh` добавлена проверка
маркера `voice.paused` до запуска цикла. Маркер создан, `sh -n` выполнен;
проверены пути исполняемых процессов и start-time `/proc`, затем остановлены
только наши supervisor, mini-assistant, mini_pcm_source и mini_pcm_sink.
Небезопасный stop по непроверенным старым PID-файлам не использовался.
Результат: `remaining_owned_voice_processes=0`, SSH сохранился, exit 0.
После отдельной read-only проверки guard выполнен `sync`.

SHA256 supervisor с guard:
`9ae6667deeb3dff3db4b9d6f3ce1c76c706f1afaa41844bdcfaa287bd6bc4490`.
Приватное evidence/backup находится в `.private/alice-mini/reviews/2026-11-04-unsolicited-fix/`.

Не менялись firmware, boot, OTA, vendor services, SSH, маршруты, DNS,
firewall/NAT и политика внешнего доступа. Новое голосовое подключение к
облаку в этой остановке не выполнялось; записи речи ещё не начинались.

## Изменение поведения в коде

- KWS/явное локальное управление дают разрешение на один ограниченный turn.
  Громкость/RMS только поддерживает уже открытую реплику.
- Нет валидного персонального шаблона — acoustic activation отключена;
  автоматического перехода к VAD-активации нет.
- Startup/reconnect/cancel/timeout не дают права на model PCM или HA/tools.
- Manual realtime activity framing вместо пустого clientContent.turnComplete.
- Поздние ответы связаны с FIFO отправленных turn, не с текущим ID наугад.
- Half-duplex и 800 мс tail: без голосового RMS barge-in до проверки AEC.
- END ждёт реальный drain renderer; старые таймеры не отменяют новую реплику.

Подробный план: [stop-unsolicited-speech](../plans/2026-11-04-stop-unsolicited-speech.md).
Результаты host/ARM/device приёмки добавляются только после выполнения.

## Откат

Оставить `voice.paused` и SSH, если сборка/проверка неуспешны. Не возвращать
разговорчивый старый runtime автоматически. Оригинальный supervisor сохранён
на Mini как `run-supervisor.before-pause-20261105.sh`; исходный init не изменён.
Восстановление исходного script — только при осознанном возврате старого режима;
снятие паузы не является безопасным default отката.

## Host и target: фактически выполненные проверки

`mini-assistant/scripts/check.sh`: fmt/clippy, 109 runtime + 5 enrollment Rust
и 13 fake-deployment tests PASS. Корень: workflow guard и 12 tests PASS.
`CARGO_TARGET_DIR=target/vendor-contract-check cargo test --offline --locked
--manifest-path vendor/rustpotter-ref/Cargo.toml`: 9 self-contained contracts
и один compile-only doc example PASS. Upstream example с внешним reference
отмечен no_run: компиляция не доказывает существование файла/распознавание.

ARM32 trial app: 2 909 108 bytes, SHA256
`d9e3df076ae0649e9ff97f6fb036709f71c35c4722841c37f0bc3b385570e254`.
keyword-enroll: 748 204 bytes, SHA256
`80b142e2e79480b23abe902737cee95d620d180eea5f1ee4d7f8dd85fd40f816`.
readelf: ELF32 ARM EABI5 hard-float; нет PT_INTERP и dynamic section.
Runtime по-прежнему использует отдельные C audio helpers и vendor ALSA library:
полное удаление ПО Яндекса/полностью Rust audio backend этим не доказаны.

Персональный reference: 10 350 bytes, 3 templates, 27–33 MFCC frames.
На Mac и Mini отдельное имя:1 detection, обычный вопрос:0; короткий фон/тишина
на Mac:0. Среди трёх training-клипов:2 detections из3. Wrapper из актуального
исходника с chunk512 также даёт1 на held-out WAV. Одна положительная и несколько
коротких отрицательных проб не измеряют false accepts/hour/FRR.
На Mini: 2-секундный WAV +2с synthetic tail обработан за253мс, RTF0.063;
обычный вопрос:283мс, RTF0.064. Это offline throughput, не задержка диалога.

## Trial и наблюдения

Отдельный каталог `/bkupgrade/data/opt/mini-assistant/trial-20261105-a`.
Trial config исключает HA и отключает weather; оригинальный config/.env не
переписывались. Named temporary WAV копировались только на свою Mini для
offline benchmark. Модель/образцы/полные логи/manifest находятся приватно.

1. Closed trial:35с, несуществующий model path → acoustic activation DISABLED.
   API handshake и ALSA capture стартовали,0 local activation events,
   graceful shutdown/Bye подтверждены. По контракту закрытого разрешения
   микрофонный фон не проходит в cloud input; packet capture не выполнялся.
2. Voice trial:60с, валидный template loaded, startup/clean shutdown успешны,
  0 local activation events. Успешная реплика/response/renderer не подтверждены.
   У владельца запрошено, была ли произнесена фраза после сообщения готовности;
   отсутствие activation само по себе не доказывает поломку библиотеки.

Watchdog направлял SIGINT, затем при необходимости SIGKILL только в trial PID
с проверкой canonical executable path и start-time; старые PID-файлы init не
использовались. Самозапускающий supervisor всё время оставался на паузе.
Новых HA-действий не было. Динамик физически отключён: слышимость и акустическую
полноту ответа проверить нельзя. Отключение динамика от эха не заменяет AEC test.

## Финальная установка на паузе

После удаления приватных weather logs и уточнения readiness собран финальный
артефакт. Основная и независимая сборка в отдельном target дали одинаковый hash:
`18e7369e1844e886111bc7ea96df197d21f1ee7a09717a0938531faf3179b268` (2 909 108 bytes).
ELF32 ARM EABI5 hard-float, нет interpreter/dynamic section. Полный check.sh
повторён:109+5 Rust,13 deployment,fmt/clippy PASS.

Новый бинарник установлен атомарно в canonical directory с SHA256-проверкой;
`mini-assistant --version` завершился0. Исходный c77b598c… сохранён как
`mini-assistant.before-unsolicited-fix-20261105` и повторно проверен полным hash.
keyword-enroll установлен; KWS template не продвигался из trial в default path.
Микрофон/облако/HA при финальной установке не запускались. `voice.paused=1`,
SSH доступен,после trials подтверждено0 owned voice processes. Cold boot
после этого изменения не выполнялся; полнота акустического ответа не принята.

Исходное состояние dirty: root AGENTS/README/workflow/STATE/review/plans/tests;
в mini-assistant Cargo/build/deploy/config/audio/Gemini/HA/weather и tests.
Изменения этой задачи ограничены interaction,keyword/enrollment/vendor adaptation,
input gate,main/live client/playback/capture,зависимостями и относящимися docs.
Ничего не staged/committed. Полный перечень и source hashes сохранены приватно
в source-manifest.json; секреты/записи/шаблон не добавлялись в Git.

## Уточнение после дополнительных live probes

Владелец подтвердил фразу в первом app trial:0активаций — это false reject.
Отдельный30с локальный monitor без API и записи дал2 detections:
отдельное имя и имя перед вопросом. ПикиRMS23.37/26.34, scores0.663/0.662.
Повторный60с app trial с диагностикой имел313чанков/5с, peakRMS28.33,
Ready=1/playback=false/warmup=0, но0активаций; clean shutdown подтверждён.
Следовательно снижать speech VAD вместо исследования KWS неправильно.
По этим наблюдениям точная причина различия live trials ещё не доказана.

На том же held-out WAV реальный KeywordEngine и InputGate после125reset
дали1/1 и на Mac, и на ARM Mini. Ещё один30с live compare одного PCM дал
matcher1 / wrapper1 / InputGate1. Для второй фразы в коротком окне вывод
не делается. Эта проба не воспроизвела расхождение обёртки/шлюза; одного
сравнения недостаточно для снятия вопроса об устойчивости/интеграции.
Порог не снижался ради получения успешного ответа, VAD fallback не включался.

Финальный установленный app SHA256:
`de2171b4ea29a671cd6e946178ffe790ee7a9e658a113f30f976594b1f7284cc`.
Это сборка с опциональным MINI_DIAGNOSTICS=1:5-секундные метаданные,
без текста/аудио/tool arguments. По умолчанию диагностика выключена.
Полный check.sh повторён109+5 Rust/13deployment/fmt/clippy PASS;
ARM32 ELF проверен заново. Intermediate18e7369… и исходныйc77b598c… сохранены.

Финальный post-check:0owned voice processes, voice.paused=1, SSH жив;
свободно64 056KiB на data. Временные diagnostic executables и WAV на Mini
удалены точечно. Локальные записи/шаблоны/исходники probes сохранены приватно.
Полный голосовой цикл и слышимость не приняты; автозапуск не включён.
Следующая приёмка требует репрезентативного positive/negative corpus и
сравнения полного voice loop; акустическая проверка — после отдельного
безопасного подключения динамика при выключенном питании.
