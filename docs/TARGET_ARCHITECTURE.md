# Целевая архитектура: автономная Mini, Rust, без ПО Яндекса

Уточнение владельца от 02.11.2026 — обязательное требование к конечному
результату. Текущие vendor-компоненты допустимы только на переходных этапах.
Актуальный план: [GENERAL_PLAN](GENERAL_PLAN.md).

## 1. Что должно получиться

- Оригинальные CPU, RAM, микрофоны, динамик и органы управления Mini используются
  нашим устройством; необходимая прикладная обработка исполняется **на Mini**.
- Наш прикладной стек пишется на **Rust**: состояние ассистента, захват/вывод,
  локальная активация, аудиомаршрутизация, LED/кнопки, сетевые клиенты и интеграции.
- **100% замена компонентов Яндекса** — конечная цель. Отсутствуют зависимость
  от maind/platformd, yio_audio, vendor VQE API, Яндекс-аккаунтов, облачных API,
  OTA и скрытого запуска оставленных служб. Список устанавливаемых файлов,
  библиотек и загрузочных компонентов проверяется отдельно.
- **Pi в эксплуатационной архитектуре обслуживает только Home Assistant.**
  Голос, Spotify, память диалогов, авторизация провайдеров и runtime ассистента
  не переносятся на Pi. Её выключение должно нарушать только HA-интеграцию.
- Mini подключается к обычному маршрутизатору напрямую. Нынешние Pi NAT/DNS/
  SSH jump — лабораторные средства, не обязательный производственный gateway.
- Облачные OpenAI/Gemini/Spotify разрешены этим сценарием: клиент находится
  на Mini, inference/каталог/стриминг предоставляются выбранным сервисом.
  Полностью локальная большая LLM на Mini этим не объявляется реализованной.

```text
Микрофоны → наш capture/DSP → KWS + VAD + privacy gate
                                  ↓
                      Rust session / intent router
                         ↙          ↓          ↘
               cloud voice API   Spotify       HA REST → Pi
                         ↘          ↓
                   Rust audio arbiter / mixer → наш output → динамик

Mini → обычный Wi-Fi/router → интернет
Mini → локальная сеть → Pi: Home Assistant
```

Общий голосовой вход «Штучка» также обслуживает команды локального
расписания. Срабатывание сохранённого будильника идёт от часов Mini к
общему владельцу аудиовыхода. Приоритет звонка и остановка с корпуса
работают на Mini независимо от голосового клиента и Pi.
[План будильников и голосового вызова](plans/2026-11-05-local-alarms.md)

«Наш стек на Rust» относится к разрабатываемому прикладному ПО. Linux kernel,
драйверы, libc, firmware контроллеров и сторонние библиотеки — отдельный нижний
слой с явным происхождением. FFI-обёртку нельзя называть Rust-реализацией её
native engine. Любые остатки ПО Яндекса означают незавершённую миграцию;
неизвестное происхождение blob означает непроверенный пункт, а не 100% результат.

Один бинарник — возможный вариант упаковки. Количество процессов выбирается
по изоляции, shutdown/cancellation, CPU/RSS и воспроизводимости. Размеры
5–8 MB, RSS 25 MB и ровно 80 MB освобождения после maind пока не измерены.

## 2. Чего текущий Rust-клиент ещё не заменяет

`mini-assistant/src/audio/vqe_ipc.rs` получает VQE по TCP `127.0.0.1:9850`.
В исследовательском инвентаре 9850/yio_audio и 9875/aliced принадлежали одному
`maind --platformd`: `research/alice-mini-2019/principles-2026-10-26/README_RU.md:98`.
Перед вмешательством это соответствие нужно подтвердить на текущей firmware.
Нынешний экспорт обработанного микрофона остаётся зависимостью vendor stack.

Вывод идёт через C/glibc helper mini_pcm_sink и vendor ALSA default. Удаление
maind не доказывает независимость output, микрофонного DSP или cold boot.
Параллельный клиент Gemini — полезный промежуточный этап L1.

## 3. Порядок полной замены

| Этап | Конкретный результат | Доказательство перехода |
|---|---|---|
| H0 — инвентарь | PID/службы/IPC/maps; kernel modules, DT, firmware loaders, mixer/init/codec/DSP и библиотеки с происхождением | Dependency manifest и точный обратимый план; никаких неподтверждённых функций maind |
| H1 — независимый audio I/O | Собственная инициализация платы и Rust capture/output через исследованный kernel interface | Контролируемый старт без vendor audio initializer/platformd; raw input/output, формат/rate/channels и готовый rollback |
| H2 — frontend | Нормализация, resampling, VAD/KWS, выбранные NS/AGC/AEC и privacy gate | Отрицательные privacy tests, CPU/peak RSS, ложные активации, захват при музыке; явно определён half/full-duplex |
| H3 — управление | Mute, stop, громкость, кнопки, LEDs и нужные датчики | Работают без cloud/vendor демона; mute закрывает весь отправляемый mic path |
| H4 — медиа/интеграции | Клиент модели, HA, локальные будильники, Spotify при подходящей интеграции, хранение credentials и контекста на Mini; общий audio arbiter | Несколько ответов, длинный звук, музыка+ducking/stop, локальный звонок без сети, bounded queues и shutdown |
| H5 — системная миграция | Наш rootfs/init и нужная boot/kernel/DTB ветка; Яндекс-службы, libs/config/OTA исключены из целевой установки | Собственный recovery; cold boot без vendor platformd; файловый/process/network inventory |
| H6 — автономность | Голос/музыка доступны без Pi; HA показывает честную недоступность | Согласованный опыт отключения Pi; Mini идёт в интернет через обычный router |
| H7 — приёмка | Полная матрица аппаратных функций, обновление/откат и очистка временных зависимостей | Повторные cold boots, source/artifact hashes, состав дистрибутива, egress audit и измерения ресурсов |

H0 можно выполнять read-only сейчас. H1–H3 требуют ограниченных аппаратных
опытов с rollback. Остановка vendor stack планируется после подготовки
альтернативного пути и восстановления; работоспособность нынешнего VQE IPC
не является доказательством H1. Даже hot-stop maind после его инициализации
может оставить DSP/усилитель в готовом состоянии: это не самостоятельный
cold boot нашего тракта. Ничего не удалять из boot/firmware как
побочный эффект обычного code review.

## 4. Поправки к присланной технической схеме

**Статический musl ELF.** Убирает зависимость этого ELF от системной glibc
при действительно статической линковке. ISA/hard-float ABI, kernel syscalls,
драйверы, codec/mixer init, конфиги и native dependencies всё равно проверяются.
Обещание «на любом Linux ARM32» неверно. [Rust ARM Linux support](https://doc.rust-lang.org/stable/rustc/platform-support/arm-linux.html).

**librespot.** Подходящий Rust-кандидат, но не готовый доказанный Mini-порт.
Upstream ALSA backend требует libasound/pkg-config/toolchain. Проверенная
ветка dev также требует явного TLS backend при отключении defaults, поэтому
старую команду только с alsa-backend не принимать как готовый build recipe.
Зафиксировать commit/features/toolchain и ELF всех native частей.
[Сборка librespot](https://github.com/librespot-org/librespot/blob/dev/COMPILING.md),
[TLS feature validation](https://github.com/librespot-org/librespot/blob/dev/oauth/src/lib.rs).

**Spotify auth и управление.** Password login deprecated с v0.5; точный OAuth/
discovery flow проверяется для выбранного release. Connect receiver и голосовой
поиск/управление — разные слои. Start/resume — **PUT**, не POST,
`/v1/me/player/play`, с нужным scope и явным Mini device_id. Premium требуется
upstream librespot; работоспособность конкретного аккаунта здесь не проверена.
[Librespot options](https://github.com/librespot-org/librespot/wiki/Options),
[Spotify playback API](https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback).

**Porcupine.** Не pure-Rust engine: SDK использует предварительно собранное
proprietary ядро. В стандартном списке README русский и именно Mini/A113X
не подтверждены; совместимость/язык/AccessKey/условия проверяются отдельно.
Это кандидат с ограничениями, не выбранный компонент нашего Rust-стека.
[Porcupine](https://github.com/Picovoice/porcupine),
[C quick start](https://picovoice.ai/docs/quick-start/porcupine-c/),
[FAQ о proprietary engine](https://picovoice.ai/docs/faq/general/).

**Микшер.** ALSA допускает несколько потоков через подходящий plugin/arbiter;
это не универсальное ограничение «только один звук». dmix не реализует AEC,
ducking или управление усилителем. hw:0,0 не заменяет исследованный default
без нового аппаратного контракта. [ALSA PCM plugins](https://www.alsa-project.org/alsa-doc/alsa-lib/pcm_plugins.html).

Исследовать независимый audio frontend важнее, чем просто удалить maind.
Полный отказ от Яндекса остаётся критерием завершения, а не опцией после L1.
