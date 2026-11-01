# Проверки и критерии готовности

## Матрица

| Изменение | Обязательная релевантная проверка |
|---|---|
| Только Markdown/workflow | Ссылки, staged diff, базовый secret guard; без Mini и ARM-сборки |
| Rust-код | fmt, clippy без warnings, tests; regression/contract tests для поведения |
| Rust Linux/audio path, сборка, зависимости | Предыдущее + целевая ARM32-сборка, ELF/dependency и runtime-helper inspection |
| C/Python wire, буферы, сессии | Offline tests, strict host C build; target build при изменении target-кода |
| Конфиг HA/Spotify/model API | Fixtures/mock transport, timeout/ошибки; внешний smoke отдельно |
| Работа с реальным звуком/сервисом Mini | Локальные проверки + ограниченный опыт, baseline, post-check, cleanup |
| Boot/firmware/доступ/маршрутизация | Проверка точной платформы, backup и способ восстановления до изменения |

Не создавать тесты ради числа тестов. Проверять публичный контракт и
действительные риски. Для низкорисковой обратимой правки достаточно проверки
изменённого поведения без нового набора тестов.

## Общие документы и guard

Из корня `gpt-mini`:

```sh
python3 scripts/check_workflow.py
python3 -B -m unittest discover -s tests -v
python3 scripts/check_workflow.py --staged
git diff --cached --check
```

Корневой guard проверяет только файлы этого репозитория. Приватный архив и
вложенный Git не сканируются и не публикуются. Данные нового корневого коммита
проверяются из индекса Git, а не из случайно изменённой рабочей копии.

## Rust-приложение

```sh
cd mini-assistant
./scripts/check.sh
```

Это форматирование, clippy и host tests. На момент настройки текущий Rust
playback запускает внешний `aplay`, без зависимости от ALSA development
libraries при сборке. Проверять наличие/совместимость helper на Mini отдельно.
Host checks на macOS/Linux не подтверждают реальное воспроизведение.
Target-сборка и запуск устройства описываются отдельно в CONTRIBUTING приложения.
Не запускать `deploy.sh` как тест: это операция с реальным устройством.

## Исследовательские C/Python-прототипы

Это локальный архив вне корневого Git/CI. При наличии архива, Python 3 и
POSIX C-компилятора выполнить из корня:

```sh
python3 -B -m unittest discover -s research/alice-mini-2019/runtime/mini_session -p 'test_*.py' -v
python3 -B -m unittest discover -s research/alice-mini-2019/lab/tools -p 'test_*.py' -v
```

Наборы используют fixtures, временные каталоги, pipes/socketpair и host C
stand-in. Они не подключаются к Mini/Pi. Linux-only PDEATHSIG test на Mac
пропускается; skip отражается в отчёте. Отдельный native core test:

```sh
workdir=$(mktemp -d)
cc -std=c11 -O2 -Wall -Wextra -Werror -I research/alice-mini-2019/runtime/mini_session research/alice-mini-2019/runtime/mini_session/mini_session_core.c research/alice-mini-2019/runtime/mini_session/test_session_core.c -o "$workdir/test-session-core"
cc -std=c11 -O2 -Wall -Wextra -Werror -I research/alice-mini-2019/runtime/mini_session research/alice-mini-2019/runtime/mini_session/mini_session_core.c research/alice-mini-2019/runtime/mini_session/mini_session_cli.c research/alice-mini-2019/runtime/mini_session/mini_session_pcm.c -o "$workdir/mini_session_cli"
"$workdir/test-session-core" "$workdir/mini_session_cli"
rm -r "$workdir"
```

Не путать эти команды с `direct_*_lab.py` и cross-build scripts: последние
имеют другие зависимости и могут изменять реальный стенд.

## Что писать в результате

Для каждой проверки: команда, среда/target, результат, skips и ограничение.
«Данные приняты ALSA» не равно «пользователь услышал звук»; control roundtrip
не равно задержке голосового диалога. RSS измерять отдельно от размера ELF
и установленных resource limits. При отказе сохранять причину без секретов.
