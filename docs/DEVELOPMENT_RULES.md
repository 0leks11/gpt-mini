# Регламент разработки, сборки и деплоя GPT Mini

> **Главный принцип:** «Одной рукой чиним — другой не ломаем».  
> Ни одна рабочая функция не может быть потеряна, отключена или повреждена при добавлении новых возможностей или исправлении дефектов.

---

## 1. Реестр активных функций (Feature Registry)

Каждая функция в этом списке является **обязательной** частью каждой сборки. Перед деплоем новой версии все функции из таблицы должны быть проверены.

| Функция | Модуль / Файлы | Флаг / Конфиг | Инструмент Gemini Live | Метод верификации |
|---|---|---|---|---|
| **Голосовой диалог Gemini Live** | `src/gemini/live_client.rs`, `src/main.rs` | `GEMINI_API_KEY`, `voice = "Callirrhoe"` | Потоковый WebSocket | Проверка `setupComplete` в логе, голос Callirrhoe |
| **Акустический Wake-Word («Штучка»)** | `src/wakeword/keyword.rs`, `src/main.rs` | `MINI_WAKEWORD_THRESHOLD=0.42` | Локальный KWS | Реакция на обращение, отсутствие ложных срабатываний |
| **Подавление эха и самопрерывания** | `src/main.rs` (`echo_until`, `playback.is_playing()`) | Встроенная защита | — | Ассистент не прерывает собственную речь |
| **Управление Home Assistant (Кондиционер)** | `src/ha/`, `src/main.rs` | `HA_URL`, `HA_TOKEN` | `control_home_device` | «Включи кондиционер», «Поставь 22 градуса» |
| **Прогноз погоды (Open-Meteo)** | `src/weather/`, `src/main.rs` | `weather.enabled = true` | `get_weather` | «Какая погода в Батуми?» с точным ветром м/с |
| **Локальные будильники** | `src/alarms/`, `alarm-cli` | `alarms.enabled = true` | `create_alarm`, `list_alarms`, `delete_alarm`, `snooze_alarm`, `stop_alarm` | «Поставь будильник на 7 утра», сброс кнопкой/голосом |
| **Воспроизведение Spotify (Soloist + Web API)** | `src/spotify/`, `soloist-env/` | `spotify.enabled = true`, OAuth refresh token | `spotify_play`, `spotify_pause`, `spotify_next`, `spotify_previous`, `spotify_volume`, `spotify_current_track` | «Включи музыку», пауза, треки; фолбэк на Web API |
| **Голосовая громкость (0–10)** | `src/audio/volume.rs`, `src/gemini/live_client.rs`, `src/main.rs` | Шкала 0–10 | `set_volume`, `volume_up`, `volume_down` | «Громкость 5», «Тише», «Громче» |
| **Жестовое управление громкостью (VL53L0)** | `src/audio/vl53.rs`, `/dev/input/event0` | `enable_ps_sensor=1` | Аппаратный сенсор ладони ToF | Приближение ладони уменьшает громкость, отдаление увеличивает |
| **Остановка диалога** | `src/main.rs`, `src/gemini/live_client.rs` | `has_stop_dialogue` | `stop_dialogue` | «Хватит», «Стоп», «Замолчи» |
| **Аппаратная кнопка Mute** | `src/buttons/`, `src/main.rs` | `/dev/input/event2` (adc_keypad) | Прерывание речи / остановка звонка | Короткое нажатие глушит будильник/речь |

---

## 2. Правила написания кода

1. **Не ломать существующие сигнатуры и контракты**:
   - При добавлении параметров в конфигурацию (`LiveClientConfig`, `AudioPlayback` и др.) обязательно обновлять все конструкторы и mock-тесты.
   - Новые инструменты Gemini Live объявляются в `live_client.rs` и регистрируются в диспетчере `main.rs`.
2. **Отказоустойчивость и фолбэки**:
   - Ни один внешний сервис не должен ронять процесс ассистента при сбое или недоступности.
   - Для Spotify: при сбое локального Soloist обязательно срабатывает фолбэк на официальный Web API (OAuth).
   - Для громкости: программное масштабирование семплов PCM работает автономно даже при отсутствии утилит микшера.
3. **Безопасность данных**:
   - Никаких секретов, токенов и ключей в репозитории и коммитах.
   - `.env` и `config.toml` с реальными учетными данными находятся только на физическом устройстве.

---

## 3. Регламент сборки (Pre-Build & Build Verification)

Перед сборкой каждого релиза выполняются следующие шаги:

1. **Локальная проверка компиляции:**
   ```bash
   cd mini-assistant && cargo check
   ```
   Должно завершаться с `0 errors`.

2. **Полный прогон юнит- и интеграционных тестов:**
   ```bash
   cargo test --offline --locked
   ```
   Все тесты (180+) обязаны завершаться со статусом `test result: ok. X passed; 0 failed`.

3. **Сборка бинарника для ARM32 (musl):**
   ```bash
   ./scripts/build.sh
   ```
   Сборка выполняется в изолированном Docker-контейнере `armv7-unknown-linux-musleabihf`.

4. **Фиксация хеша артефакта:**
   Вычисляется SHA256 полученного бинарника `target/armv7-unknown-linux-musleabihf/release/mini-assistant`. Этот хеш фиксируется в отчете и в `docs/STATE.md`.

---

## 4. Регламент развертывания на физическом устройстве (Deployment & Verification)

1. **Сохранение конфигурации:**
   - Скрипт деплоя НЕ должен перезаписывать существующий `.env` или `config.toml` на устройстве шаблонными значениями.
   - Голос в `config.toml` на устройстве: строго `Callirrhoe`.

2. **Загрузка бинарника:**
   - Деплой через Jump Host (`pi@10.77.0.130`) на Mini (`10.77.0.111:2222`).
   - Использование потокового `cat` через SSH (ввиду отсутствия SFTP на Busybox Mini).

3. **Верификация после перезапуска службы:**
   - Проверка запущенных процессов:
     ```bash
     ps | grep -E 'mini-assistant|mini_pcm_source|soloist'
     ```
     Должны работать: `mini-assistant`, `mini_pcm_source`, `soloist`.
   - Проверка состояния аппаратного сенсора расстояния:
     ```bash
     cat /sys/devices/virtual/input/input0/enable_ps_sensor
     ```
     Значение должно быть `1`.
   - Проверка логов (`tail -n 30 /data/opt/mini-assistant/assistant.log`):
     * Присутствует строка `setupComplete confirmed`
     * Зарегистрированы все инструменты: `ha_tools: true, weather_tools: true, alarm_tools: true, spotify_tools: true, volume_tools: true`
     * Голос: `Callirrhoe`.

---

## 5. Регламент фиксации изменений в Git

1. **Атомарные коммиты:**
   - Каждое логическое изменение фиксируется отдельным коммитом явным списком файлов:
     ```bash
     git add src/audio/volume.rs src/audio/vl53.rs ...
     git commit -m "feat(audio): add voice volume scale 0-10 and VL53L0 gesture reader"
     ```
   - Запрещено использовать `git add -A`.
2. **Формат сообщений:** Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`).
3. **Обновление состояния проекта:**
   - При каждом релизе на устройство обновляется `docs/STATE.md` с указанием SHA256 бинарника, проверенных функций и выявленных ограничений.
