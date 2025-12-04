#!/usr/bin/env python3
import warnings
warnings.filterwarnings("ignore")

import sounddevice as sd
import requests, wave, tempfile, os, time, asyncio, subprocess
import edge_tts
import threading
import tkinter as tk
from PIL import Image, ImageTk
import cv2
import datetime, re

# ================================
# CONFIG
# ================================
MIC_DEVICE = "hw:1,0"        # ✅ USB mic
SAMPLE_RATE = 48000
RECORD_SECONDS = 6

STATE = "IDLE"
reply = ""

ELEVEN_API_KEY = "sk_527b4e2851fb5e97621d473c099f9f3da5eb062abb18b381"
STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


# ================================
# VIDEO PLAYER
# ================================
class VideoPlayer(tk.Tk):
    def __init__(self, videos):
        super().__init__()

        self.title("Aarya VoiceBot")
        self.attributes("-fullscreen", True)
        self.configure(bg="black")
        self.bind("<q>", lambda e: os._exit(0))

        self.w = self.winfo_screenwidth()
        self.h = self.winfo_screenheight()

        self.label = tk.Label(self, bg="black")
        self.label.pack(fill="both", expand=True)

        self.videos = videos
        self.cap = None
        self.current_state = None
        self.frame_job = None

        self.btn = tk.Button(self,
            text="Activate Aarya",
            font=("Arial", 42, "bold"),
            fg="white",
            bg="black",
            command=self.activate,
            bd=0,
            activeforeground="cyan"
        )
        self.btn.place(relx=0.5, rely=0.5, anchor="center")

        self.show("idle")

    def activate(self):
        global STATE
        STATE = "RECORDING"
        self.btn.place_forget()

    def show_button(self):
        if STATE == "IDLE":
            self.btn.place(relx=0.5, rely=0.5, anchor="center")

    def open_video(self, path):
        if self.cap:
            self.cap.release()

        self.cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)

        if not self.cap.isOpened():
            print("❌ Cannot open:", path)
            return False

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return True

    def show(self, state):
        if state == self.current_state:
            return

        print("🎬 Switching to:", state)

        self.current_state = state

        if self.frame_job:
            self.after_cancel(self.frame_job)

        ok = self.open_video(self.videos[state])
        if ok:
            self.update_frame()

    def update_frame(self):
        if not self.cap:
            return

        ret, frame = self.cap.read()

        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                return

        frame = cv2.resize(frame, (self.w, self.h))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        img = ImageTk.PhotoImage(Image.fromarray(frame))
        self.label.config(image=img)
        self.label.image = img

        self.frame_job = self.after(33, self.update_frame)   # ~30fps


# ================================
# AUDIO RECORD
# ================================
def record_fixed_time():
    return sd.rec(int(RECORD_SECONDS * SAMPLE_RATE),
             samplerate=SAMPLE_RATE,
             channels=1,
             dtype='int16',
             device=MIC_DEVICE)


def write_wav(audio):
    sd.wait()
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
def transcribe_audio(file):
    with open(file, "rb") as f:
        r = requests.post(STT_URL,
            headers={"xi-api-key": ELEVEN_API_KEY},
            files={"file": f},
            data={"model_id": "scribe_v1", "language_code": "en"}
        )
    return r.json().get("text", "") if r.status_code == 200 else ""


# ================================
# BRAIN
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
# TEXT TO SPEECH
# ================================
async def tts_run(text, file):
    voice = edge_tts.Communicate(text, voice="en-IN-NeerjaNeural")
    await voice.save(file)

def speak_text(text):
    file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    asyncio.run(tts_run(text, file))
    subprocess.run(["mpg123", "-q", file])
    os.remove(file)


# ================================
# THREAD WORKERS
# ================================
def record_thread():
    global STATE, reply
    audio = record_fixed_time()
    path = write_wav(audio)
    text = transcribe_audio(path)
    os.remove(path)
    reply = answer_command(text)

    print("USER:", text)
    print("BOT:", reply)
    STATE = "SPEAKING"


def speak_thread():
    global STATE
    speak_text(reply)
    STATE = "IDLE"


# ================================
# MAIN BRAIN LOOP
# ================================
def run_voice(gui):
    global STATE

    while True:
        if STATE == "IDLE":
            gui.after(0, gui.show, "idle")
            gui.after(0, gui.show_button)

        elif STATE == "RECORDING":
            gui.after(0, gui.show, "listening")
            STATE = "BUSY"
            threading.Thread(target=record_thread, daemon=True).start()

        elif STATE == "SPEAKING":
            gui.after(0, gui.show, "speaking")
            STATE = "BUSY"
            threading.Thread(target=speak_thread, daemon=True).start()

        time.sleep(0.05)


# ================================
# START
# ================================
if __name__ == "__main__":
    videos = {
        "idle": "aarya_idle.mp4",
        "listening": "aarya_listening.mp4",
        "speaking": "aarya_speaking.mp4"
    }

    app = VideoPlayer(videos)
    threading.Thread(target=run_voice, args=(app,), daemon=True).start()
    app.mainloop()

