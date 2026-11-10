# Опыт: Перевод Станции Мини в сеть ACAB и восстановление прямого выхода в Интернет — 3 ноября 2026

- Дата / ответственный: 2026-11-03 / Antigravity
- Основание в задаче пользователя: Запрос пользователя: «routing , need fix internet connection to station mini new wifi ACAB wil be used» после перемещения Raspberry Pi в сеть ACAB (`192.168.1.113`) по кабелю.

## Гипотеза и измерение

- **Гипотеза:**
  1. Включение виртуальной точки доступа Станции Мини `WifiMaster0/AccessPoint3` (SSID `shergo`) в основной домашний мост Keenetic `Bridge0` (сеть ACAB) переведёт Станцию Мини в единую L2-подсеть `192.168.1.0/24`.
  2. Удаление устаревшей переопределённой конфигурации шлюза (`192.168.77.2`) в `/etc/dhcpcd.conf` Станции Мини позволит ей получить штатный шлюз `192.168.1.1` и DNS `192.168.1.1` от DHCP Keenetic.
  3. Прямой SSH-доступ с Mac (`192.168.1.69`) к Станции Мини (`192.168.1.110:2222`) заработает без промежуточных JumpHost.
  4. Станция Мини получит полноценный прямой доступ в Интернет (Gemini Live API) и прямую связь с Home Assistant на Pi (`http://192.168.1.113:8123`).
- **Что не проверяется:** Живой захват речи и физическое воспроизведение через динамик (согласно указанию пользователя акустические испытания отложены).

## Preflight

- Устройство: Yandex Station Mini 1 (`YNDX-0004`), A113X Cortex-A53 (armhf), glibc 2.23, ядро 4.9.68. MAC: `b0:02:47:4c:70:56`.
- Сеть до изменения:
  - Роутер Keenetic KN-1212 (`192.168.1.1` на `Bridge0`, `192.168.77.1` на `Bridge3`).
  - `WifiMaster0/AccessPoint3` (SSID `shergo`) находился в изолированном мосте `Bridge3` с `security-level protected` и блокирующим ACL `MiniLab_20261023_v2`.
  - Raspberry Pi отключил Wi-Fi `wlan0` (ранее `192.168.77.2`) и был переведён кабелем на порт 1 Keenetic в сеть `Bridge0` с IP `192.168.1.113`.
  - Станция Мини не имела маршрута наружу из-за изоляции `Bridge3` и жестко зашитого в `/etc/dhcpcd.conf` адреса мертвого шлюза `192.168.77.2`.
- Сняты резервные копии Keenetic `running-config` и `startup-config.txt` в `.private/alice-mini/reviews/2026-11-03-routing/`.

## Действия

1. **Keenetic CLI (KN-1212):**
   - Удаление AP3 из изолированного сегмента: `interface Bridge3 no include WifiMaster0/AccessPoint3`.
   - Включение AP3 в домашнюю сеть: `interface Bridge0 include WifiMaster0/AccessPoint3`.
   - Закрепление постоянного DHCP-адреса для Мини: `ip dhcp host YandexStationMini b0:02:47:4c:70:56 192.168.1.110`.
   - Мягкий перезапуск радиоинтерфейса: `interface WifiMaster0/AccessPoint3 down`, пауза 2с, `up`.
   - Сохранение настроек в энергонезависимую память: `system configuration save`.
2. **Станция Мини (Dropbear SSH:2222):**
   - Проверка получения аренды: интерфейс `wlan0` получил `192.168.1.110/24`.
   - В `/etc/dhcpcd.conf` очищены принудительные строки `static routers=192.168.77.2` и `static domain_name_servers=8.8.8.8` (резервная копия сохранена в `/etc/dhcpcd.conf.bak20261103`).
   - Переключен маршрут по умолчанию на `192.168.1.1`.
3. **Локальная конфигурация (`mini-assistant`):**
   - В `.env` обновлены: `MINI_HOST=192.168.1.110`, отключен `MINI_JUMP_HOST`, `HA_URL=http://192.168.1.113:8123`.
   - В `config.toml` обновлен: `url = "http://192.168.1.113:8123"`.
   - Запущен деплой `./scripts/deploy.sh`: собран и залит свежий musl static бинарник `mini-assistant` и `mini_pcm_sink`.

## Восстановление (Rollback Plan)

- В случае сбоя моста:
  ```text
  interface Bridge0 no include WifiMaster0/AccessPoint3
  interface Bridge3 include WifiMaster0/AccessPoint3
  no ip dhcp host b0:02:47:4c:70:56
  interface WifiMaster0/AccessPoint3 down && interface WifiMaster0/AccessPoint3 up
  system configuration save
  ```
- Исходный `/etc/dhcpcd.conf` доступен на Мини в `/etc/dhcpcd.conf.bak20261103`.

## Результаты измерений

1. **Сетевой статус Keenetic:**
   - Станция Мини ассоциирована на `WifiMaster0/AccessPoint3` (SSID `shergo`), авторизована (WPA2-PSK CCMP), RSSI -42 dBm.
   - Выдан IP `192.168.1.110`, статус аренды в Keenetic: активна.
2. **Прямой доступ с Mac (`192.168.1.69`):**
   - ICMP ping к `192.168.1.110`: 3 пакета, 0% потерь, RTT ~77..97 мс.
   - SSH `root@192.168.1.110:2222` открывается напрямую без прокси за 0.3 с.
3. **Интернет со Станции Мини:**
   - DNS-запрос к `generativelanguage.googleapis.com` успешно резолвится в `172.217.114.4`.
   - ICMP ping к `8.8.8.8`: 3 пакета, 0% потерь, RTT ~28..31 мс.
   - ICMP ping к `generativelanguage.googleapis.com`: 2 пакета, 0% потерь, RTT ~27..35 мс.
4. **Связь Станция Мини ↔ Home Assistant:**
   - HTTP GET `http://192.168.1.113:8123/manifest.json`: HTTP 200 OK.
5. **Деплой приложения:**
   - На Станцию Мини доставлены и проверены по SHA256:
     - `/data/opt/mini-assistant/mini-assistant`: `c067433d89ede0380dafb8dc21ea4e4a7ba109fbfe8d57b21ebf12f9cb5249c3`.
     - `/data/opt/mini-assistant/mini_pcm_sink`: `f8d8c8a3290c0b0417feeb187850d334966866fcfe398c01bab8eaa88c34d60d`.
     - Актуальные `.env` и `config.toml` синхронизированы.
