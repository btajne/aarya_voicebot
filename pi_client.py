#!/usr/bin/env python3

import speech_recognition as sr
import requests

SERVER_URL = "http://10.55.40.128:5050/ask"  # change if needed

print("\n🎤 AARYA VOICEBOT READY")
print("Searching microphones...")

# FIND MICROPHONE
mics = sr.Microphone.list_microphone_names()
print("🧭 Found microphones:")
for i, m in enumerate(mics):
    print(f"  {i}: {m}")

# AUTO SELECT FIRST USB MIC
mic_index = None
for i, name in enumerate(mics):
    if "USB" in name or "Microphone" in name or "Audio" in name:
        mic_index = i
        break

if mic_index is None:
    mic_index = 0  # fallback

print(f"\n🎤 Using microphone index: {mic_index}")

r = sr.Recognizer()

print("Press ENTER and speak...")

while True:
    input("\n➤ Press ENTER to start speaking...")

    try:
        with sr.Microphone(device_index=mic_index) as source:
            r.adjust_for_ambient_noise(source)
            print("🎤 Recording... speak now...")

            audio = r.listen(source, timeout=5, phrase_time_limit=6)

            print("📡 Processing speech...")
    except Exception as e:
        print(f"❌ Mic/Timeout error: {e}")
        continue

    # SPEECH TO TEXT
    try:
        user_text = r.recognize_google(audio)
        print("🗣️ You said:", user_text)
    except:
        print("❌ Speech not recognized")
        continue

    # SEND TO SERVER
    try:
        resp = requests.post(SERVER_URL, json={"user": user_text})
        reply = resp.json().get("reply", None)

        if reply:
            print("🤖 PC replied:", reply)
        else:
            print("❌ No reply from server")

    except Exception as e:
        print("❌ Server connection error:", e)

