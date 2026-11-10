# План: глубокое ревью кода и правил агентов

- Статус: done
- Дата: 2026-11-01
- Область: root workflow и mini-assistant, без deployment/изменений стенда

## Задача и критерии

Проверить текущий код, приложенный журнал и инструкции, воспроизвести
значимые дефекты локальными fixtures, внести ограниченные исправления и
подготовить честную сводку подтверждённого состояния и открытых рисков.

## Исходное состояние

Root HEAD `cab9e6f`; child HEAD `6b93d20`. В приложении до начала ревью уже
изменены `src/audio/playback.rs`, `config.example.toml` и
`docs/experiments/2026-11-01-initial-device-smoke-test.md`. Эти изменения
не откатываем; к эксперименту добавляем отдельное уточнение.

Baseline: root guard 8 passed; Rust fmt/clippy/tests pass, 15 tests.
Зелёный baseline не покрывает модельные события, subprocess playback,
HTTP-ошибки HA и ошибки deployment.

## Владение файлами

- Audio reviewer: только VQE и Gemini module, встроенные regression tests.
- HA reviewer: HA client/config/main/docs, минимальная date dependency.
- Deploy reviewer: deploy/check scripts, tests, ignore и CI.
- Координатор: root docs, README/SETUP/ARCHITECTURE, итоговое ревью/проверки.

## Шаги

- [x] Изучить исходное дерево, журнал и baseline проверок.
- [x] Независимо проверить audio/Live, HA/config, workflow/deployment.
- [x] Воспроизвести parser/event/deployment ошибки на fixtures.
- [x] Внести ограниченные исправления и regression tests.
- [x] Проверить совокупный diff, host gate, ARM artifact и документацию.
- [x] Обновить STATE и итоговую сводку, назвать оставшиеся blockers.

## Финальные проверки

32 Rust-теста,8 fake-deployment тестов,8 тестов root guard прошли; fmt/clippy без
ошибок. Исследовательские Python suites:98 passed + 1 Linux-only skip; C:15 групп.
Офлайн ARM32 release build прошёл; snapshot совпал с исходниками. Итог:
[сводка ревью](../DEEP_REVIEW_2026-11-01_RU.md).

## Границы

Не включаем устройства, не меняем маршрутизацию/NAT/OTA/SSH и не отправляем
настоящую речь или команды в HA/облако. Loopback fixtures не используют
реальные аккаунты. Непроверенные сообщения из чужого журнала помечаем
reported, а не результатом сегодняшнего прогона.
