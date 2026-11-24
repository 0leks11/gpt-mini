#!/usr/bin/env python3
"""
scripts/device/run_phase1_loopback_probe.py
Phase 1: Hardware Loopback Verification and Delay Calibration for GPT Mini.

Simultaneously streams a synthetic calibration chirp to GPT Mini's DAC (mini_pcm_sink)
and captures 8-channel S32_LE audio from ALSA hw:0,2 (mini_pcm_source).
Analyzes cross-correlation R_xy(tau) to verify:
  1. Channels 6 & 7 contain loopback reference audio.
  2. Measures exact bulk delay tau_bulk between playback and microphone capture.
  3. Evaluates correlation coefficient rho and relative signal levels.
"""

import math
import os
import struct
import subprocess
import sys
import time
from typing import List, Tuple

SSH_HOST = "10.77.0.111"
SSH_PORT = 2222
SSH_USER = "root"
SSH_BASE_CMD = [
    "ssh",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=4",
    "-p", str(SSH_PORT),
    f"{SSH_USER}@{SSH_HOST}"
]

def check_connectivity() -> bool:
    try:
        res = subprocess.run(
            SSH_BASE_CMD + ["uptime"],
            capture_output=True,
            timeout=5
        )
        return res.returncode == 0
    except Exception:
        return False

def generate_chirp_pcm(
    sample_rate: int = 48000,
    duration_sec: float = 1.5,
    f_start: float = 200.0,
    f_end: float = 3800.0,
    peak_amplitude: int = 12000 # -8.7 dBFS safe level
) -> bytearray:
    """Generates stereo 16-bit LE PCM log-frequency chirp."""
    num_samples = int(sample_rate * duration_sec)
    pcm = bytearray()

    # Pre-padding silence (0.2s)
    silence_pre = int(sample_rate * 0.2)
    for _ in range(silence_pre):
        pcm.extend(struct.pack('<hh', 0, 0))

    for i in range(num_samples):
        t = i / sample_rate
        # Logarithmic sweep
        k = (f_end / f_start) ** (t / duration_sec)
        instant_phase = 2.0 * math.pi * f_start * ((k - 1.0) / math.log(f_end / f_start)) * duration_sec
        val_sin = math.sin(instant_phase)

        # Tukey-like window (10% fade-in, 10% fade-out)
        fade_samples = int(num_samples * 0.1)
        if i < fade_samples:
            env = 0.5 * (1.0 - math.cos(math.pi * i / fade_samples))
        elif i > num_samples - fade_samples:
            env = 0.5 * (1.0 - math.cos(math.pi * (num_samples - i) / fade_samples))
        else:
            env = 1.0

        sample_val = int(peak_amplitude * env * val_sin)
        sample_val = max(-32768, min(32767, sample_val))
        pcm.extend(struct.pack('<hh', sample_val, sample_val))

    # Post-padding silence (0.5s)
    silence_post = int(sample_rate * 0.5)
    for _ in range(silence_post):
        pcm.extend(struct.pack('<hh', 0, 0))

    return pcm

def build_mpcm_stream(raw_pcm: bytearray, sample_rate: int = 48000) -> bytearray:
    """Wraps raw stereo PCM into MPCM protocol stream for mini_pcm_sink."""
    preamble = b'MPCM' + struct.pack('<IIHH', 1, sample_rate, 2, 16)
    stream = bytearray(preamble)

    chunk_size = 4096
    for i in range(0, len(raw_pcm), chunk_size):
        chunk = raw_pcm[i:i + chunk_size]
        stream.extend(struct.pack('<II', 1, len(chunk)))
        stream.extend(chunk)

    stream.extend(struct.pack('<II', 2, 0)) # EOF record
    return stream

def parse_8ch_s32_le(raw_bytes: bytes) -> List[List[float]]:
    num_frames = len(raw_bytes) // 32
    channels = [[] for _ in range(8)]
    fmt = f"<{num_frames * 8}i"
    samples = struct.unpack(fmt, raw_bytes[:num_frames * 32])
    norm = 1.0 / 2147483648.0
    for i in range(num_frames):
        base = i * 8
        for ch in range(8):
            channels[ch].append(samples[base + ch] * norm)
    return channels

def compute_rms(signal: List[float]) -> float:
    if not signal:
        return 0.0
    sum_sq = sum(x * x for x in signal)
    return math.sqrt(sum_sq / len(signal))

def compute_cross_correlation(x: List[float], y: List[float], max_lag: int) -> Tuple[int, float]:
    n = min(len(x), len(y))
    if n <= max_lag:
        return 0, 0.0
    rms_x = compute_rms(x)
    rms_y = compute_rms(y)
    if rms_x < 1e-6 or rms_y < 1e-6:
        return 0, 0.0
    denom = rms_x * rms_y * (n - max_lag)
    best_lag = 0
    best_corr = -1.0
    for lag in range(max_lag):
        dot = sum(x[t] * y[t + lag] for t in range(n - max_lag))
        corr = dot / denom
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return best_lag, best_corr

def main():
    print("=" * 65)
    print("  GPT Mini: Фаза 1 — Аппаратная верификация loopback и задержки tau")
    print("=" * 65)

    print(f"[*] Проверка сетевого доступа к GPT Mini ({SSH_HOST}:{SSH_PORT})...")
    if not check_connectivity():
        print(f"[-] Ошибка: GPT Mini ({SSH_HOST}) недоступен по SSH.")
        print("    Убедитесь, что питание колонки подключено, и она загрузилась.")
        sys.exit(1)

    print("[+] GPT Mini на связи. Готовим калибровочный акустический свип (200-3800 Гц)...")
    chirp_pcm = generate_chirp_pcm()
    mpcm_stream = build_mpcm_stream(chirp_pcm)
    chirp_duration = len(chirp_pcm) / (48000 * 4)
    capture_duration = int(math.ceil(chirp_duration + 0.5))

    print(f"[*] Синхронный запуск: воспроизведение {chirp_duration:.2f}с, захват {capture_duration}с...")

    # Start capture process on device piping raw stdout
    capture_cmd = SSH_BASE_CMD + [
        f"LD_LIBRARY_PATH=/system/vendor/quasar/libs /data/opt/mini-assistant/mini_pcm_source -D hw:0,2 -d {capture_duration}"
    ]

    # Start playback process on device reading stdin
    playback_cmd = SSH_BASE_CMD + [
        "LD_LIBRARY_PATH=/system/vendor/quasar/libs /data/opt/mini-assistant/mini_pcm_sink"
    ]

    # 1. Spawn capture first so it's ready before sound starts
    capture_proc = subprocess.Popen(
        capture_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Small delay (50ms) to ensure capture DMA has started
    time.sleep(0.05)

    # 2. Spawn playback and pipe MPCM stream
    playback_proc = subprocess.Popen(
        playback_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    playback_out, playback_err = playback_proc.communicate(input=mpcm_stream)

    # 3. Wait for capture to finish
    capture_out, capture_err = capture_proc.communicate()

    if len(capture_out) < 32 * 48000:
        print(f"[-] Ошибка захвата: получено всего {len(capture_out)} байт.")
        print(f"    stderr capture: {capture_err.decode('utf-8', errors='ignore')}")
        sys.exit(1)

    frames_count = len(capture_out) // 32
    print(f"[+] Захвачено {len(capture_out)} байт ({frames_count} фреймов, {frames_count / 48000.0:.2f} с)")

    channels = parse_8ch_s32_le(capture_out)

    print("\n--- Уровни каналов захвата ALSA hw:0,2 (RMS / dBFS) ---")
    for ch in range(8):
        rms = compute_rms(channels[ch])
        dbfs = 20.0 * math.log10(rms) if rms > 1e-9 else -120.0
        role = "Микрофон" if ch < 4 else ("Служебный" if ch < 6 else "Опорный Loopback")
        print(f"  Канал {ch} [{role:16s}]: RMS = {rms:.6f} ({dbfs:.1f} dBFS)")

    # Correlation analysis
    max_search_lag = int(0.120 * 48000) # search up to 120 ms
    print(f"\n--- Анализ взаимной корреляции R_xy(tau) (Окно поиска: 120 мс) ---")

    results = {}
    for ref_ch in [6, 7]:
        print(f"\n[Опорный сигнал: Канал {ref_ch}]")
        for mic_ch in range(4):
            lag, rho = compute_cross_correlation(channels[ref_ch], channels[mic_ch], max_search_lag)
            lag_ms = (lag / 48000.0) * 1000.0
            lag_16k = int(round(lag * 16000.0 / 48000.0))
            print(f"  Ref Ch{ref_ch} -> Mic Ch{mic_ch}: Задержка = {lag} сэмплов ({lag_ms:.2f} мс, {lag_16k} сэмплов @ 16кГц), Корреляция rho = {rho:.4f}")
            results[(ref_ch, mic_ch)] = (lag, lag_ms, lag_16k, rho)

    # Quality Gate 1 Check
    best_rho = max(r[3] for r in results.values())
    avg_rho_ch6 = sum(results[(6, m)][3] for m in range(4)) / 4.0
    avg_lag_ch6 = sum(results[(6, m)][0] for m in range(4)) / 4.0
    avg_lag_ms = (avg_lag_ch6 / 48000.0) * 1000.0
    avg_lag_16k = int(round(avg_lag_ch6 * 16000.0 / 48000.0))

    print("\n" + "=" * 65)
    print("  ИТОГ ФАЗЫ 1 (Quality Gate 1):")
    print(f"  - Максимальный коэффициент корреляции: rho = {best_rho:.4f}")
    print(f"  - Средняя аппаратная задержка tau_bulk: {avg_lag_ch6:.1f} сэмплов @ 48кГц ({avg_lag_ms:.2f} мс / {avg_lag_16k} сэмплов @ 16кГц)")

    if best_rho >= 0.70:
        print("  - Статус: [УСПЕХ] Аппаратный loopback подтверждён!")
        print("    Каналы 6 и 7 точно содержат цифровой референс воспроизведения.")
        print(f"    Рекомендуемая задержка для кольцевого буфера AEC: {avg_lag_16k} сэмплов @ 16кГц.")
    else:
        print("  - Статус: [ВНИМАНИЕ] Корреляция ниже порога (rho < 0.70).")
        print("    Проверьте, включен ли усилитель (amp_table=1) и не замьючен ли звук.")
    print("=" * 65)

if __name__ == "__main__":
    main()
