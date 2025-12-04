#!/usr/bin/env python3
"""
pi_voice_gui.py

Raspberry Pi client:
 - Shows GIFs for idle / listening / thinking / speaking
 - Records fixed-time audio from microphone
 - POSTs recorded wav to SERVER_URL
 - Receives JSON {text, reply, audio_b64}
 - Plays audio reply and shows speaking animation

Requirements (on Pi):
  sudo apt-get install mpg123
  pip install requests sounddevice numpy pillow

Usage:
  SERVER_URL can be set via environment variable, e.g.:
    export SERVER_URL="http://192.168.31.227:5050/voice"
  Then run:
    python3 pi_voice_gui.py
"""

import os
import threading
import tempfile
import wave
import base64
import time
import requests
import subprocess
import logging
from pathlib import Path
import sounddevice as sd
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk, ImageSequence
import shutil  # FIXED

# ---------------------- CONFIG ----------------------
SERVER_URL = os.environ.get("SERVER_URL", "http://192.168.31.227:5050/voice")
SAMPLE_RATE = int(os.environ.get("SAMPLE_RATE", "16000"))
RECORD_SECONDS = int(os.environ.get("RECORD_SECONDS", "5"))
MIC_DEVICE_INDEX = os.environ.get("MIC_INDEX", None)
PLAY_COMMAND = os.environ.get("PLAY_CMD", "mpg123 -q")
TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))

# GIF paths
GIF_IDLE = "idle_black.gif"
GIF_LISTEN = "listening.gif"
GIF_THINK = "thinking.gif"
GIF_SPEAK = "speaking.gif"
# ----------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


# ---------------------- GIF PLAYER ----------------------
class GifPlayer(tk.Tk):
    def __init__(self, gif_map):
        super().__init__()
        self.title("Aarya Voice Client")
        self.configure(bg="#000")
        self.geometry("960x540")
        self.resizable(False, False)

        self.frame = tk.Frame(self, bg="#000")
        self.frame.place(relx=0.5, rely=0.48, anchor="center", width=900, height=420)

        self.label = tk.Label(self.frame, bg="#000")
        self.label.pack(fill="both", expand=True)

        self.frames = {}
        self.delays = {}
        for key, path in gif_map.items():
            if not os.path.exists(path):
                logging.warning("GIF not found: %s", path)
                img = Image.new("RGBA", (900,420), (0,0,0,255))
                self.frames[key] = [ImageTk.PhotoImage(img)]
                self.delays[key] = [100]
                continue
            img = Image.open(path)
            fl, dl = [], []
            for frame in ImageSequence.Iterator(img):
                f = frame.convert("RGBA").resize((900,420), Image.Resampling.LANCZOS)
                fl.append(ImageTk.PhotoImage(f))
                dl.append(frame.info.get("duration", 80))
            self.frames[key] = fl
            self.delays[key] = dl

        self.current_state = None
        self.frame_index = 0
        self._animating = False

        self.btn = tk.Button(self, text="Activate Aarya",
                             font=("Helvetica", 28, "bold"),
                             bg="#111", fg="#fff", bd=0, padx=20, pady=10,
                             command=self.on_button_press)
        self.btn.place(relx=0.5, rely=0.9, anchor="center")

        self.info = tk.Label(self, text="Server: {}\nPress button to record {}s".format(SERVER_URL, RECORD_SECONDS),
                             bg="#000", fg="#ddd", font=("Helvetica", 10), justify="center")
        self.info.place(relx=0.5, rely=0.03, anchor="n")

    def on_button_press(self):
        global STATE
        if STATE == "IDLE":
            STATE = "RECORDING"
            self.btn.place_forget()

    def show_button(self):
        if STATE == "IDLE":
            self.btn.place(relx=0.5, rely=0.9, anchor="center")

    def show(self, state):
        if state == self.current_state:
            return
        self.current_state = state
        self.frame_index = 0
        if not self._animating:
            self._animating = True
            self.after(0, self._animate_step)

    def _animate_step(self):
        if not self.current_state or self.current_state not in self.frames:
            self._animating = False
            return
        frames = self.frames[self.current_state]
        delays = self.delays[self.current_state]
        idx = self.frame_index % len(frames)
        self.label.config(image=frames[idx])
        delay = delays[idx]
        self.frame_index = (self.frame_index + 1) % len(frames)
        self.after(delay, self._animate_step)

    def update_info(self, text):
        self.info.config(text=text)

# ---------------------- AUDIO HELPERS ----------------------
def get_mic_index():
    if MIC_DEVICE_INDEX is None:
        return None
    try:
        return int(MIC_DEVICE_INDEX)
    except:
        return None


def record_fixed(seconds=RECORD_SECONDS, samplerate=SAMPLE_RATE, device=None):
    try:
        audio = sd.rec(int(seconds * samplerate), samplerate=samplerate,
                       channels=1, dtype='int16', device=device)
        sd.wait()
        return audio
    except Exception as e:
        logging.error("Recording failed: %s", e)
        return None


def write_wav(audio):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    path = tmp.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return path


def play_mp3_b64(b64data):
    data = base64.b64decode(b64data)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    path = tmp.name
    with open(path, "wb") as f:
        f.write(data)
    subprocess.run(f"{PLAY_COMMAND} {path}", shell=True)
    os.remove(path)

# ---------------------- POST AUDIO ----------------------
def post_audio(wav_path):
    files = {"file": (Path(wav_path).name, open(wav_path, "rb"), "audio/wav")}
    try:
        r = requests.post(SERVER_URL, files=files, timeout=TIMEOUT)
    except Exception as e:
        return {"error": str(e)}

    if r.status_code != 200:
        return {"error": r.text}

    try:
        return r.json()
    except:
        return {"error": "Invalid JSON"}

# ---------------------- MAIN LOOP ----------------------
STATE = "IDLE"


def voice_loop(gui):
    global STATE
    mic_index = get_mic_index()

    while True:
        if STATE == "IDLE":
            gui.show("idle")
            gui.show_button()
            time.sleep(0.1)
            continue

        if STATE == "RECORDING":
            gui.show("listening")
            gui.update_info("Recording...")
            audio = record_fixed(device=mic_index)
            if audio is None:
                STATE = "IDLE"
                continue
            wav_path = write_wav(audio)
            STATE = "SENDING"

        if STATE == "SENDING":
            gui.show("thinking")
            gui.update_info("Processing...")

            res = post_audio(wav_path)
            os.remove(wav_path)

            if "error" in res:
                gui.update_info("Error: " + res["error"])
                STATE = "IDLE"
                continue

            text = res.get("text", "")
            reply = res.get("reply", "")
            audio_b64 = res.get("audio_b64")

            gui.update_info(f"You said: {text}\nBot: {reply}")

            if audio_b64:
                STATE = "SPEAKING"

                gui.show("speaking")
                gui.update_info("Speaking...")

                play_mp3_b64(audio_b64)

            STATE = "IDLE"
            gui.update_info("Ready.")

        time.sleep(0.05)

# ---------------------- RUN APP ----------------------
def main():
    if shutil.which("mpg123") is None:
        logging.warning("mpg123 not installed. Install: sudo apt-get install mpg123")

    gifs = {
        "idle": GIF_IDLE,
        "listening": GIF_LISTEN,
        "thinking": GIF_THINK,
        "speaking": GIF_SPEAK,
    }

    gui = GifPlayer(gifs)
    threading.Thread(target=voice_loop, args=(gui,), daemon=True).start()
    gui.mainloop()


if __name__ == "__main__":
    main()
