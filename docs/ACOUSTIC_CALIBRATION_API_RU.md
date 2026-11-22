# Руководство по API автономной акустической калибровки GPT Mini

Документ описывает программный интерфейс автономной акустической калибровки, протокол подключения внешних AI-агентов через MCP (Model Context Protocol), модель безопасности и разграничения прав, управление комнатными профилями и правила безопасного натурного тестирования.

---

## 1. Архитектура и принципы безопасности

1. **Изоляция калибровочного агента (Least Privilege):**
   - AI-агент взаимодействует с устройством исключительно через ограниченный протокол MCP по `stdio` (или через защищённый REST API `/api/v1/acoustics/*`).
   - Агенту **запрещён** доступ к SSH, системному шеллу, перезагрузке, управлению громкостью, системным настройкам звука и ключам стриминговых сервисов.
   - Попытки вызова административных или посторонних эндпоинтов (`/api/v1/system/*`, `/api/v1/voice`, `/api/v1/volume`, `/api/v1/led`, `/api/spotify/*`) немедленно прерываются с кодом `401 Unauthorized` или `403 Forbidden`.

2. **Ограниченная сессия и защитная аренда (Lease Bounds):**
   - Калибровка выполняется строго внутри ограниченной сессии (`AcousticSession`).
   - Лимиты сессии защищают оборудование и покой пользователя:
     - `max_duration_secs`: максимальная длительность сессии (по умолчанию 1800 с, максимум 7200 с).
     - `max_volume_pct`: аппаратный потолок громкости воспроизведения стимулов (по умолчанию 50%, максимум 70%).
     - `max_runs`: лимит запусков измерительных заданий (по умолчанию 20, максимум 50).
   - При превышении любого лимита аренда аннулируется, а настройки возвращаются к исходному `baseline`.

3. **Защита от сбоев (Crash Recovery & Non-Destructive):**
   - При старте сессии на диск записывается файл `recovery_session.json` с исходной ревизией (`baseline_revision`) и конфигурацией.
   - Во время сессии кандидаты настроек применяются **только в оперативную память (RAM)** через канал очереди аудио-цикла без перезаписи `config.toml`.
   - Если демон или устройство перезагрузится во время сессии, при старте проверяется `recovery_session.json` и система автоматически откатывается к проверенному `baseline`.
   - Штатное завершение (`finish`) или отмена (`cancel`) сессии атомарно удаляет файл восстановления.

4. **Живой контроль владельца («Нужен живой контроль»):**
   - Ни один автоматически подобранный кандидат не может быть принят в статус `owner_confirmed` без явного подтверждения человеком.
   - Перед закрытием сессии и активацией профиля система требует вызова `confirm_session_owner`.

---

## 2. Модель авторизации и права (Scopes)

Авторизация осуществляется через заголовок `Authorization: Bearer <token>`.

### Матрица прав:
| Scope | Назначение | Доступные эндпоинты |
|---|---|---|
| `acoustics_read` | Чтение статуса, журнала событий и отчётов | `GET /state`, `GET /events`, `GET /jobs/{id}/report` |
| `acoustics_write`| Управление сессией, применение RAM-кандидатов | `POST /sessions`, `POST /sessions/{id}/candidate`, `POST /sessions/{id}/restore` |
| `profiles` | CRUD комнатных профилей, активация | `GET/POST /profiles`, `PUT/DELETE /profiles/{id}`, `POST /profiles/{id}/activate` |
| `samples` | Загрузка и прослушивание аудио-записей | `GET/POST /samples`, `GET /samples/{id}/audio`, `DELETE /samples/{id}` |
| `jobs` | Запуск и остановка измерительных сигналов | `POST /jobs`, `POST /jobs/{id}/cancel`, `POST /evaluate`, `POST /search` |

---

## 3. Спецификация REST API (OpenAPI 3.1)

Базовый путь: `/api/v1/acoustics`

### Эндпоинты:

#### 1. Метаданные и схема
- `GET /api/v1/acoustics/schema` или `/api/v1/acoustics/openapi.json`:
  Возвращает полную спецификацию OpenAPI 3.1 со всеми схемами DTO.
- `GET /api/v1/acoustics/state`:
  Текущее состояние аудио-тракта: статус готовности, загруженная модель KWS (`model_sha256`), фоновый шум, уровень RMS, ревизии, реестр возможностей (capabilities) и все 33 акустических параметра с допустимыми диапазонами.

#### 2. Сессии калибровки
- `POST /api/v1/acoustics/sessions`:
  Создание новой сессии. Если уже есть активная сессия — возвращается `409 Conflict`.
  Тело: `{"name": "string", "max_duration_secs": 1800, "max_jobs": 15}`.
- `GET /api/v1/acoustics/sessions`:
  Получение информации о текущей активной сессии.
- `POST /api/v1/acoustics/sessions/{id}/candidate`:
  Применение кандидата настроек в RAM (требуется полный объект из 33 полей).
- `POST /api/v1/acoustics/sessions/{id}/restore`:
  Возврат аудио-тракта к baseline сессии.
- `POST /api/v1/acoustics/sessions/{id}/confirm_owner`:
  Фиксация живого подтверждения владельцем.
- `POST /api/v1/acoustics/sessions/{id}/finish`:
  Завершение сессии. Опционально сохраняет кандидат как именованный комнатный профиль (`save_profile_name`) и активирует его (`activate_profile`).
- `POST /api/v1/acoustics/sessions/{id}/cancel`:
  Досрочная отмена сессии и сброс настроек.

#### 3. Измерительные задания (Jobs)
- `POST /api/v1/acoustics/jobs`:
  Запуск измерительного задания.
  Заголовок `Idempotency-Key: <unique_key>` предотвращает повторный запуск звука при сетевых ретраях.
  Тело:
  ```json
  {
    "stimulus_origin": "ambient" | "own_output" | "external_user_position",
    "output_route": "built_in" | "none",
    "stimulus": { "type": "silence" | "chirp_sweep" | "sample", "duration_ms": 200 },
    "pre_roll_ms": 400,
    "post_roll_ms": 800,
    "volume_pct": 30
  }
  ```
- `GET /api/v1/acoustics/jobs/{id}/report`:
  Структурированный отчёт о выполненном задании:
  - Валидность (`is_valid`, `validity_reason` — отбраковка тихого микрофона или цифрового клиппинга).
  - Полосный анализ тракта (`path_frequency_response` в полосах 100..500 Гц, 500..2000 Гц, 2000..6000 Гц) со строгим дисклеймером («Relative audio path attenuation below 8kHz; does not substitute room acoustic RT60»).
  - Метрики KWS: recall, false alarms, extra triggers, latency.
- `POST /api/v1/acoustics/jobs/{id}/cancel`:
  Идемпотентная отмена активного воспроизведения.

#### 4. Оценка и автоподбор параметров
- `POST /api/v1/acoustics/evaluate`:
  Пакетная оценка текущих параметров KWS на фиксированном корпусе сплита (`calibration`, `train`, `held_out`).
- `POST /api/v1/acoustics/search`:
  Ограниченный координатный поиск (потолок 20 итераций) с многокритериальной функцией ранжирования:
  $$S = 100 \times \text{recall} - 10 \times \text{FA/hr} - 20 \times \text{own\_leaks} - 2 \times \text{extra\_triggers} - \text{RTF\_penalty}$$

#### 5. Именованные профили помещений
- `GET /api/v1/acoustics/profiles`: Список сохранённых профилей.
- `POST /api/v1/acoustics/profiles`: Сохранение профиля (33 параметра, версионирование `schema: 1`).
- `POST /api/v1/acoustics/profiles/{id}/activate`: Активация профиля с долговременным сохранением в `config.toml` и аудио-цикле.
- `POST /api/v1/acoustics/restore`: Возврат к базовой конфигурации по умолчанию.

---

## 4. Подключение через MCP (Model Context Protocol)

Адаптер `scripts/mcp_acoustic_agent.py` реализует стандартный протокол MCP по `stdio`.

### Настройка окружения:
```bash
export GPT_MINI_URL="http://10.77.0.111:8080"
export GPT_MINI_CALIBRATION_TOKEN="calib_..."
export GPT_MINI_TIMEOUT="60.0"
python3 scripts/mcp_acoustic_agent.py
```

### Доступные инструменты (Tools):
1. `get_openapi_schema` — получить схему OpenAPI 3.1.
2. `get_acoustic_status` — состояние тракта, модели и 33 настроек.
3. `create_acoustic_session` — открыть ограниченную сессию.
4. `get_acoustic_session` — статус сессии.
5. `apply_session_candidate` — применить RAM-кандидат.
6. `restore_session_baseline` — вернуть исходные настройки сессии.
7. `start_acoustic_job` — запустить измерительный стимул (с `idempotency_key`).
8. `get_acoustic_job` / `get_acoustic_job_report` — отчёт и спектральный анализ тракта.
9. `evaluate_acoustic_candidate` — метрики KWS на калибровочном корпусе.
10. `search_acoustic_candidates` — координатный поиск оптимальных параметров.
11. `confirm_session_owner` — подтверждение живого контроля.
12. `finish_acoustic_session` — закрыть сессию с сохранением профиля.
13. `activate_acoustic_profile` — активировать сохранённый профиль.
14. `restore_working_profile` — сбросить тракт к заводским настройкам.

---

## 5. Итоговый реестр аппаратных возможностей (Capabilities)

На физическом устройстве GPT Mini зафиксированы следующие неизменяемые характеристики:

| Параметр | Значение | Ограничение и статус |
|---|---|---|
| **Микрофонный поток** | PCM16 mono · 16 000 Гц | Аппаратный драйвер ALSA захватывает native 8ch S32LE @ 48 кГц, понижаемый C-хелпером до 16 кГц mono. |
| **Физический канал** | `ch0` | Назначается при инициализации ALSA. Горячее переключение каналов в рантайме не поддерживается. |
| **MFCC** | Окно 30 мс / шаг 10 мс; pre-emphasis 0.97 | Фиксировано архитектурой акустической модели Rustpotter. |
| **Программный AEC/NS** | Не подключён | Полосовой фильтр KWS и нормализатор действуют внутри детектора; они не являются заменой полнодуплексного эхоподавления. |
| **AUX-выход** | **Отсутствует (Unavailable)** | На плате GPT Mini отсутствует разъём 3.5 мм AUX Jack. Маршрут `aux_out` отключён в UI и API. |
| **Обучение модели** | 3–8 эталонов фразы | Окно записи 3.8 с (максимум 4.0 с). Обучение изолировано в мастере главной страницы. |
