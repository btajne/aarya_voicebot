#!/usr/bin/env python3
"""
Aarya Voice Chatbot + Animated GUI
----------------------------------
- Wake word detection ("Aarya")
- ElevenLabs STT + Edge TTS
- Tkinter GIF UI:
    💤 idle_black.gif   -> when waiting
    👂 listening.gif     -> when wake word detected
    🗣️ speaking.gif      -> while replying
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="webrtcvad")

import sounddevice as sd
import webrtcvad
import requests
import wave
import tempfile
import os
import difflib
import time
import datetime
import string
import asyncio
import subprocess
import edge_tts
import threading
import tkinter as tk
from PIL import Image, ImageTk
import logging

# ----------------------- CONFIG -----------------------
ELEVEN_API_KEY = "557ffd060eca83bf1c3db4ea8ccc1ef81ccf628caf489404cfbcc917082558da"
STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
SAMPLE_RATE = 16000   # ✅ lowered to match typical mic hardware
FRAME_DURATION_MS = 20
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)
VAD_MODE = 2
MIN_SPEECH_FRAMES = 8
MAX_SPEECH_SECONDS = 3
QUESTION_RECORD_SECONDS = 4
STT_REQUEST_TIMEOUT = 10
FUZZY_THRESHOLD = 0.78
MIC_DEVICE_INDEX = None   # ✅ auto-detect default mic
WINDOW_SIZE = (1024, 600)

VARIANTS = [
    # Core
    "arya", "aarya", "aaryaa", "aryaa", "aryaah", "aaryah", "ariya", "aria", "ariah",
    # Indian/Accent Variants
    "areeya", "areya", "ariyaa", "ariyah", "arrya", "aryuh", "aryuhh", "aryaaah",
    "aryaaa", "aryahh", "aryuhhh", "aryee", "arye", "aariya", "ahria", "ahriya",
    "aahria", "ahrya", "aar-ya", "aahr-ya", "aar-yaa", "aaryaa bhai", "aarya ji",
    "aarye", "aarye ve", "aaryaa ve", "ah ya", "are ya", "are yah", "ar ya", "r ya",
    "are you", "a rya", "a yah", "aahrya", "aahriaa", "aaryaahh", "ahriyaa"
]
logging.basicConfig(level=logging.ERROR)

STATE = "WAIT_WAKE"
vad = webrtcvad.Vad(VAD_MODE)

# -------------------- GUI (Tkinter) --------------------
class GifPlayer(tk.Tk):
    def __init__(self, gifs):
        super().__init__()
        self.title("Aarya VoiceBot")
        self.configure(bg="black")
        self.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}")
        self.resizable(False, False)
        self.bind("<Escape>", lambda e: self.destroy())

        # Load all GIFs once
        self.gifs = {state: Image.open(path) for state, path in gifs.items()}
        self.current_state = None
        self.label = tk.Label(self, bg="black")
        self.label.pack(fill="both", expand=True)

    def show(self, state):
        if self.current_state == state:
            return
        self.current_state = state
        self._animate(state, 0)

    def _animate(self, state, frame_idx):
        if self.current_state != state:
            return
        gif = self.gifs[state]
        try:
            gif.seek(frame_idx)
            # ✅ Resize to fill 1024×600
            frame = gif.copy().convert("RGBA").resize(WINDOW_SIZE, Image.Resampling.LANCZOS)
            img = ImageTk.PhotoImage(frame)
            self.label.config(image=img)
            self.label.image = img
            delay = max(20, gif.info.get("duration", 50) // 2)  # ✅ Slightly faster animation
            self.after(delay, self._animate, state, frame_idx + 1)
        except EOFError:
            self._animate(state, 0)

# -------------------- UTILITIES --------------------
def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower().translate(str.maketrans("", "", string.punctuation))
    return " ".join(s.split())

def fuzzy_match_score(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()

def is_wake_word_in_text(text: str) -> bool:
    t = normalize_text(text)
    for v in VARIANTS:
        if fuzzy_match_score(t, v) >= FUZZY_THRESHOLD:
            return True
        for word in t.split():
            if fuzzy_match_score(word, v) >= FUZZY_THRESHOLD:
                return True
    return False

def write_wav(frames, rate=SAMPLE_RATE):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))
    return tmp.name

def transcribe_audio(path: str) -> str:
    headers = {"xi-api-key": ELEVEN_API_KEY}
    data = {"model_id": "scribe_v1", "language_code": "en"}
    try:
        with open(path, "rb") as f:
            r = requests.post(STT_URL, headers=headers, files={"file": f}, data=data, timeout=STT_REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json().get("text", "").strip()
    except Exception:
        pass
    return ""

def answer_command(cmd: str) -> str:
    """
    Aarya Voice Assistant – Robust Command Answering Function
    ----------------------------------------------------------
    - Handles greetings, date/time, robotics Q&A, tech, and politics.
    - Prevents substring conflicts (like 'hi' in 'chief', 'pm' in 'computer').
    - Case-insensitive and punctuation-tolerant.
    """

    import datetime, time, re

    # --- Normalize input ---
    t = cmd.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)  # remove punctuation for clean matching
    words = t.split()
    now = datetime.datetime.now()

    # --- Helper functions ---
    def contains_word(word_list):
        """Return True if any full word or phrase appears in text."""
        for w in word_list:
            # full phrase match (not substring)
            if re.search(rf'\b{re.escape(w)}\b', t):
                return True
        return False

    # --- Basic System Responses ---
    if contains_word(["time"]):
        return now.strftime("The current time is %I:%M %p.")
    if contains_word(["date"]):
        return now.strftime("Today's date is %d %B %Y.")
    if contains_word(["day"]):
        return now.strftime("Today is %A.")
    if contains_word(["joke", "funny"]):
        return "Why did the computer go to the doctor? Because it had a bad byte!"

    # --- Greetings ---
    if contains_word(["hello", "hi", "hey", "namaste", "good morning", "good afternoon", "good evening"]):
        return "Hi, I’m Aarya, your receptionist robot. How can I assist you today?"
    if "how are you" in t:
        return "I'm feeling fantastic, thank you for asking!"
    if contains_word(["your name", "who are you"]):
        return "My name is Aarya. I’m a humanoid receptionist robot developed by Ecruxbot."

    # --- Date / Time / Place ---
    if contains_word(["month"]):
        return f"The current month is {time.strftime('%B')}."
    if contains_word(["year"]):
        return f"The current year is {time.strftime('%Y')}."
    if contains_word(["place", "where are you", "location"]):
        return "Right now, I’m at the Tech Event in Jalgaon, Maharashtra."

    # --- About Aarya ---
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
    if contains_word(["difference between you and alexa", "google assistant"]):
        return "Unlike Alexa or Google Assistant, I work offline and represent Ecruxbot at real-world events."
    if contains_word(["languages you speak", "languages"]):
        return "I currently speak English, and soon I’ll also support Hindi and Marathi."
    if contains_word(["are you customizable"]):
        return "Yes, I can be customized for different industries, events, or organizations."
    if contains_word(["are you open source"]):
        return "Some of our educational projects are open-source, while our commercial robots are proprietary."
    if contains_word(["price", "cost"]):
        return "I’m a prototype developed for demonstrations. Future commercial versions will be available on request."

    # --- Industrial Robotics ---
    if contains_word(["do you make industrial robots", "industrial robots"]):
        return "Yes, Ecruxbot designs and builds industrial robots, including autonomous systems and robotic arms."
    if contains_word(["robotic arm", "6 degree arm", "six degree arm"]):
        return "We’re developing a six-degree-of-freedom robotic arm for precise industrial and educational applications."
    if contains_word(["autonomous robot"]):
        return "Yes, we’re also building autonomous robots for various industrial and service applications."
    if contains_word(["custom robots", "do you make custom robots"]):
        return "Yes, we create customized robots tailored to specific industry or educational requirements."

    # --- Tech Event Context ---
    if contains_word(["why are you in delhi"]):
        return "We’re here at the Indian Mobile Congress in Delhi to showcase Aarya and our robotics innovations."
    if contains_word(["can i buy your products", "buy your product", "buy your robots"]):
        return "Yes! You can talk to our team here or visit our website ecruxbot.in for details."
    if contains_word(["website"]):
        return "Our official website is www.ecruxbot.in."
    if contains_word(["contact", "email", "reach you"]):
        return "You can reach us anytime at info@ecruxbot.in."
    if contains_word(["other events", "exhibitions"]):
        return "We regularly participate in tech exhibitions and educational events across India."

    # --- Tech & AI ---
    if contains_word(["tinyml"]):
        return "TinyML stands for Tiny Machine Learning — running AI models on small microcontrollers like the Raspberry Pi Pico."
    if contains_word(["ai in robotics", "artificial intelligence in robotics"]):
        return "AI gives robots the ability to see, listen, and respond intelligently to human behavior."
    if contains_word(["future of robotics"]):
        return "The future of robotics lies in human-robot collaboration powered by Artificial Intelligence."

    # --- Maharashtra / Politics ---
    if contains_word(["chief minister", "cm"]):
        return "The Chief Minister of Maharashtra is Devendra Fadnavis."
    if contains_word(["prime minister", "pm"]):
        return "The Prime Minister of India is Narendra Modi."
    if contains_word(["member of parliament", "mp", "khasdar"]):
        return "The Member of Parliament for Jalgaon is Smita Tai Wagh."
    if contains_word(["smita wagh"]):
        return "Smita Wagh is the current Member of Parliament for Jalgaon."
    if contains_word(["member of legislative assembly", "mla", "aamdar"]):
        return "The Member of the Legislative Assembly for Jalgaon is Raju Mama Bhole."
    if contains_word(["company"]):
        return "ecruxbot is a robotics company which make educational and industrial robots"

    # --- Default Fallback ---
    return f"I heard: {cmd}" if cmd else "I didn’t catch that. Could you please repeat?"




async def _tts_save(text: str, path: str):
    tts = edge_tts.Communicate(text, voice="en-US-AriaNeural")
    await tts.save(path)

def speak_text(text: str):
    if not text:
        return
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    try:
        asyncio.run(_tts_save(text, tmp))
        subprocess.run(["mpg123", "-q", tmp])
    finally:
        os.remove(tmp)

# -------------------- MAIN LISTENER --------------------
def run_listener(gui):
    global STATE
    print("🎧 Listening… say 'Aarya' to wake.")
    speech_frames, question_frames = [], []
    in_speech = False
    question_start = 0.0
    max_frames = int(MAX_SPEECH_SECONDS * 1000 / FRAME_DURATION_MS)

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SIZE,
            dtype="int16",
            channels=1,  # ✅ Fixed: always mono (prevents -9998 ALSA error)
            device=MIC_DEVICE_INDEX,
        ) as stream:
            while True:
                frame, _ = stream.read(FRAME_SIZE)
                if not frame:
                    continue
                detected = vad.is_speech(frame, SAMPLE_RATE)

                if STATE == "WAIT_WAKE":
                    gui.show("idle")
                    if detected:
                        speech_frames.append(frame)
                        in_speech = True
                        if len(speech_frames) > max_frames:
                            speech_frames = speech_frames[-max_frames:]
                    else:
                        if in_speech and len(speech_frames) >= MIN_SPEECH_FRAMES:
                            wav = write_wav(speech_frames)
                            text = transcribe_audio(wav)
                            os.remove(wav)
                            if text and is_wake_word_in_text(text):
                                print("🎙️ Wake word detected! Recording query...")
                                STATE = "RECORD_QUESTION"
                                question_frames = []
                                question_start = time.time()
                            speech_frames.clear()
                            in_speech = False

                elif STATE == "RECORD_QUESTION":
                    gui.show("listening")
                    question_frames.append(frame)
                    if time.time() - question_start >= QUESTION_RECORD_SECONDS:
                        qwav = write_wav(question_frames)
                        qtext = transcribe_audio(qwav)
                        os.remove(qwav)
                        if not qtext:
                            STATE = "WAIT_WAKE"
                            continue
                        print(f"🗣️ You said: {qtext}")
                        reply = answer_command(qtext)
                        print(f"🤖 {reply}\n")
                        STATE = "SPEAKING"
                        gui.show("speaking")
                        speak_text(reply)
                        STATE = "WAIT_WAKE"
                        question_frames.clear()

    except KeyboardInterrupt:
        print("🛑 Exiting...")
        gui.destroy()
    except Exception as e:
        print("⚠️ Error:", e)
        gui.destroy()

# -------------------- ENTRY --------------------
if __name__ == "__main__":
    gifs = {
        "idle": "idle_black.gif",
        "listening": "thinking.gif",
        "speaking": "speaking.gif",
    }

    gui = GifPlayer(gifs)
    listener_thread = threading.Thread(target=run_listener, args=(gui,), daemon=True)
    listener_thread.start()
    gui.mainloop()

