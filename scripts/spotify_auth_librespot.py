#!/usr/bin/env python3
import os
import subprocess
import sys
import time

SSH_KEY = "/Users/oleksii/Documents/gpt-mini/.private/alice-mini/usb-root-2026-10-25/ssh-ram-v2/client_ed25519"
MINI_HOST = "10.77.0.111"
MINI_PORT = "2222"
JUMP_HOST = "pi@10.77.0.130"
LOCAL_CACHE = "/tmp/spotify_auth_cache"

def scp_to_mini(local_file, remote_file):
    cmd = [
        "scp", "-O", "-J", JUMP_HOST, "-i", SSH_KEY, "-P", MINI_PORT,
        "-o", "StrictHostKeyChecking=no",
        local_file, f"root@{MINI_HOST}:{remote_file}"
    ]
    subprocess.run(cmd, check=True)

def main():
    os.makedirs(LOCAL_CACHE, exist_ok=True)
    for f in os.listdir(LOCAL_CACHE):
        os.remove(os.path.join(LOCAL_CACHE, f))

    print("1. Launching local librespot OAuth server on Mac...")
    cmd = [
        "/opt/homebrew/bin/librespot",
        "--enable-oauth",
        "--oauth-port", "8081",
        "--system-cache", LOCAL_CACHE,
        "--name", "GPT Mini Auth",
        "-v"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    auth_opened = False
    success = False

    for line in iter(proc.stdout.readline, ''):
        print(line, end='', flush=True)
        if "Browse to: " in line and not auth_opened:
            auth_url = line.split("Browse to: ")[1].strip()
            print("\n" + "="*80)
            print("SPOTIFY AUTHENTICATION URL:")
            print(auth_url)
            print("="*80 + "\n")
            print("Opening browser for authorization...")
            try:
                subprocess.run(["open", auth_url])
            except Exception as e:
                print(f"Could not open browser automatically: {e}")
            auth_opened = True

        if any(marker in line for marker in [
            "Authenticated as",
            "Setting up new Spirc",
            "AP connection established",
            "logged in",
            "Credentials cached",
        ]):
            print("\n" + "="*80)
            print(">>> SPOTIFY CONNECT AUTHENTICATION SUCCESSFUL! <<<")
            print("="*80 + "\n")
            success = True
            time.sleep(2)
            break

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()

    cred_file = os.path.join(LOCAL_CACHE, "credentials.json")
    if os.path.exists(cred_file):
        print(f"Found {cred_file}! Copying to GPT Mini...")
        # Ensure remote directory exists
        ssh_cmd = [
            "ssh", "-J", JUMP_HOST, "-i", SSH_KEY, "-p", MINI_PORT,
            "-o", "StrictHostKeyChecking=no",
            f"root@{MINI_HOST}", "mkdir -p /data/opt/mini-assistant/spotify_cache"
        ]
        subprocess.run(ssh_cmd, check=True)
        scp_to_mini(cred_file, "/data/opt/mini-assistant/spotify_cache/credentials.json")
        print("Successfully uploaded credentials.json to GPT Mini!")
    else:
        print("ERROR: credentials.json was not generated.")
        sys.exit(1)

if __name__ == "__main__":
    main()
