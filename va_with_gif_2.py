#!/usr/bin/env python3

import warnings
warnings.filterwarnings("ignore")

import sounddevice as sd
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
from PIL import Image, ImageTk, ImageSequence
import logging
import datetime
import re

# ================================
# CONFIG
# ================================
MIC_INDEX = 1
SAMPLE_RATE = 48000
RECORD_SECONDS = 7

# STATE values used by background threads: "IDLE", "RECORDING", "SPEAKING"
STATE = "IDLE"
reply = ""

ELEVEN_API_KEY = "sk_527b4e2851fb5e97621d473c099f9f3da5eb062abb18b381"
STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

logging.basicConfig(level=logging.ERROR)

# ================================
# GUI CLASS
# ================================
class GifPlayer(tk.Tk):
    def __init__(self, gifs):
        super().__init__()

        self.title("Aarya VoiceBot")
        self.configure(bg="black")
        # fullscreen; comment out if you want windowed mode while testing
        self.attributes("-fullscreen", True)
        self.bind("<q>", self.exit_app)
        self.bind("<Q>", self.exit_app)

        # screen size (use updated values after window appears)
        self.update_idletasks()
        w, h = self.winfo_screenwidth(), self.winfo_screenheight()

        self.canvas = tk.Label(self, bg="black")
        self.canvas.pack(fill="both", expand=True)

        # store frames and delays
        self.frames = {}   # key -> list of PhotoImage
        self.delays = {}   # key -> list of ints (ms)

        # load and pre-process GIF frames once
        for key, path in gifs.items():
            try:
                img = Image.open(path)
            except Exception as e:
                logging.error(f"Failed loading GIF {path}: {e}")
                self.frames[key] = []
                self.delays[key] = []
                continue

            fl, dl = [], []
            for frame in ImageSequence.Iterator(img):
                # convert once and resize once (costly but done only during init)
                frame = frame.convert("RGB").resize((w, h), Image.BILINEAR)
                fl.append(ImageTk.PhotoImage(frame))
                # ensure a sensible minimum duration
                dl.append(max(40, int(frame.info.get("duration", 40))))
            if not fl:
                # fallback: if GIF empty or single-frame, create a tiny empty image
                blank = Image.new("RGB", (w, h), "black")
                fl = [ImageTk.PhotoImage(blank)]
                dl = [1000]

            self.frames[key] = fl
            self.delays[key] = dl

        # animation state
        self.state_now = "idle"  # the active key among frames dict (idle/listening/speaking)
        self.index = 0

        # button (center)
        self.btn = tk.Button(
            self,
            text="Activate Aarya",
            font=("Arial", 46, "bold"),
            fg="white",
            bg="black",
            activeforeground="cyan",
            command=self.activate,
            bd=0
        )
        self._button_visible = False
        self.show_button_if_needed()

        # start a single continuous animation loop (never call animate() externally)
        self.after(0, self.animate)

    def exit_app(self, event=None):
        os._exit(0)

    def activate(self):
        global STATE
        STATE = "RECORDING"
        # hide button immediately (use .place_forget if placed)
        if self._button_visible:
            self.btn.place_forget()
            self._button_visible = False

    def show_button_if_needed(self):
        # place the button only if STATE is IDLE and it's not already placed
        if STATE == "IDLE" and not self._button_visible:
            # center button
            self.btn.place(relx=0.5, rely=0.5, anchor="center")
            self._button_visible = True
        elif STATE != "IDLE" and self._button_visible:
            self.btn.place_forget()
            self._button_visible = False

    def show(self, state_key):
        """
        Set the logical animation state. state_key should be one of the keys
        used in the gifs dict: "idle", "listening", or "speaking".
        This function only sets state; animate() runs continuously and will pick it up.
        """
        # normalize
        if not state_key:
            return
        if self.state_now == state_key:
            return
        # switch state and reset frame index
        self.state_now = state_key
        self.index = 0

    def animate(self):
        """
        Continuous animation loop. Called via after() and never re-started.
        """
        frames = self.frames.get(self.state_now, [])
        delays = self.delays.get(self.state_now, [])

        if not frames:
            # nothing to show; schedule again
            self.after(100, self.animate)
            return

        # clamp index
        self.index %= len(frames)

        # update image on canvas
        try:
            self.canvas.config(image=frames[self.index])
        except Exception as e:
            logging.error(f"Error updating frame: {e}")

        # pick delay (safe fallback)
        try:
            delay = delays[self.index]
        except Exception:
            delay = 100

        # advance index
        self.index = (self.index + 1) % len(frames)

        # schedule next frame
        self.after(delay, self.animate)

# ================================
# AUDIO RECORD
# ================================
def record_fixed_time():
    # record for RECORD_SECONDS seconds (blocking until done)
    audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE),
                   samplerate=SAMPLE_RATE,
                   channels=1,
                   dtype="int16",
                   device=MIC_INDEX)
    sd.wait()
    return audio

def write_wav(audio):
    file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    with wave.open(file.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return file.name

# ================================
# SPEECH TO TEXT
# ================================
def transcribe_audio(file, timeout=20):
    try:
        with open(file, "rb") as f:
            res = requests.post(
                STT_URL,
                headers={"xi-api-key": ELEVEN_API_KEY},
                files={"file": f},
                data={"model_id": "scribe_v1", "language_code": "en"},
                timeout=timeout
            )
        if res.status_code == 200:
            return res.json().get("text", "") or ""
        else:
            logging.error(f"STT failed: {res.status_code} {res.text}")
            return ""
    except Exception as e:
        logging.error(f"STT request error: {e}")
        return ""

# ================================
# BRAIN (unchanged logic)
# ================================
def answer_command(cmd: str) -> str:
    import datetime, time, re
    t = (cmd or "").lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    now = datetime.datetime.now()

    def contains_word(word_list):
        for w in word_list:
            if re.search(rf'\b{re.escape(w)}\b', t):
                return True
        return False

    if contains_word(["time"]):
        return now.strftime("The current time is %I:%M %p.")
    if contains_word(["date"]):
        return now.strftime("Today's date is %d %B %Y.")
    if contains_word(["day"]):
        return now.strftime("Today is %A.")
    if contains_word(["joke", "funny"]):
        return "Why did the computer go to the doctor? Because it had a bad byte!"
    if contains_word(["hello", "hi", "hey", "namaste", "good morning", "good afternoon", "good evening"]):
        return "Hi, I’m Aarya, your receptionist robot. How can I assist you today?"
    if "how are you" in t:
        return "I'm feeling fantastic, thank you for asking!"
    if contains_word(["your name", "who are you"]):
        return "My name is Aarya. I’m a humanoid receptionist robot developed by Ecruxbot."
    if contains_word(["month"]):
        return f"The current month is {time.strftime('%B')}."
    if contains_word(["year"]):
        return f"The current year is {time.strftime('%Y')}."
    if contains_word(["purpose", "what is your purpose", "tell me about yourself", "why you", "purpose of you"]):
        return "I’m designed to interact with people, share information, and assist at events, offices, and exhibitions."
    if contains_word(["who created you", "who made you", "your creator"]):
        return "I was created by Ecruxbot, an Indian robotics and AI company."
    if contains_word(["features"]):
        return "I can communicate through speech, answer visitor queries, and showcase company technologies."
    if contains_word(["can you move"]):
        return "Currently, I’m a stationary humanoid designed for receptionist roles. A mobile version is under development."
    if contains_word(["what technology do you use", "technology you use"]):
        return "I use speech recognition, text-to-speech, and AI-powered natural language understanding, all built using Python."
    if contains_word(["where are you used", "usage"]):
        return "I’m used at exhibitions, offices, educational institutes, and events as a receptionist or guide."
    if contains_word(["are you ai", "are you intelligent"]):
        return "Yes, I’m powered by Artificial Intelligence to communicate naturally with humans."
    if contains_word(["difference between you and alexa", "google assistant" , "how are you different from alexa"]):
        return "Unlike Alexa or Google Assistant, I work offline and represent Ecruxbot at real-world events."
    if contains_word(["languages you speak", "languages"]):
        return "I currently speak English, and soon I’ll also support Hindi and Marathi."
    if contains_word(["are you customizable"]):
        return "Yes, I can be customized for different industries, events, or organizations."
    if contains_word(["price", "cost"]):
        return "I’m a prototype developed for demonstrations. Future commercial versions will be available on request."
    if contains_word(["do you make industrial robots", "industrial robots"]):
        return "Yes, Ecruxbot designs and builds industrial robots, including autonomous systems and robotic arms."
    if contains_word(["robotic arm", "6 degree arm", "six degree arm"]):
        return "We’re developing a six-degree-of-freedom robotic arm for precise industrial and educational applications."
    if contains_word(["autonomous robot"]):
        return "Yes, we’re also building autonomous robots for various industrial and service applications."
    if contains_word(["custom robots", "do you make custom robots"]):
        return "Yes, we create customized robots tailored to specific industry or educational requirements."
    if contains_word(["can i buy your products", "buy your product", "buy your robots"]):
        return "Yes! You can talk to our team here or visit our website ecruxbot.in for details."
    if contains_word(["website"]):
        return "Our official website is www.ecruxbot.in."
    if contains_word(["contact", "email", "reach you"]):
        return "You can reach us anytime at ecruxbot@gmail.com."
    if contains_word(["other events", "exhibitions"]):
        return "We regularly participate in tech exhibitions and educational events across India."
    if contains_word(["tinyml"]):
        return "TinyML stands for Tiny Machine Learning — running AI models on small microcontrollers like the Raspberry Pi Pico."
    if contains_word(["ai in robotics", "artificial intelligence in robotics"]):
        return "AI gives robots the ability to see, listen, and respond intelligently to human behavior."
    if contains_word(["future of robotics"]):
        return "The future of robotics lies in human-robot collaboration powered by Artificial Intelligence."
    if contains_word(["chief minister", "cm"]):
        return "The Chief Minister of Maharashtra is Devendra Fadnavis."
    if contains_word(["prime minister", "pm"]):
        return "The Prime Minister of India is Narendra Modi."
    if contains_word(["company"]):
        return "ecruxbot is a robotics company which make educational and industrial robots"

    return "I didn’t catch that. Could you please repeat?"

# ================================
# TEXT TO SPEAK
# ================================
async def _tts(text, filename):
    tts = edge_tts.Communicate(text, voice="en-IN-NeerjaNeural")
    await tts.save(filename)

def speak_text(text):
    file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    try:
        asyncio.run(_tts(text, file))
        subprocess.run(["mpg123", "-q", file])
    except Exception as e:
        logging.error(f"TTS/playback error: {e}")
    finally:
        try:
            os.remove(file)
        except Exception:
            pass

# ================================
# THREAD WORKERS
# ================================
def record_process():
    global STATE, reply
    try:
        audio = record_fixed_time()
        path = write_wav(audio)

        text = transcribe_audio(path)
        try:
            os.remove(path)
        except Exception:
            pass

        reply = answer_command(text)

        print("\n----------------")
        print("You   :", text)
        print("Aarya :", reply)
        print("----------------\n")

    except Exception as e:
        logging.error(f"record_process error: {e}")
        reply = "Sorry, I had trouble hearing you."

    # transition to speaking (the main loop will detect and start speak thread)
    STATE = "SPEAKING"

def speak_process():
    global STATE
    try:
        speak_text(reply)
    except Exception as e:
        logging.error(f"speak_process error: {e}")
    finally:
        STATE = "IDLE"

# ================================
# MAIN LOOP
# ================================
def run_voice(gui):
    """
    Background loop (runs in a daemon thread). It watches the global STATE and:
    - updates GUI with gui.show(...) only when state actually changes
    - launches worker threads once per state transition
    """
    global STATE
    last_state = None
    worker_started_for_state = None

    # mapping from our state names to GUI keys
    state_map = {
        "IDLE": "idle",
        "RECORDING": "listening",
        "SPEAKING": "speaking"
    }

    while True:
        current_state = STATE

        # if state changed -> update GUI and reset worker marker
        if current_state != last_state:
            gui_state = state_map.get(current_state, "idle")
            gui.after(0, gui.show, gui_state)
            # update button placement immediately (safe)
            gui.after(0, gui.show_button_if_needed)
            worker_started_for_state = None
            last_state = current_state

        # handle starting worker threads only once per transition
        if current_state == "RECORDING" and worker_started_for_state != "RECORDING":
            threading.Thread(target=record_process, daemon=True).start()
            worker_started_for_state = "RECORDING"

        elif current_state == "SPEAKING" and worker_started_for_state != "SPEAKING":
            threading.Thread(target=speak_process, daemon=True).start()
            worker_started_for_state = "SPEAKING"

        # small sleep to reduce CPU use (longer is fine; GUI updates use after())
        time.sleep(0.12)

# ================================
# START
# ================================
if __name__ == "__main__":
    gifs = {
        "idle": "idle_black.gif",
        "listening": "thinking.gif",
        "speaking": "speaking.gif"
    }

    app = GifPlayer(gifs)
    # start background daemon thread to manage state/workers
    threading.Thread(target=run_voice, args=(app,), daemon=True).start()
    app.mainloop()

