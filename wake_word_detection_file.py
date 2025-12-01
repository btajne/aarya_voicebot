import requests
import sounddevice as sd
import wave
import tempfile

ELEVEN_API_KEY = "557ffd060eca83bf1c3db4ea8ccc1ef81ccf628caf489404cfbcc917082558da"
STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

SAMPLE_RATE = 16000
DURATION = 2   # record time in seconds

def record_wav():
    print("🎙️ Recording... Speak now!")
    audio = sd.rec(int(SAMPLE_RATE * DURATION), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
    sd.wait()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return tmp.name

def transcribe(path):
    headers = {"xi-api-key": ELEVEN_API_KEY}
    data = {"model_id": "scribe_v1", "language_code": "en"}
    with open(path, "rb") as f:
        r = requests.post(STT_URL, headers=headers, files={"file": f}, data=data)
    if r.status_code == 200:
        return r.json().get("text", "").strip()
    else:
        print("⚠️ STT Error:", r.text)
        return ""

def main():
    print("✨ Aarya Pronunciation Collector Started")
    print("Press ENTER to record each sample.")
    print("Say the name 'Aarya' differently each time.\n")

    while True:
        input("➡️  Press ENTER and speak...")
        wav = record_wav()
        text = transcribe(wav)
        print(f"🗣️ Recognized: {text}")

        if text:
            with open("aarya_pronunciations.txt", "a") as f:
                f.write(text + "\n")
            print("✅ Saved to aarya_pronunciations.txt\n")
        else:
            print("❌ Nothing recognized, try again.\n")

if __name__ == "__main__":
    main()

