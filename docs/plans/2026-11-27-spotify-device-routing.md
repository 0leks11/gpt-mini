# План: Приоритетная маршрутизация Spotify Connect на GPT Mini

- Статус: done (задеплоено и проверено; боевой сценарий «активен MacBook → голос на Mini» готов к проверке пользователем)
- Дата: 2026-11-27
- Репозиторий и владелец: `mini-assistant` (`9bcbda8`) + `gpt-mini`

## Задача и критерии готовности

После перезагрузки или отключения питания `soloist` (Spotify Connect) запускается со статусом `is_active: false`, пока активным устройством в аккаунте Spotify остаётся ноутбук (MacBook) или телефон. При команде «включи музыку» или нажатии Play на `http://<ip>:8080/` музыка возобновлялась на внешнем устройстве вместо самой колонки.

Критерии готовности:
1. При голосовом запуске/переключении треков (`spotify_play`, `spotify_next`, `spotify_previous` в `src/spotify/mod.rs`) и при действиях в Web UI (`/api/spotify/play`, `/api/spotify/next`, `/api/spotify/previous`, `/api/spotify/activate` в `src/web/mod.rs`) колонка сначала гарантированно становится активным устройством Spotify Connect (`soloist-ctl activate` + fallback через Spotify Web API `PUT /v1/me/player` на устройство `GPT Mini`).
2. `SoloistStatus::is_actually_playing()` требует `is_active == true`, поэтому проигрывание на стороннем устройстве (MacBook/телефон) не считается локальным воспроизведением в `MusicDucker`, поллере `main.rs` и статусе Web UI.
3. В `dashboard.html` статус Spotify показывает реальное состояние (`Активна на Mini` / `Другое устройство` / `Не подключена`) и кнопку быстрого перехвата `Выбрать GPT Mini`, когда активен другой клиент.
4. Все изменения минимальны, не ломают существующие интерфейсы и калибровку `Acoustics Lab`, покрыты модульными тестами (`cargo test`), проходят `./scripts/check.sh`, задеплоены и подтверждены `./scripts/verify_deploy.sh`.

## Исходное состояние и ограничения

- Логи на Mini (`15:06:39Z`–`15:07:03Z`) подтвердили: при `active device: no` вызов `soloist-ctl play` (`resume()`) запускает воспроизведение на MacBook.
- `soloist-ctl` поддерживает команду `activate` (`Become the active Spotify Connect device`).
- Spotify Web API клиент (`src/spotify/web_api.rs`) уже умеет `get_devices()` и `select_target_device()` с приоритетом `"GPT Mini"`, но не имеет метода `transfer_playback` (`PUT /v1/me/player`) и helper-фильтра только для Mini.
- `Calibration` токены в `src/web/auth.rs` запрещены на `/api/spotify/*` (должно сохраниться и для `/api/spotify/activate`).

## Шаги

- [x] Добавить `SoloistClient::activate()` и учет `is_active` в `SoloistStatus::is_actually_playing()` + `MusicDucker::duck()`
- [x] Добавить `find_mini_device()` и `SpotifyApiClient::transfer_playback()` в `src/spotify/web_api.rs`
- [x] Вынести единый helper `ensure_local_device_active()` и `execute_playback_action()` в `src/spotify/mod.rs` и подключить к `handle_spotify_tool_call` и `/api/spotify/*` (`play`, `next`, `previous`, `activate`)
- [x] Обновить статус и кнопку перехвата устройства в `src/web/dashboard.html`
- [x] Написать модульные тесты (fake `soloist-ctl`, mock Web API `PUT /v1/me/player`, auth/routing в `web/mod.rs`), прогнать `./scripts/check.sh`
- [x] Закоммитить и запушить `mini-assistant` (`9bcbda8`), задеплоить через `./scripts/deploy.sh`, пройти `./scripts/verify_deploy.sh` и проверить на живой Mini
- [x] Обновить план, `docs/STATE.md`, закоммитить и запушить `gpt-mini`

## Проверки, результаты и ограничения

- `./scripts/check.sh` → host macOS → `RESULT PASS (5/5 stages passed)` (`format`, `lint`, `rust`: `289 lib` + `3 bin` + `9 bcm_attach` + `298 main` + `8 integration`, `vendor`, `python`).
- `./scripts/deploy.sh && ./scripts/verify_deploy.sh` → GPT Mini (`10.77.0.111`) → `PASS=23 FAIL=0`, `BUILD_INFO` = `9bcbda84d268c7b03e2353ea181d70dc52e17647`, SHA256 бинарника `b4dd640dc7e080593b4985c544589acebf86eca432b6acb3d868bd01e1c19982`, `available=163376 kB`.
- `GET http://127.0.0.1:8080/api/v1/status` и `soloist-ctl status` на Mini → отдаёт `"reachable": true, "is_active": true, "is_playing": false`, сессия `logged in: yes`. Живой перехват при активно играющем MacBook покрыт unit-тестом с mock HTTP/fake `soloist-ctl`, на физическом стенде проверяется переключением воспроизведения на Mac и вызовом «включи музыку» / кнопкой UI.

## Откат и открытые вопросы

- Откат: `git revert 9bcbda8` в `mini-assistant` и повторный `./scripts/deploy.sh`.
- Пауза (`spotify_pause` / `/api/spotify/pause`) намеренно НЕ перехватывает неактивное устройство, чтобы не сбрасывать активный плеер при случайной команде «стоп».
