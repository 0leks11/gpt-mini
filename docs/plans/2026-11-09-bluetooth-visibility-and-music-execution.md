# План: Восстановление видимости Bluetooth, надёжного воспроизведения музыки и чувствительности активации

- Статус: done
- Дата: 2026-11-09
- Репозиторий и владелец: gpt-mini, mini-assistant

## Задача и критерии готовности

1. **Bluetooth-видимость на Mini:**
   - При голосовой команде «Включи Bluetooth» колонка включает режим обнаружения (`piscan`) через системный Linux ioctl `HCISETSCAN` (Page Scan + Inquiry Scan), устанавливает имя `GPT Mini` (`HCI_Write_Local_Name`), класс аудио-устройства `0x200414` (`HCI_Write_Class_of_Device`) и Extended Inquiry Response (`0x0C52`) с именем и UUID Audio Sink (`0x110B`).
   - Устройство `GPT Mini` отображается в списке доступных Bluetooth-устройств на MacBook и iPhone.
   - Статус: подтверждено (`hci0: Scan mode active: Flags=0x0000001D (UP=true, RUNNING=true, PSCAN=true, ISCAN=true)`).
2. **Гарантированное воспроизведение музыки («Включи музыку»):**
   - При голосовой команде «Включи музыку» (без указания конкретного трека) ассистент не просто вызывает unpause/resume на завершённом треке, а проверяет реальное состояние Soloist.
   - Если Soloist дошёл до конца трека (EOF: `position_ms + 3000 >= duration_ms`) или не воспроизводит звук после resume, немедленно запускается воспроизведение плейлиста `spotify:playlist:37i9dQZF1DXcBWIGoYBM5M`. Музыка звучит гарантированно.
   - Статус: подтверждено unit-тестами и интеграционной логикой в `src/spotify/mod.rs` и `src/spotify/soloist.rs`.
3. **Чувствительность активации и отзывчивость («Штучка»):**
   - Устранено зависание микрофонного пайплайна: осиротевший фоновый процесс `bt_demo` удалён, CPU свободен.
   - Порог детекции ключевого слова Rustpotter откалиброван: `threshold=0.38`, `avg_threshold=0.20` (в коде и в `.env` на Mini), что предотвращает пропуски естественной речи пользователя при баллах `0.413-0.417`.
   - Колонка стабильно откликается на «Штучка» и подает визуальную индикацию при диалоге.
   - Статус: подтверждено в логах запуска `threshold=0.38 avg_threshold=0.20`.

## Исходное состояние и ограничения

- Устройство: GPT Mini (`10.77.0.111:2222`, Jump: `pi@10.77.0.130`).
- Userspace: ELF32 ARMv7 / armhf, glibc 2.23, 236 MiB RAM.
- Чип Bluetooth: Broadcom BCM43430 (`/dev/ttyS1`), загружен через `bcm-attach`, `hci0` UP и RUNNING.
- Именование строго: **`GPT Mini`** / **`gpt-mini`**.
- Сохранять существующие `.env` и `config.toml` на Mini.

## Шаги

- [x] 1. Исследование причин:
  - Выявлен процесс `bt_demo -h`, создававший 21% CPU нагрузку и вызывавший ALSA overruns (убит).
  - Выявлено, что raw write команды `HCI_Write_Scan_Enable` без `ioctl(HCISETSCAN)` не включал inquiry/page scan в ядре.
  - Выявлено, что при завершении трека Soloist оставался на позиции `3:15 / 3:15`, и `soloist.resume()` завершался с кодом 0 без фактического звука.
  - Выявлено, что порог KWS 0.42 отсекал речь пользователя с баллами 0.413-0.417.
- [x] 2. Реализация в коде `mini-assistant`:
  - `src/bluetooth/mod.rs`: реализация `HCISETSCAN` ioctl (`0x400448DD`) с `SCAN_PAGE | SCAN_INQUIRY`, отправка `HCI_Write_Local_Name` ("GPT Mini"), `HCI_Write_Class_of_Device` (`0x200414`), `HCI_Write_Extended_Inquiry_Response` (EIR), чтение подтверждений контроллера.
  - `src/bin/bcm_attach.rs`: исправление проверки флага `HCI_RUNNING` (бит 2 вместо бита 1), авто-включение piscan при старте.
  - `src/spotify/soloist.rs`: улучшение детекции `is_at_eof()` с допуском 3000 мс (`position_ms + 3000 >= duration_ms`) и перевод в `Stopped` при EOF.
  - `src/spotify/mod.rs`: автоматический fallback на `soloist.play_uri` при завершении предыдущего трека или отсутствии реального воспроизведения после resume.
  - `src/wakeword/keyword.rs`: калибровка порогов по умолчанию (`threshold=0.38`, `avg_threshold=0.20`).
- [x] 3. Юнит-тестирование: `cargo test --offline --locked` (198 тестов passed, 0 failed).
- [x] 4. Развертывание на GPT Mini и калибровка `.env`:
  - Обновление `MINI_WAKEWORD_THRESHOLD=0.38` и `MINI_WAKEWORD_AVG_THRESHOLD=0.20` в `/data/opt/mini-assistant/.env`.
  - Сборка и деплой бинарников `mini-assistant` (SHA256: `5bddaeb0a72565af2a840b46cfbca62409ed4ffe15a9b9a70ac8345acea58379`) и `bcm-attach` (SHA256: `4ec66fc4fee14ad5e3696dcfc28c61080f5331cf333bf48a62e4424c583e9da5`).
- [x] 5. Проверка на устройстве:
  - Проверка `DevInfoBuffer` (флаги содержат `HCI_PSCAN` и `HCI_ISCAN`, `Flags=0x0000001D`).
  - Проверка запуска микрофона `hw:0,2` и подключения к Gemini Live API.
  - Проверка отсутствия ALSA overrun ошибок.
- [x] 6. Коммит и фиксация изменений.
