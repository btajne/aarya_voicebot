#!/usr/bin/env python3

import warnings
warnings.filterwarnings("ignore")

import sounddevice as sd
import numpy as np
import requests
import wave
import tempfile
import os
import time
import asyncio
import subprocess
import edge_tts
import threading
import tkinter as tk
from PIL import Image, ImageTk
import logging
import datetime
import re

# ===========================================
# SET YOUR USB MICROPHONE
# ===========================================
MIC_DEVICE = "hw:2,0"
sd.default.device = (MIC_DEVICE, None)

# CONFIG
ELEVEN_API_KEY = "sk_527b4e2851fb5e97621d473c099f9f3da5eb062abb18b381"  
STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

SAMPLE_RATE = 48000
RECORD_SECONDS = 7
WINDOW_SIZE = (1024, 600)
logging.basicConfig(level=logging.ERROR)

STATE = "IDLE"

# =============================================================
# GUI CLASS
# =============================================================
class GifPlayer(tk.Tk):
    def __init__(self, gifs):
        super().__init__()
        self.title("Aarya VoiceBot Assistant")
        self.configure(bg="#000")
        self.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}")
        self.resizable(False, False)

        self.frame = tk.Frame(self, bg="#000")
        self.frame.place(relx=0.5, rely=0.47, anchor="center", width=900, height=480)

        self.gifs = {state: Image.open(path) for state, path in gifs.items()}
        self.current_state = None

        self.label = tk.Label(self.frame, bg="#000")
        self.label.pack(fill="both", expand=True)

        # Transparent Button
        self.btn = tk.Button(
            self,
            text="Activate Aarya",
            font=("Helvetica", 40, "bold"),
            command=self.on_button_press,
            bg="#000",
            activebackground="#000",
            fg="white",
            bd=0,
            relief="flat",
            highlightthickness=0,
        )

        self.show_button()

    def hide_button(self):
        self.btn.place_forget()

    def show_button(self):
        self.btn.place(relx=0.5, rely=0.5, anchor="center")

    def on_button_press(self):
        global STATE
        if STATE == "IDLE":
            self.hide_button()
            STATE = "RECORDING"

    def show(self, state):
        if self.current_state != state:
            self.current_state = state
            self._animate(state, 0)

    def _animate(self, state, frame):
        if self.current_state != state:
            return

        gif = self.gifs[state]
        try:
            gif.lseek(frame)
            img = ImageTk.PhotoImage(
                gif.copy().convert("RGBA").resize((900, 480), Image.Resampling.LANCZOS)
            )
            self.label.config(image=img)
            self.label.image = img

            delay = gif.info.get("duration", 50)
            self.after(delay, self._animate, state, frame + 1)

        except EOFError:
            self._animate(state, 0)


# =============================================================
# RECORD AUDIO FOR EXACT 7 SECONDS
# =============================================================
def record_fixed_time():
    print("🎤 Recording for 7 seconds...")

    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=MIC_DEVICE,
    )

    sd.wait()
    return audio


# =============================================================
# SAVE WAV FILE
# =============================================================
def write_wav(audio):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")

    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

    return tmp.name


# =============================================================
# SPEECH-TO-TEXT
# =============================================================
def transcribe_audio(path):
    headers = {"xi-api-key": ELEVEN_API_KEY}
    data = {"model_id": "scribe_v1", "language_code": "en"}

    try:
        with open(path, "rb") as f:
            r = requests.post(STT_URL, headers=headers, files={"file": f}, data=data)

        if r.status_code == 200:
            return r.json().get("text", "")
    except:
        return "(STT error)"

    return "(failed)"


# =============================================================
# COMMAND LOGIC
# =============================================================
def answer_command(cmd: str) -> str:

    t = cmd.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    now = datetime.datetime.now()

    def contains(wlist):
        for w in wlist:
            if re.search(rf'\b{re.escape(w)}\b', t):
                return True
        return False

    if contains(["time"]):
        return now.strftime("The time is %I:%M %p")

    if contains(["date"]):
        return now.strftime("Today's date is %d %B %Y")

    if contains(["day"]):
        return now.strftime("Today is %A")

    if contains(["hello", "hi", "hey", "namaste"]):
        return "Hello, I am Aarya. How can I help you?"

    if contains(["your name", "who are you"]):
        return "My name is Aarya, a humanoid receptionist robot developed by Ecruxbot."

    if contains(["who created you"]):
        return "I was created by Ecruxbot, an Indian robotics company."

    if contains(["place", "location"]):
        return "We are currently at Jalgaon Sports Complex."

    if contains(["company"]):
        return "Ecruxbot designs industrial and educational robots in India."

    return f"I heard: {cmd}" if cmd else "Please say again."


# =============================================================
# TEXT TO SPEECH
# =============================================================
async def _tts_save(text, path):
    tts = edge_tts.Communicate(text, voice="en-US-AriaNeural")
    await tts.save(path)


def speak_text(text):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    asyncio.run(_tts_save(text, tmp))
    subprocess.run(["mpg123", "-q", tmp])
    os.remove(tmp)


# =============================================================
# MAIN LOOP
# =============================================================
def run_voice_loop(gui):
    global STATE

    while True:

        if STATE == "IDLE":
            gui.show("idle")
            gui.show_button()
            time.sleep(0.1)
            continue

        if STATE == "RECORDING":
            gui.show("listening")
            gui.hide_button()

            audio = record_fixed_time()
            wav = write_wav(audio)
            text = transcribe_audio(wav)

            os.remove(wav)

            print("❓ You said:", text)

            reply = answer_command(text)
            print("💬 Aarya:", reply)

            STATE = "SPEAKING"

        if STATE == "SPEAKING":
            gui.show("speaking")
            speak_text(reply)
            STATE = "IDLE"


# =============================================================
# ENTRY POINT
# =============================================================
if __name__ == "__main__":

    gifs = {
        "idle": "idle_black.gif",
        "listening": "thinking.gif",
        "speaking": "speaking.gif",
    }

    gui = GifPlayer(gifs)
    threading.Thread(target=run_voice_loop, args=(gui,), daemon=True).start()
    gui.mainloop()

