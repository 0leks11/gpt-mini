# Аппаратная карта и периферия GPT Mini (Yandex Station Mini A113X)

- **Дата аудита**: 2026-11-10
- **Платформа**: Amlogic A113X (Meson AXG), Cortex-A53, userspace ELF32 ARM/armhf, 236 MiB RAM
- **Статус верификации**: Подтверждено на физическом устройстве

## Физические шины и контроллеры

| Интерфейс | Адрес / Устройство | Назначение | Проверка / Драйвер |
|---|---|---|---|
| **I2C-0** | `0x3c` | Контроллер светодиодной подсветки SN3236 (36 каналов) | `i2cset -y 0 0x3c` (управление 12 RGB диодами кольца) |
| **I2C-1** | `0x29` | Лазерный ToF-датчик расстояния STMicroelectronics VL53L0X | Ядерный драйвер `stmvl53l0`, опрос `/dev/input/event1` / I2C |
| **Input Event** | `/dev/input/event2` | Аппаратная кнопка Mute (`adc_keypad`) | Опрос нажатий, переключение микрофона / сброс |
| **UART** | `/dev/ttyS1` | Bluetooth контроллер Broadcom BCM43430 | `bcm-attach /dev/ttyS1 bcm43438.hcd 115200 1500000 flow` (`hci0`) |
| **ALSA DAC** | `hw:0,0` | Quasar DAC PCM вывод звука (музыка, TTS, сигналы) | 16-bit stereo 48 kHz (через Soloist / `audio::playback`) |
| **ALSA MIC** | `hw:0,2` | 4-микрофонная решетка (8ch S32_LE 48 kHz) | `mini_pcm_source` -> raw PCM -> Rustpotter (Ch0 mono 16 kHz) |
| **Wi-Fi** | `wlan0` | Broadcom Wi-Fi подключен к сети `ffff` | IP `10.77.0.111`, шлюз `10.77.0.1` (MikroTik 1) |

## GPIO и сервисные пины

| Линия / GPIO | Где найден в коде / схеме | Статус / Проверка безопасности |
|---|---|---|
| GPIO 0 | `.private/.../Telegram_Control_Bot/bot.py` | Внутренний тестовый триггер |
| Strapping Pins | SoC A113X | Не модифицировать, сохранены штатные подтяжки bootloader |
| I2C Pullups | 3.3V шины I2C-0 и I2C-1 | Штатные подтяжки на плате, прямое подключение без коллизий |
