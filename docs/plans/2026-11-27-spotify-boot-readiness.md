# План: Надёжная последовательность холодного старта и защита Spotify Connect (`run-supervisor.sh`)

- Статус: deployed (остаётся контрольный `reboot` / цикл питания пользователем)
- Дата: 2026-11-27
- Репозиторий и владелец: `mini-assistant` (`b454de6`) + `gpt-mini`

## Задача и критерии готовности

При выключении питания или переносе GPT Mini в другую комнату и повторном включении все службы должны запускаться строго после готовности своих зависимостей, чтобы проприетарный `soloist` (Spotify Connect) не стартовал раньше IPv4, DNS и TLS до серверов Spotify и не аннулировал сохранённую OAuth-сессию.

Критерии готовности:
1. В `mini-assistant/scripts/run-supervisor.sh` без перекройки остального кода добавлена аккуратная поэтапная проверка готовности:
   - `network_ipv4_ready()`: наличие IPv4 на `wlan0` и default route через `ip -4` (ожидание до 30 с на холодном старте до запуска `mini-assistant` / `watchdog_loop`, даже если системный год уже `>= 2026`);
   - `spotify_network_ready()`: в `watchdog_loop` перед запуском `soloist-run.sh` проверяется `YEAR >= 2026`, `network_ipv4_ready()`, DNS-резолв (`nslookup`) и реальный HTTPS-ответ с системным CA-бандлом (`wget --ca-certificate=/etc/ssl/certs/ca-certificates.crt -T 4 -t 1 -q -O /dev/null https://apresolve.spotify.com`), без спама в лог;
   - однократный `sync` на уровне ОС после перехода `soloist-ctl status` в `logged in: yes`, чтобы токен фиксировался на UBIFS-флэш до возможного снятия питания.
2. Покрыто изолированными Python unit-тестами (`mini-assistant/tests/test_supervisor.py`) с подменёнными бинарниками (`ip`, `nslookup`, `wget`, `date`, `soloist-ctl`, `chronyc`), проверяющими сценарий `fe80`-линка / падения DNS / восстановления сети.
3. Все стадии `./scripts/check.sh` проходят (`PASS`); деплой на Mini через `./scripts/deploy.sh` обновляет `run-supervisor.sh` и проходит `./scripts/verify_deploy.sh` (`PASS`, сохраняя живую текущую авторизацию `soloist`).

## Исходное состояние и ограничения

- Инцидент в логах (`2026-11-27T13:28:26–13:28:32Z`): при загрузке системный год уже был `2026`, `wait_for_ntp` прошёл за 0 с без проверки `wlan0` IPv4, через 4 с `watchdog_loop` запустил `soloist`, который увидел только `[fe80::...%wlan0]`, словил `CURL error: 6` при `restoreCurrentSession` и сам выполнил `Invalidating oauth client for session` (`LOGGED_OUT`), за 1 с до готовности mDNS/DNS.
- На Mini доступны: `/sbin/ip`, `/usr/bin/nslookup`, `/usr/bin/wget` (`GNU Wget 1.20`), `/bin/ping`, `/usr/bin/chronyc`, `/etc/ssl/certs/ca-certificates.crt`. Отсутствуют: `nc`, `curl`, `openssl`, `dig`, `timeout`.
- Скрипт `S81spotify` неактивен (нет `spotify.conf`).
- Живое состояние сейчас: пользователь уже повторно авторизовал `soloist` (`logged in: yes`), важно не перезаписывать/не сбрасывать `soloist-data`.

## Шаги

- [x] Диагностика цепочки `/etc/init.d/rcS` → `S99mini_assistant` → `run-supervisor.sh` → `soloist.log` и доступных утилит Mini
- [x] Минимальная правка `mini-assistant/scripts/run-supervisor.sh` (IPv4/route check, DNS+HTTPS gate перед `soloist`, однократный `sync` при авторизации, защита от спама логов)
- [x] Добавление тестов `mini-assistant/tests/test_supervisor.py` и прогон `./scripts/check.sh` (3 прогона `tests.test_supervisor` под `-W error` PASS; `./scripts/check.sh` PASS 5/5)
- [x] Атомарный коммит и push (`b454de6`), деплой на Mini (`./scripts/deploy.sh`) и проверка `./scripts/verify_deploy.sh` (`PASS=23 FAIL=0`, SHA256 `run-supervisor.sh`: `3cbaa0887f7271244ce79b558e488652c85fd4dc04ab5a1d4a0be9b2b519db04`)
- [x] Подтверждение сохранности `logged in: yes`, BusyBox `sh -n` и живой проверки сети (`SPOTIFY_NET_GATE_OK`)

## Откат и открытые вопросы

- Изменяемый runtime-файл на Mini: `/data/opt/mini-assistant/run-supervisor.sh` (SHA256 `3cbaa0887f7271244ce79b558e488652c85fd4dc04ab5a1d4a0be9b2b519db04`, деплоится из `mini-assistant/scripts/run-supervisor.sh`). Откат: `git revert b454de6` + повторный `./scripts/deploy.sh`.
- Опциональная проверка на реальном стенде: выполнить `reboot` или кратковременное снятие питания для наблюдения вживую задержки `Delaying Spotify Soloist startup` и автоматического старта `soloist` с `logged in: yes`.
