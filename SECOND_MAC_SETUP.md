# Руководство по подключению и настройке второго Mac

В этой инструкции собраны все данные, сетевые адреса, конфигурации и команды для быстрой настройки вашего второго MacBook, чтобы вы могли полноценно работать с сервером разработки Dell, платой Raspberry Pi и Telegram-ботом.

---

## 1. Параметры сети и устройств

### Локальная сеть Wi-Fi (пространство FFFF)
* **Имя сети (SSID):** `ffff`
* **Пароль Wi-Fi:** `forfriends`
* **Шлюз / Главный роутер (MikroTik):** `10.77.0.1`
* **Диапазон адресов:** `10.77.0.0/24`

### Сервер разработки Dell (`olekserver`)
Ноутбук Dell Inspiron N7110 — выделенный сервер, на котором крутится Telegram-агент OMP и хостятся все проекты.
* **Имя хоста:** `olekserver`
* **Пользователь Linux:** `oleksii`
* **Локальный Wi-Fi IP:** `10.77.0.116`
* **Tailscale VPN IP:** `100.96.169.1`
* **Рабочая папка проектов:** `/home/oleksii/workspace`
* **Порт SSH:** `22`
* **Установленное окружение:** Node.js v26.13.0 LTS, pnpm, OMP v18.18.0, Git, Python 3, rsync.
* **Активная модель ИИ по умолчанию:** `google-antigravity/gemini-3.8-flash`

### Плата Raspberry Pi 4 Model B (`oleksii-pi`)
Плата умного дома, к которой подключён Home Assistant и кондиционер.
* **Имя хоста:** `oleksii-pi`
* **Пользователь Linux:** `oleksii`
* **Локальный Wi-Fi IP:** `10.77.0.110`
* **Tailscale VPN IP:** `100.67.101.12`
* **Веб-интерфейс Home Assistant:** `http://10.77.0.110:8123` или `http://100.67.101.12:8123`
* **Порт SSH:** `22`

---

## 2. Пошаговая настройка второго Mac

### Шаг 1. Подключение к сети Tailscale (для доступа из любой точки мира)
1. Установите [Tailscale для macOS](https://tailscale.com/download/mac).
2. Авторизуйтесь под вашим общим аккаунтом: `ak.kozyrev01@...`.
3. После входа второй Mac автоматически появится в общей mesh-сети и сможет напрямую подключаться к Dell (`100.96.169.1`) и Raspberry Pi (`100.67.101.12`), даже если вы находитесь в другой сети или в кафе.

---

### Шаг 2. Генерация SSH-ключа на втором Mac
Откройте терминал на втором Mac и выполните:
```bash
ssh-keygen -t ed25519 -C "second-mac"
```
*(При запросе пути и пароля просто нажимайте `Enter`)*.

Посмотрите ваш сгенерированный публичный ключ:
```bash
cat ~/.ssh/id_ed25519.pub
```
Скопируйте эту строчку (она начинается на `ssh-ed25519 AAAAC3...`).

---

### Шаг 3. Добавление ключа второго Mac на Dell и Raspberry Pi

Чтобы второй Mac мог заходить на сервер Dell и Raspberry Pi без пароля:

#### Вариант А: Добавить через этот чат (самый быстрый)
Просто скопируйте и пришлите мне в чат вывод команды `cat ~/.ssh/id_ed25519.pub` со второго Mac — я сам мгновенно добавлю его в `authorized_keys` на Dell и Raspberry Pi!

#### Вариант Б: Добавить вручную с первого Mac
Выполните на вашем **первом Mac**:
```bash
# Добавить на Dell
ssh olekserver "echo 'ВАШ_НОВЫЙ_ПУБЛИЧНЫЙ_КЛЮЧ' >> ~/.ssh/authorized_keys"

# Добавить на Raspberry Pi
ssh oleksii@10.77.0.110 "echo 'ВАШ_НОВЫЙ_ПУБЛИЧНЫЙ_КЛЮЧ' >> ~/.ssh/authorized_keys"
```

---

### Шаг 4. Настройка файла `~/.ssh/config` на втором Mac
Создайте или отредактируйте файл `~/.ssh/config` на втором Mac:
```bash
nano ~/.ssh/config
```
Вставьте следующий блок конфигурации:

```ssh-config
# Сервер Dell через глобальный Tailscale (работает везде)
Host olekserver
    HostName 100.96.169.1
    User oleksii
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking accept-new

# Сервер Dell через локальный домашний Wi-Fi ffff
Host olekserver-local
    HostName 10.77.0.116
    User oleksii
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking accept-new

# Raspberry Pi Home Assistant через Tailscale
Host oleksii-pi
    HostName 100.67.101.12
    User oleksii
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking accept-new

# Raspberry Pi через локальный Wi-Fi ffff
Host oleksii-pi-local
    HostName 10.77.0.110
    User oleksii
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking accept-new
```
Сохраните файл (`Ctrl + O`, затем `Enter`, затем `Ctrl + X`).

Проверьте подключение со второго Mac:
```bash
ssh olekserver
```
Вы сразу окажетесь в консоли вашего сервера Dell!

---

## 3. Передача файлов и синхронизация кода

### Вариант 1: Быстрая отправка через `rsync`
Чтобы скопировать проект со второго Mac на Dell:
```bash
rsync -avz --exclude 'node_modules' --exclude '.git' ~/Documents/мой-проект/ olekserver:/home/oleksii/workspace/мой-проект/
```
Чтобы скачать результат работы бота обратно на второй Mac:
```bash
rsync -avz --exclude 'node_modules' olekserver:/home/oleksii/workspace/мой-проект/ ~/Documents/мой-проект/
```

### Вариант 2: Прямая работа в VS Code / Cursor через Remote SSH
1. Установите расширение **Remote - SSH** в VS Code / Cursor на втором Mac.
2. Нажмите `F1` $\to$ `Remote-SSH: Connect to Host...` $\to$ выберите `olekserver`.
3. Откройте папку `/home/oleksii/workspace`.
4. Вы сможете писать код на втором Mac так, будто файлы лежат локально, но физически они находятся на Dell, и Telegram-бот сразу видит все изменения.

### Вариант 3: Через Git / GitHub
1. На втором Mac создайте репозиторий и сделайте `git push`.
2. На сервере Dell зайдите в папку проекта и сделайте `git pull`:
   ```bash
   ssh olekserver "cd /home/oleksii/workspace/мой-проект && git pull"
   ```

---

## 4. Как управлять разработкой через Telegram

На втором Mac (или прямо со смартфона):
1. Откройте Telegram и зайдите в группу **VibeCoding Space**.
2. В теме **# General** поставьте задачу:
   ```text
   /new Сделай веб-страницу с таймером обратного отсчета и запусти локальный сервер
   ```
3. Бот **Creator Dev Bot** (@My\_Self\_Dev\_bot) создаст топик и выполнит задачу в папке `/home/oleksii/workspace` на Dell с помощью модели **Gemini 3.8 Flash**.
