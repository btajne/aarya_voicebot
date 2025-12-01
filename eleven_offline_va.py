#!/usr/bin/env python3
"""
Aarya Voice Chatbot (Optimized for Reliable Wake Detection)
-----------------------------------------------------------
- Wake word: fuzzy + phonetic match for "Aarya"
- Handles Indian accent variants
- Uses ElevenLabs STT and Edge-TTS
- Filters ambient noise and fake transcriptions
(Clean terminal output version)
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
import logging

# ----------------------- CONFIG -----------------------
ELEVEN_API_KEY = "557ffd060eca83bf1c3db4ea8ccc1ef81ccf628caf489404cfbcc917082558da"
STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

SAMPLE_RATE = 48000
FRAME_DURATION_MS = 20
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)
VAD_MODE = 2
MIN_SPEECH_FRAMES = 8
MAX_SPEECH_SECONDS = 3
QUESTION_RECORD_SECONDS = 4
STT_REQUEST_TIMEOUT = 10
FUZZY_THRESHOLD = 0.78
MIC_DEVICE_INDEX = 1
BT_SINK = "bluez_output.41_42_70_96_76_FD.1"

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
vad = webrtcvad.Vad(VAD_MODE)
STATE = "WAIT_WAKE"

# -------------------- UTILITIES --------------------
def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = s.translate(str.maketrans("", "", string.punctuation))
    return " ".join(s.split())

def fuzzy_match_score(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()

def is_wake_word_in_text(text: str) -> bool:
    t = normalize_text(text)
    if not t:
        return False
    for v in VARIANTS:
        if fuzzy_match_score(t, v) >= FUZZY_THRESHOLD:
            return True
        for word in t.split():
            if fuzzy_match_score(word, v) >= FUZZY_THRESHOLD:
                return True
    return False

def write_wav(frames, rate=SAMPLE_RATE):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    path = tmp.name
    tmp.close()
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))
    return path

def transcribe_audio(path: str) -> str:
    headers = {"xi-api-key": ELEVEN_API_KEY}
    data = {"model_id": "scribe_v1", "language_code": "en"}
    try:
        with open(path, "rb") as f:
            r = requests.post(STT_URL, headers=headers, files={"file": f}, data=data, timeout=STT_REQUEST_TIMEOUT)
        if r.status_code == 200:
            text = r.json().get("text", "").strip()
            if text:
                return text
    except Exception:
        pass
    return ""

def answer_command(cmd: str) -> str:
    t = normalize_text(cmd)
    now = datetime.datetime.now()
    if "time" in t:
        return now.strftime("The time is %I:%M %p.")
    if "date" in t:
        return now.strftime("Today's date is %d %B %Y.")
    if "day" in t:
        return now.strftime("Today is %A.")
    if "hello" in t or "hi" in t:
        return "Hello! How can I help you?"
    if "joke" in t:
        return "Why did the computer go to the doctor? Because it caught a virus!"
    return f"I heard: {cmd}" if cmd else "I didn't catch that."

async def _tts_save(text: str, path: str):
    tts = edge_tts.Communicate(text, voice="en-US-AriaNeural")
    await tts.save(path)

def speak_text(text: str):
    if not text:
        return
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    try:
        asyncio.run(_tts_save(text, tmp))
        null = open(os.devnull, "w")
        if BT_SINK:
            subprocess.run(["mpg123", "-q", "-a", BT_SINK, tmp], stdout=null, stderr=null)
        else:
            subprocess.run(["mpg123", "-q", tmp], stdout=null, stderr=null)
        null.close()
    finally:
        try:
            os.remove(tmp)
        except:
            pass

# -------------------- MAIN LOOP --------------------
def run_listener():
    global STATE
    print("🎧 Listening… say 'Aarya' to wake.")
    speech_frames = []
    question_frames = []
    in_speech = False
    question_start = 0.0
    max_frames = int(MAX_SPEECH_SECONDS * 1000 / FRAME_DURATION_MS)

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SIZE,
            dtype="int16",
            channels=1,
            device=MIC_DEVICE_INDEX,
        ) as stream:
            while True:
                frame, _ = stream.read(FRAME_SIZE)
                if not frame:
                    continue
                detected = vad.is_speech(frame, SAMPLE_RATE)

                if STATE == "WAIT_WAKE":
                    if detected:
                        speech_frames.append(frame)
                        in_speech = True
                        if len(speech_frames) > max_frames:
                            speech_frames = speech_frames[-max_frames:]
                    else:
                        if in_speech and len(speech_frames) >= MIN_SPEECH_FRAMES:
                            try:
                                wav = write_wav(speech_frames)
                                text = transcribe_audio(wav)
                                if text and is_wake_word_in_text(text):
                                    print("🎙️ Wake word detected! Recording query...")
                                    STATE = "RECORD_QUESTION"
                                    question_frames = []
                                    question_start = time.time()
                            finally:
                                os.remove(wav)
                            speech_frames.clear()
                            in_speech = False

                elif STATE == "RECORD_QUESTION":
                    question_frames.append(frame)
                    if time.time() - question_start >= QUESTION_RECORD_SECONDS:
                        try:
                            qwav = write_wav(question_frames)
                            qtext = transcribe_audio(qwav)
                        finally:
                            os.remove(qwav)

                        if not qtext:
                            STATE = "WAIT_WAKE"
                            question_frames.clear()
                            continue

                        qtext_lower = qtext.lower().strip()
                        ignore_patterns = [
                            "(music)", "(wind)", "(silence)", "(noise)", "(breathing)",
                            "(birds)", "(dog)", "(electronic)", "(heartbeat)", "(sound)",
                            "(whooshing)", "(background)", "(suspenseful)", "(chirping)",
                            "(environmental)", "(ambient)"
                        ]

                        if any(p in qtext_lower for p in ignore_patterns):
                            STATE = "WAIT_WAKE"
                            question_frames.clear()
                            continue

                        if len(qtext_lower.split()) < 2 and qtext_lower not in ("hi", "hello"):
                            STATE = "WAIT_WAKE"
                            question_frames.clear()
                            continue

                        print(f"🗣️ You said: {qtext}")
                        reply = answer_command(qtext)
                        print(f"🤖 {reply}\n")
                        speak_text(reply)

                        STATE = "WAIT_WAKE"
                        question_frames.clear()

    except KeyboardInterrupt:
        print("🛑 Exiting...")
    except Exception as e:
        print("⚠️ Error:", e)


# -------------------- ENTRY --------------------
if __name__ == "__main__":
    run_listener()

