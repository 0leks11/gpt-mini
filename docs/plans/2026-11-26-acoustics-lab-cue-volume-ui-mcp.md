# План: Починка видимости профилей и расширение Акустической лаборатории (Beep-подсказки, громкость, воспроизведение сэмплов, API, MCP и UI)

- Статус: done
- Дата: 2026-11-26
- Репозиторий и владелец: `mini-assistant` (`894702d`, тег `release/2026-11-26-894702d`) / `gpt-mini`

## Задача и критерии готовности

1. Профили помещений в `/data/opt/mini-assistant/profiles.json` и записи в `/data/opt/mini-assistant/samples/` видны и управляемы в веб-интерфейсе `http://<ip>:8080/acoustics` без ручной подстановки Bearer-токена (сохраняя `401 Unauthorized` для анонимных внешних запросов без same-origin контекста браузера).
2. Агент (через REST API и MCP) и пользователь (через UI `/acoustics`) могут:
   - подавать короткий звуковой сигнал (`POST /api/v1/acoustics/cue`, `play_acoustic_cue`) для проверки бодрствования динамика и старта фразы пользователя;
   - запускать запись фразы после звукового сигнала с звуковым подтверждением приёма (`cue_before` / `cue_after` в `CreateJobDto` и MCP-инструмент `prompt_and_capture_phrase`);
   - управлять громкостью (`0–10` / Soloist `%`) и фоновым воспроизведением музыки Soloist (`GET/POST /api/v1/acoustics/volume`, `/api/v1/acoustics/reference_playback`) с соблюдением лимита `CalibrationLease.max_volume_pct`;
   - загружать произвольные WAV-файлы с автоконвертацией в `16 kHz mono PCM16` (`auto_convert=true`), проигрывать их на динамике через измерительный джоб (`StimulusSignal::Sample`) и проверять скоринг KWS (`evaluate` по одному `sample_id` или корпусу).
3. Все проверки (`check.sh`: format, clippy `-D warnings`, Rust + Python тесты), сборка ARM32, деплой на GPT Mini и `verify_deploy.sh` (`PASS=23 FAIL=0`) пройдены.

## Исходное состояние и ограничения

- На устройстве уже сохранены 3 профиля (`prof_7d49...`, `prof_81be...`, `prof_fe60...`) и 44 сэмпла, однако `web/mod.rs` определял `same_origin` только по заголовку `Origin` (который браузеры не отправляют на `GET`), поэтому `GET /profiles`, `/samples`, `/jobs`, `/sessions`, `/aec` возвращали `401 Unauthorized`.
- `AcousticJobRunner` + `RealPlaybackSink` уже поддерживают `StimulusSignal::Sample`, но UI выставлял только `chirp_sweep`/`silence`, не было загрузки WAV, громкости, воспроизведения Soloist и звуковых сигналов-маркеров.
- Физическое ограничение M-AEC: звук, воспроизводимый самой Mini (`OwnOutput` / `BuiltIn`), попадает в аппаратный loopback `Ch6 TDMIN_B` и подавляется M-AEC+RES до ~`-77 dBFS` (тестирует самоподавление, а не распознавание живой речи; для оценки отклика KWS на чистую/стороннюю запись используется прямая подача сэмпла в `evaluate` либо внешний источник звука).

## Шаги

- [x] Контракт, аудит auth/UI/jobs/MCP и минимальное воспроизведение
- [x] Backend: `same_origin` GET fix, `auto_convert` WAV нормализация, `cue` / `cue_before` / `cue_after`, `volume` & `reference_playback` API, single-sample `evaluate`, `auth.rs`, `openapi.rs`
- [x] Frontend & MCP: обновление `acoustic_lab.html` и `mcp_acoustic_agent.py`
- [x] Тесты (`cargo test`, Python `test_acoustic_ui.py` / `test_mcp_acoustic_agent.py`, `scripts/check.sh`)
- [x] Деплой на GPT Mini, `verify_deploy.sh`, живые HTTP/акустические проверки, обновление `docs/STATE.md` и пуш

## Проверки, результаты и ограничения

- Выполнены и пройдены: `cd mini-assistant && cargo fmt && bash scripts/check.sh` (`RESULT PASS (5/5 stages passed)`: 587 Rust тестов + 40/41 Python тестов OK + 1 opt-in live test skipped), `./scripts/deploy.sh` (ARM32 `4.4M`, `sha256: 276d5353d3679fe1b452785f50f2d9ba63be4f3bd00571b76b4779f0a22e51ca`), `./scripts/verify_deploy.sh` (`PASS=23 FAIL=0`), живые `curl` проверки `/profiles` (`401` без заголовков, `200` с `Sec-Fetch-Site: same-origin` — видны 3 профиля), `/samples?split=calibration` (`43` сэмпла), `/volume` (`level=1`, `soloist_pct=42`), `/reference_playback` (`available=true`, `paused`), `POST /cue` (`ready`, `played_ms=260`, `peak_amplitude=8231`).
- Ограничение физики при воспроизведении стороннего wake-word WAV из собственного динамика Mini: сигнал попадает в loopback M-AEC и подавляется на ~17–32 дБ; плюс модель `keyword.rpw` (DTW) привязана к голосу владельца, поэтому для прямой оценки чувствительности используется `POST /api/v1/acoustics/evaluate` («Проверить KWS»).

## Откат и открытые вопросы

- Откат кода: `git revert` коммита или `mv mini-assistant.prev mini-assistant && /etc/init.d/S99mini_assistant restart`.
