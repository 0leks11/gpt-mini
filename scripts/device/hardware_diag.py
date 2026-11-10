#!/usr/bin/env python3
"""GPT Mini Complete Hardware Diagnostic Suite.
Tests: Speaker, Microphones, Button, LED ring, ToF proximity sensor, Bluetooth, Wi-Fi.
"""
import math
import struct
import subprocess
import sys
import time

SSH_CMD = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-p", "2222", "root@10.77.0.111"]

def run_remote(cmd: str) -> tuple[int, str]:
    res = subprocess.run(SSH_CMD + [cmd], capture_output=True, text=True)
    return res.returncode, res.stdout.strip() + res.stderr.strip()

def test_speaker():
    print("[1/6] Тестирование динамика (DAC pcm5122 -> Quasar ALSA hw:0,0)...")
    # Generate 0.5s of dual-tone chime (523Hz + 659Hz)
    rate = 48000
    duration = 0.5
    num_samples = int(rate * duration)
    pcm_data = bytearray()
    for i in range(num_samples):
        t = i / rate
        env = min(1.0, i / 2400.0) * min(1.0, (num_samples - i) / 2400.0)
        s1 = math.sin(2 * math.pi * 523.25 * t)
        s2 = math.sin(2 * math.pi * 659.25 * t)
        val = int(5000 * env * (s1 + s2) * 0.5)
        val = max(-16000, min(16000, val))
        pcm_data.extend(struct.pack('<hh', val, val))

    preamble = b'MPCM' + struct.pack('<IIHH', 1, 48000, 2, 16)
    stream = bytearray(preamble)
    for i in range(0, len(pcm_data), 4096):
        chunk = pcm_data[i:i+4096]
        stream.extend(struct.pack('<II', 1, len(chunk)))
        stream.extend(chunk)
    stream.extend(struct.pack('<II', 2, 0)) # EOF

    proc = subprocess.Popen(
        SSH_CMD + ["LD_LIBRARY_PATH=/system/vendor/quasar/libs /data/opt/mini-assistant/mini_pcm_sink"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate(input=stream)
    output = stdout.decode('utf-8', errors='ignore') + stderr.decode('utf-8', errors='ignore')

    if proc.returncode == 0 and "completed" in output:
        print("  -> Динамик: ОК (звуковой тестовый аккорд успешно воспроизведён)")
        return True, "OK (воспроизведение успешно)"
    else:
        print(f"  -> Динамик: ОШИБКА ({output})")
        return False, f"FAIL: {output}"

def test_led():
    print("[2/6] Тестирование светодиодного кольца (sn3236 @ I2C 0x3c)...")
    code, out = run_remote("i2cset -y 0 0x3c 0x00 0x01 && sleep 1 && i2cset -y 0 0x3c 0x00 0x00")
    if code == 0:
        print("  -> Светодиоды: ОК (сигнал включения/выключения передан без ошибок шины)")
        return True, "OK (I2C шина ответила успешно)"
    else:
        print(f"  -> Светодиоды: ОШИБКА I2C ({out})")
        return False, f"FAIL: {out}"

def test_tof_sensor():
    print("[3/6] Тестирование ToF лазерного датчика расстояния (VL53L0 @ I2C 0x29)...")
    code, out = run_remote("test -e /sys/bus/i2c/devices/1-0029/driver && ps w | grep STM-VL53L0 | grep -v grep")
    if code == 0 and "STM-VL53L0" in out:
        print("  -> Датчик расстояния (ToF): ОК (драйвер ядра stmvl53l0 и опросный поток активны)")
        return True, "OK (драйвер и поток опроса активны)"
    else:
        print(f"  -> Датчик расстояния: ПРЕДУПРЕЖДЕНИЕ ({out})")
        return False, f"WARN: {out}"

def test_button():
    print("[4/6] Проверка устройства кнопки Mute (/dev/input/event2)...")
    code, out = run_remote("test -c /dev/input/event2 && grep -A 4 'adc_keypad' /proc/bus/input/devices")
    if code == 0 and "adc_keypad" in out:
        print("  -> Кнопка: ОК (устройство ввода adc_keypad зарегистрировано в ядре)")
        return True, "OK (драйвер adc_keypad активен)"
    else:
        print(f"  -> Кнопка: ОШИБКА ({out})")
        return False, f"FAIL: {out}"

def test_bluetooth_and_wifi():
    print("[5/6] Тестирование беспроводных интерфейсов (BCM43430 Wi-Fi & BLE)...")
    code_w, out_w = run_remote("ifconfig wlan0")
    code_b, out_b = run_remote("cat /data/opt/mini-assistant/bcm-attach.log 2>/dev/null | tail -n 2")
    wifi_ok = (code_w == 0 and "10.77.0.111" in out_w)
    bt_ok = (code_b == 0 and "UP=true" in out_b)
    if wifi_ok and bt_ok:
        print(f"  -> Wi-Fi и Bluetooth: ОК (wlan0 в сети {out_w.split('inet addr:')[1].split()[0]}, hci0 UART UP)")
        return True, "OK (wlan0 + hci0 активны)"
    else:
        print(f"  -> Беспроводные интерфейсы: ОШИБКА (WiFi: {out_w}, BT: {out_b})")
        return False, f"WiFi: {out_w}, BT: {out_b}"

def test_microphones():
    print("[6/6] Тестирование микрофонного массива (8ch S32_LE hw:0,2)...")
    code, out = run_remote("cat /proc/asound/card0/pcm2c/sub0/status | grep state; tail -n 5 /data/opt/mini-assistant/assistant.log | grep peak_rms")
    if "RUNNING" in out:
        print(f"  -> Микрофоны: ОК (аппаратный поток активен, {out.strip()})")
        return True, f"OK: {out.strip()}"
    else:
        print(f"  -> Микрофоны: {out}")
        return False, out

def main():
    print("=" * 60)
    print("  GPT Mini: Комплексный аппаратный тест компонентов")
    print("=" * 60)
    results = {}
    results["Динамик"] = test_speaker()
    results["LED-кольцо"] = test_led()
    results["Датчик расстояния ToF"] = test_tof_sensor()
    results["Кнопка Mute"] = test_button()
    results["Wi-Fi и Bluetooth"] = test_bluetooth_and_wifi()
    results["Микрофоны ALSA"] = test_microphones()
    print("=" * 60)
    all_ok = all(r[0] for r in results.values())
    print(f"ИТОГ: {'ВСЕ КОМПОНЕНТЫ ИСПРАВНЫ' if all_ok else 'ОБНАРУЖЕНЫ ЗАМЕЧАНИЯ'}")
    print("=" * 60)

if __name__ == "__main__":
    main()
