"""Local Whisper + Piper Flask Server"""

from transformers import WhisperProcessor, WhisperForConditionalGeneration
import torchaudio
import numpy as np
import threading
import tempfile
import torch
import os
import wave
import traceback
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from huggingface_hub import login
from piper.voice import PiperVoice
from langdetect import detect, DetectorFactory
import uuid
import warnings
import socket
# -------------------------------------------------------------
# Configuration
# -------------------------------------------------------------
DetectorFactory.seed = 0
HF_TOKEN = "<HF TOKEN>"  # Replace with your own
login(HF_TOKEN)
local_ip = socket.gethostbyname(socket.gethostname())

# Automatically pick GPU (NVIDIA CUDA / AMD DirectML) or CPU
if torch.cuda.is_available():
    device = torch.device("cuda")
elif hasattr(torch, "directml") and torch.directml.is_available():
    device = torch.device("directml")
else:
    device = torch.device("cpu")

print(f"✅ Using device: {device}")

# -------------------------------------------------------------
# Load Models
# -------------------------------------------------------------
print("🔄 Loading Whisper model...")
whisper_processor = WhisperProcessor.from_pretrained("models/whisper")
whisper_model = WhisperForConditionalGeneration.from_pretrained("models/whisper").to(device)

print("🔄 Loading Piper voices...")
PIPER_VOICES = {
    "en": PiperVoice.load("models/piper/en_US_lessac/en_US-lessac-medium.onnx"),
    "lb": PiperVoice.load("models/piper/lb_LU/lb_LU-marylux-medium.onnx")
}
print("✅ Models loaded successfully.")

# -------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------
def load_audio_whisper(audio_path, target_sr=16000):
    waveform, sample_rate = torchaudio.load(audio_path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0)
    if sample_rate != target_sr:
        waveform = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=target_sr)(waveform)
    return waveform.squeeze().numpy().astype(np.float32)


def transcribe_whisper(audio_path):
    audio_np = load_audio_whisper(audio_path)
    inputs = whisper_processor(audio_np, sampling_rate=16000, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        generated_ids = whisper_model.generate(
            **inputs, num_beams=1, do_sample=False, max_new_tokens=128, return_timestamps=False
        )
    return whisper_processor.decode(generated_ids[0], skip_special_tokens=True)


def split_by_language(text):
    import re
    segments = re.split(r'(?<=[.!?])\s+', text)
    lang_blocks = []
    for segment in segments:
        cleaned = segment.strip()
        if cleaned:
            try:
                lang = detect(cleaned)
                lang = "lb" if lang in ["lb", "de"] else "en"
            except:
                lang = "en"
            lang_blocks.append((lang, cleaned))
    return lang_blocks


def speak_multilang(text, voices_dict, output_path="final_output.wav"):
    segments = split_by_language(text)
    with wave.open(output_path, "wb") as out_wav:
        out_wav.setnchannels(1)
        out_wav.setsampwidth(2)
        out_wav.setframerate(voices_dict["en"].config.sample_rate)
        for lang, segment in segments:
            voice = voices_dict.get(lang, voices_dict["en"])
            for chunk in voice.synthesize(segment):
                out_wav.writeframes(chunk.audio_int16_bytes)
    return output_path


# -------------------------------------------------------------
# Flask App Setup
# -------------------------------------------------------------
app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "static/audio"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/")
def index():
    return "Hello from Whisper + Piper Local Server!"


# -------------------------------------------------------------
# Transcription Endpoint
# -------------------------------------------------------------
@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400
    file = request.files["audio"]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        file.save(tmp.name)
        audio_path = tmp.name

    try:
        text = transcribe_whisper(audio_path)
        print(f"📝 Transcribed: {text}")
        return jsonify({"text": text})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


# -------------------------------------------------------------
# Text-to-Speech Endpoint
# -------------------------------------------------------------
@app.route("/tts", methods=["POST"])
def tts():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON body provided"}), 400

        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "Missing 'text' in request"}), 400

        # Determine language code
        parts = text.split(":", 1)
        if len(parts) == 2:
            lang_code, clean_text = parts[0].strip(), parts[1].strip()
        else:
            lang_code, clean_text = "en", text

        voice = PIPER_VOICES.get(lang_code, PIPER_VOICES["en"])

        filename = f"{uuid.uuid4()}.wav"
        file_path = os.path.join(UPLOAD_FOLDER, filename)

        with wave.open(file_path, "wb") as out_wav:
            out_wav.setnchannels(1)
            out_wav.setsampwidth(2)
            out_wav.setframerate(voice.config.sample_rate)
            for chunk in voice.synthesize(clean_text):
                out_wav.writeframes(chunk.audio_int16_bytes)

        # public_url = f"http://127.0.0.1:9000/{UPLOAD_FOLDER}/{filename}"
        public_url = f"http://{local_ip}:9000/{UPLOAD_FOLDER}/{filename}"
        return jsonify({"url": public_url})
        # return send_file(file_path, mimetype="audio/wav", as_attachment=False)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/static/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# -------------------------------------------------------------
# Run Server
# -------------------------------------------------------------
if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    # print("🚀 Starting Flask server on http://127.0.0.1:9000 ...")
    app.run(host="0.0.0.0", port=9000, debug=False, use_reloader=False)
