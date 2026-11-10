# Отчёт: Прохождение гейтов G0, G1, G2 и аудит холодной загрузки Mini — 4 ноября 2026

- **Дата / время:** 2026-11-04 16:40 Asia/Tbilisi.
- **Исполнитель:** Antigravity.
- **Основание:** План [docs/plans/2026-11-04-independent-boot-recovery.md](../plans/2026-11-04-independent-boot-recovery.md).

---

## 1. Этап 0: Подтверждение сети и оборудования (Гейт G0: PASSED)

1. **Подключение Mac к LAN KN-1212:**
   - Mac переключён на Wi-Fi `ACAB` (SSID подтверждён через `ipconfig getsummary en0`).
   - IP Mac: `192.168.1.69/24`, шлюз по умолчанию: `192.168.1.1`.
2. **Верификация роутера KN-1212:**
   - Панель управления: `http://192.168.1.1` доступна.
   - Модель через API: `4G (KN-1212)`, версия KeeneticOS `4.3.9`.
   - BSSID MAC в ARP: `50:ff:20:89:31:c9` (соответствует LAN-интерфейсу KN-1212; WAN MAC был `50:ff:20:89:31:ca`).
3. **Обнаружение Станции Мини:**
   - Таблица активных клиентов Keenetic hotspot:
     `MAC=b0:02:47:4c:70:56`, `IP=192.168.1.110`, `Name=YandexStationMini`, `Active=True`, `Link=up`, `SSID=ACAB`.
   - ICMP ping с Mac к `192.168.1.110`: 3 пакета, 0.0% потерь, RTT 71–99 мс.
4. **Проверка Dropbear SSH:**
   - Порт 2222: открыт.
   - Сканирование ключа хоста: `[192.168.1.110]:2222 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPimOKqPmIGwjBC2J4XQthMUQ8VcTUqmFx0fASRV/geM`.
   - Сверка с `.private/alice-mini/usb-root-2026-10-25/ssh-ram-v2/known_hosts`: **100% точное совпадение**.

---

## 2. Этап 1: Получение реальной root-консоли (Гейт G1: PASSED)

1. Вход по SSH выполнен напрямую с Mac по ключу `client_ed25519` со строгой проверкой хоста (`StrictHostKeyChecking=yes`):
   ```text
   uid=0(root) gid=0(root) groups=0(root),10(wheel)
   12:36:44 up 1:05, load average: 1.00, 1.00, 1.00
   ```
2. Подтверждена возможность повторного входа, команды выполняются без задержек.

---

## 3. Этап 2: Снятие свежего baseline и подготовка восстановления (Гейт G2: PASSED)

1. **Резервные копии:**
   - Локально на Mac: `.private/alice-mini/reviews/2026-11-04-boot-recovery/backup/etc/` (все скрипты `init.d` и `inittab`).
   - На постоянном носителе Mini: `/bkupgrade/backup-20261104/` (копия `/etc/init.d` и `/etc/inittab`).
2. **Инвентаризация ядра и файловых систем:**
   - Ядро: `Linux YandexStationMini_7056 4.9.68 #1 SMP PREEMPT Fri Oct 30 13:02:07 MSK 2026 aarch64`.
   - Userspace: ARM 32-bit (armhf), glibc 2.23.
   - Точки монтирования:
     - `/` (rootfs): `/dev/ubi0_0`, ubifs, `rw,relatime`.
     - `/bkupgrade`: `/dev/ubi1_0`, ubifs, `rw,relatime`.
     - `/data`: канонический симлинк `/data -> /bkupgrade/data` присутствует.
   - Память:
     - `MemTotal: 242028 kB`, `MemFree: 171296 kB`, `MemAvailable: 194828 kB`.
     - Свободно около 195 МБ RAM (процессы Яндекса не занимают память).
3. **Процессы на устройстве:**
   - Процессов Яндекса (`maind`, `quasar_launcher2`, `mediad`, `updatesd`, `telemetry`): **0**.
   - Активны:
     - `wpa_supplicant` (PID 1313) на `wlan0`.
     - `dhcpcd` (PID 1683).
     - `chronyd` (PID 1688).
     - `unbound` (PID 1784).
     - `dropbear` (PID 1729) на порту 2222.
4. **Аппаратный контроллер светодиодов:**
   - I2C устройство: `sn3236@3c` на шине `i2c-0` (`/sys/bus/i2c/devices/0-003c`, 36-канальный LED-драйвер SI-EN SN3236).

---

## 4. Причины поведения устройства («голубой индикатор и тишина»)

1. **Почему колонка молчала после перезагрузки:**
   - Wi-Fi, DHCP и SSH **успешно поднялись сами** при холодной загрузке благодаря существующим скриптам `S40wifi`, `S41dhcpcd` и `S99zzmini_ssh`.
   - Однако на 13-й секунде загрузки скрипт `S99mini_assistant` запустил `mini-assistant`, когда сетевой стек (DNS в `unbound` / `chronyd`) ещё не завершил инициализацию.
   - `mini-assistant` завершился с ошибкой:
     ```text
     Error: Failed to start Gemini Live client
     Caused by:
         0: Failed to connect to Gemini Live WebSocket
         1: IO error: failed to lookup address information: Try again
     ```
   - В скрипте `S99mini_assistant` отсутствовал supervisor loop (перезапуск при сбое), поэтому процесс остался в статусе `NOT_RUNNING`.
2. **Почему индикатор постоянно горел голубым:**
   - При аппаратном старте контроллер питания и ядро выставляют светодиод `sn3236` в базовый аппаратный цвет (голубой).
   - Поскольку `mini-assistant` упал на 14-й секунде, управление светодиодом не передавалось никакому процессу.
3. **Подтверждение дефекта P1 (ложный barge-in / самоэхо):**
   - При тестовом ручном запуске `mini-assistant` успешно связался с Home Assistant (`http://192.168.1.113:8123`) и Gemini Live API.
   - Во время первого голосового ответа звук из динамика уловили микрофоны (RMS 56.9 > barge-in порога 40.0).
   - Ложный barge-in вызвал `playback.interrupt()`, увеличил `playback epoch` до 1, но не синхронизировал `client epoch`.
   - Сгенерированный ответ по погоде в Батуми (`get_weather`) был отброшен хелпером как «stale audio chunk from epoch 0 resp 2 (active epoch: 1)».

---

## 5. Вывод и готовность к следующим этапам

- Гейты **G0**, **G1** и **G2** полностью пройдены и задокументированы.
- Устройство находится в стабильном управляемом состоянии, готово к выполнению Этапа 3 и Этапа 6 плана:
  1. Исправление дефекта P1 (единый cancellation lifecycle, фильтрация самоэха / калибровка barge-in порога).
  2. Добавление ожидания сетевой готовности (DNS wait) и supervisor loop в автозапуск `mini-assistant`.
  3. Инициализация и гашение/управление светодиодом `sn3236` через I2C.
