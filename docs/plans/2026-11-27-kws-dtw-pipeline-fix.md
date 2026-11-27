# План: Исправление DTW-пайплайна wakeword (Вариант 1 — Rustpotter MFCC/DTW + Enrollment)

- Статус: in-progress
- Дата: 2026-11-27
- Репозиторий и владелец: `mini-assistant` + `gpt-mini`

## Задача и критерии готовности

Пользователь выбрал Вариант 1: устранить структурные дефекты текущего пайплайна Rustpotter MFCC/DTW (`vendor/rustpotter-ref` и `src/wakeword/enrollment.rs`), не переходя пока к нейросетевому KWS (Вариант 2 в резерве), и проверить реальный потолок DTW на GPT Mini при чистом переобучении фразы «Штучка-интеллект».

Критерии готовности:
1. В `vendor/rustpotter-ref/src/wakewords/comp/wakeword_comp.rs` нормализация и выравнивание скользящего окна `audio_mfcc_window` переведены с префикса (`0..target_len`) на суффикс (`len - target_len..len`), чтобы все шаблоны выравнивались по свежему концу речи без отставания на длину самого длинного шаблона.
2. В `src/wakeword/enrollment.rs`:
   - подрезание (`trim_enrollment`) ужесточено (`threshold = (peak * 0.30).max(noise * 3.0).min(peak * 0.65)`, допустимая внутренняя пауза `<= 28` фреймов / `280 мс` с сохранением составной паузы `250 мс`, отступы `10` фреймов до / `12` после, ограничение длительности `<= 48_000` семплов / `3.0 с` в соответствии с `MfccWavFileExtractor`);
   - расчёт SNR в `process_sample` использует реальный 10-й процентиль тихих фреймов `raw_pcm` вместо искусственного `trimmed_rms * 0.3`;
   - анализ и отбор шаблонов (`analyze_samples` / выбор до 8 шаблонов) исключает длительностные и акустически изолированные выбросы (без выбора шаблонов с `0.000` сходством через `min(min_sim)`), использует корректное направление сравнения `(longer, shorter)` и сбалансированный отбор по фазам;
   - `compile_reference` передаёт `None, None` для `threshold` и `avg_threshold`, не зашивая устаревшие пороги внутрь `.rpw`.
3. Все 5 стадий `./scripts/check.sh` проходят на macOS без предупреждений Clippy; `kws_sweep` подтверждает рост/стабильность разделения между wakeword и обычной речью/музыкой/тишиной.
4. Чистый коммит, сборка ARM32 (`armv7-unknown-linux-musleabihf`), деплой на GPT Mini (`10.77.0.111`) через `./scripts/deploy.sh`, `PASS` от `./scripts/verify_deploy.sh` и настройка runtime (`avg_threshold = 0.0`).
5. Проверка на устройстве: сценарий чистого переобучения и последующий тест (обычная речь ~2 мин с 0 ложных срабатываний + живые обращения «Штучка-интеллект»).

## Исходное состояние и ограничения

- Базовый коммит `mini-assistant`: `894702d`, рабочее дерево чистое.
- Живой конфиг на Mini (`rev = 4`): `score_mode = "max"`, `threshold = 0.48`, `avg_threshold = 0.20`, `min_scores = 6`. При нём за 2 минуты обычной речи было `0` ложных срабатываний, но живой wakeword отклонялся (`0.462..0.495` либо не набирал 6 кадров, либо резался `avg_score = 0.174..0.182 < 0.20`).
- Анализ живого `keyword.rpw` и оффлайн-корпуса (`scratch/corpus_check`, вне Git):
  - старый `keyword.rpw` содержал 8 шаблонов от `0.63 s` до `2.43 s` с `0.000` попарным DTW-сходством;
  - в `Clean.rpw` (`hall_kw_01..06`, обрезанных до `1.90..2.00 s`) при `avg_threshold = 0.0`, `threshold = 0.48..0.50`, `min_scores = 5` получено `hall = 12/12`, `sil_fa = 0`, `music_fa = 0`, `meas_fa = 0`; при этом `t-2 (189)` vs `t-0 (195)` при однонаправленном `compare` давало `0.000`, а обратное `t-0 (195)` vs `t-2 (189)` — `0.641`.
- Аппаратные ограничения: A113X **ELF32 ARM/armhf**, `glibc 2.23`, ~236 MiB RAM; `CARGO_TARGET_DIR` диагностического стенда `scratch/kws_sweep` изолирован от основного `mini-assistant/target`.
- Ограничение одной задачи: не смешивать с задачей proportional ducking / `cue` и не внедрять Вариант 2 (NN KWS) в рамках этого цикла.

## Шаги

- [x] Контракт и минимальное воспроизведение (`kws_sweep` на сохранённом корпусе + аудит `normalize_prefix` / `enrollment.rs`)
- [x] Реализация суффиксного выравнивания в `vendor/rustpotter-ref/src/wakewords/comp/wakeword_comp.rs` и юнит-тест
- [x] Реализация исправлений в `src/wakeword/enrollment.rs` (тримминг, реальный SNR, симметричное сравнение / фильтрация выбросов / фазовый отбор, `None, None` в `compile_reference`) и регрессионные тесты
- [x] Проверка на корпусе через `kws_sweep` и полная локальная проверка `./scripts/check.sh`
- [x] Ревью финального diff, атомарный коммит (`e0b261a`) и push в GitHub
- [x] Сборка ARM32, деплой на GPT Mini (`./scripts/deploy.sh`), проверка `./scripts/verify_deploy.sh` и обновление `avg_threshold = 0.0`
- [ ] Живая валидация с пользователем после чистого переобучения «Штучка-интеллект» (обычная речь ~2 мин + живые вызовы)

## Проверки, результаты и ограничения

- До изменений: `cargo test --locked --manifest-path mini-assistant/vendor/rustpotter-ref/Cargo.toml --no-default-features` → `11 passed; 0 failed` (+ 1 doctest).
- После изменений:
  - `./scripts/check.sh` (`mini-assistant`, коммит `e0b261a`): **PASS (5/5 этапов)** (`format`, `lint`, `rust`, `vendor`, `python`).
  - `kws_sweep`: на реальных `hall_kw_01..10` сходство в матрице `(1 - norm_cost)` выросло с ложных `0.000` (при `|len_a - len_b| = 6..9`) до `0.703..0.973`; `Clean.rpw` (`hall_kw_01..06`, `1.90..2.00 s`) при `thr=0.46..0.48`, `avg=0.00`, `min_scores=5..6` дал `hall=12/12`, `sil_fa=0`, `music_fa=0`, `meas_fa=0` (против `neg_fa=20` на старом `keyword.rpw`).
  - ARM32 бинарник `mini-assistant`: `4.5M`, SHA256 `d0fcf765fde16609e3a2b6c8bbf84583d57cb99a57645c3c306e75fdf3ebcb46`.
  - `./scripts/verify_deploy.sh`: **PASS=23 FAIL=0** (`BUILD_INFO = e0b261a5a91c0a7385997ec4c30e9e3dc4077346`, `dirty=clean`, `available=141900 kB` RAM).
  - Runtime конфиг через `POST /api/v1/acoustics` (`rev=1`): `avg_threshold = 0.0` (`saved` + `applied`), `threshold = 0.48`, `min_scores = 6`, `score_mode = "max"`.
  - Ограничение: на устройстве пока загружена прежняя модель `.rpw` (`d661892...`) — живое тестирование требует чистого переобучения через Web UI.

## Откат и открытые вопросы

- Изменяемые файлы: `mini-assistant/vendor/rustpotter-ref/src/wakewords/comp/wakeword_comp.rs`, `mini-assistant/src/wakeword/enrollment.rs`, при необходимости дефолты/UX в `src/config.rs` или `src/web/dashboard.html`.
- Откат кода: `git revert` коммита в `mini-assistant`. Откат бинарника на устройстве: встроенный механизм `./scripts/deploy.sh` (`mini-assistant.prev`). Модель `.rpw` переобучается через Web UI; при полном провале DTW на чистых шаблонах переходим к Варианту 2 (отдельным планом).
