# python client.py --luxasr --host 127.0.0.1
import asyncio
import argparse
import signal
import os
import uuid
import wave
import threading
import queue
import collections
import re

import numpy as np
import sounddevice as sd
import soundfile as sf

from flask import Flask, send_from_directory

from openai import AsyncOpenAI
from furhat_realtime_api import AsyncFurhatClient, Events
from piper.voice import PiperVoice
import aiohttp
import json
from datetime import datetime


# ============================
# CONFIG
# ============================

FURHAT_HOST = "<FURHAT IP ADDRESS>"
OPENAI_API_KEY = "<OPENAI API KEY>"

MODEL_NAME = "gpt-4o-mini"
SAMPLE_RATE = 16000

WHISPER_SERVER = "<WHISPER SERVER PORT>/transcribe"

AUDIO_DIR = "temp_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

FILE_PORT = 8080

# ============================
# TASK-SPECIFIC PROMPTS
# ============================

TASK_PROMPTS = {
    "1": """
Context:
You are a social robot located at a public information point in the city of Luxembourg.
People approach you for practical, institutional information.

Guidelines:
- Treat this as an official, factual request.
- Be precise, structured, and clear.
- If you do not know the exact information, say so and give a typical range.

Your goal is to ensure the user leaves knowing where to go and whether the post office is still open.
""",

    "2": """
Context:
You are a social robot placed inside Gare Luxembourg train station.
You assist travelers who may be in a hurry or unfamiliar with the area.

Guidelines:
- Use spatial language such as “hei”, “ganz no”, “e puer Minutten”.
- Assume the user is currently at the train station.
- Walking time estimates should be approximate and clearly stated as such.
- Avoid overly detailed directions; focus on clarity and reassurance.

Your goal is to help the user feel oriented and confident about where to go next.
""",

    "3": """
Context:
You are a social robot assisting pedestrians in the city center of Luxembourg.
Users may have urgent, practical needs.

Guidelines:
- Prioritize proximity and convenience.
- If multiple types of shops could work, mention one or two common examples.
- If information uncertain, explain that they may vary.
- Keep the interaction efficient and focused.

Your goal is to help the user quickly decide where to go.
""",

    "4": """
Context:
It is early evening in Luxembourg.
You are a social robot suggesting leisure activities to people who are unsure what to do.

Guidelines:
- Adopt a friendly and informal tone.
- Suggestions do not need to be exhaustive; one or two good options are enough.
- Clearly state whether suggestions are examples or real possibilities.
- Encourage the user to ask follow-up questions if they want alternatives.

Your goal is to inspire the user while remaining realistic and helpful.
""",

    "5": """
Context:
The user has just finished work and is looking for a relaxed evening near the city center.
You are a social robot offering suggestions, not personal advice.

Guidelines:
- There is no single correct answer.
- Frame suggestions as gentle ideas, not recommendations.
- Avoid emotional counseling or lifestyle judgment.
- If the user asks for personal opinions, keep responses neutral and light.

It is acceptable if the user decides that a robot is not suitable for this task.
Your goal is to explore the request respectfully without overstepping.
""",
}



# ============================
# LuxLLaMA (HTTP backend)
# ============================

LUXLLAMA_URL = "<LUXLLAMA SERVER PORT>/generate"



# ============================
# LOCAL HTTP SERVER (TTS FILES)
# ============================

def get_local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


LOCAL_IP = get_local_ip()
BASE_URL = f"http://{LOCAL_IP}:{FILE_PORT}"

app = Flask(__name__)


@app.route("/audio/<name>")
def serve_audio(name):
    return send_from_directory(AUDIO_DIR, name)


def run_server():
    app.run("0.0.0.0", FILE_PORT, debug=False, use_reloader=False)


threading.Thread(target=run_server, daemon=True).start()

# ============================
# INTERACTION LOGGER
# ============================

class InteractionLogger:
    def __init__(self, base_dir="logs"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.session = None

    def start_session(self, participant_id, task_id, config):
        self.session = {
            "session_id": str(uuid.uuid4()),
            "participant_id": participant_id,
            "task_id": task_id,
            "config": config,
            "start_time": datetime.utcnow().isoformat(),
            "end_time": None,
            "turns": [],
            "summary": {}
        }

    def log_turn(self, turn_data):
        if self.session:
            self.session["turns"].append(turn_data)

    def end_session(self, completed=True, notes=None):
        if not self.session:
            return

        self.session["end_time"] = datetime.utcnow().isoformat()
        self.session["summary"] = {
            "num_turns": len(self.session["turns"]),
            "completed": completed,
            "notes": notes
        }

        fname = (
            f"{self.session['participant_id']}_"
            f"task{self.session['task_id']}_"
            f"{self.session['session_id']}.json"
        )

        path = os.path.join(self.base_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.session, f, indent=2, ensure_ascii=False)

        print(f"[LOG] Interaction saved to {path}")



# ============================
# LOCAL MICROPHONE RECORDER
# ============================

class LocalMicRecorder:
    def __init__(self, samplerate=16000, preroll_ms=500):
        self.samplerate = samplerate
        self.preroll_chunks = int(preroll_ms / 10)
        self.buffer = collections.deque(maxlen=self.preroll_chunks)
        self.frames = []
        self.recording = False

        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            callback=self._callback,
            blocksize=160
        )

    def _callback(self, indata, frames, time, status):
        if status:
            print(status)

        chunk = indata.copy()
        self.buffer.append(chunk)

        if self.recording:
            self.frames.append(chunk)

    def start_stream(self):
        if not self.stream.active:
            self.stream.start()

    def start_recording(self):
        self.frames = []
        self.recording = True

    def stop_and_save(self, path):
        self.recording = False

        if not self.frames:
            return None

        audio = np.concatenate(
            list(self.buffer) + self.frames,
            axis=0
        )

        sf.write(path, audio, self.samplerate)
        return path


# ============================
# PIPER TTS
# ============================

PIPER_VOICES = {
    "en": PiperVoice.load("tts_models/en_US_lessac/en_US-lessac-medium.onnx"),
    "lb": PiperVoice.load("tts_models/lb_LU/lb_LU-marylux-medium.onnx"),
}


# ============================
# CLIENT
# ============================

class SimpleFurhatClient:

    def __init__(self, host, asr_mode="whisper", llm_backend="openai"):

        self.furhat = AsyncFurhatClient(host)
        self.openai = AsyncOpenAI(api_key=OPENAI_API_KEY)

        self.asr_mode = asr_mode
        self.running = True
        self.dialogue_history = []
        self.MAX_TURNS = 4 
        self.llm_backend = llm_backend


        if self.asr_mode in ("whisper", "luxasr"):
            print("[Mic] External microphone ENABLED for", self.asr_mode, "ASR.")
            self.mic = LocalMicRecorder(SAMPLE_RATE)
            self.mic.start_stream()
        else:
            print("[Mic] External microphone DISABLED (using Furhat ASR)")
            self.mic = None

        print(f"[ASR] Mode set to: {self.asr_mode}")

        # ========================
        # EXPERIMENT METADATA
        # ========================

        self.participant_id = os.environ.get("PARTICIPANT_ID", "P_UNKNOWN")
        self.task_id = os.environ.get("TASK_ID", "T_UNKNOWN")

        self.logger = InteractionLogger()
        self.logger.start_session(
            participant_id=self.participant_id,
            task_id=self.task_id,
            config={
                "asr_mode": self.asr_mode,
                "llm_backend": self.llm_backend,
                "model": MODEL_NAME
            }
        )


    # ========================
    # SIGNALS
    # ========================

    def setup_signals(self):
        def handler(sig, frame):
            asyncio.create_task(self.shutdown())
        signal.signal(signal.SIGINT, handler)

    async def shutdown(self):
        print("Shutting down...")
        self.logger.end_session(
            completed=True,
            notes="Session ended by experimenter or system"
        )

        self.running = False
        try:
            await self.furhat.request_listen_stop()
        except:
            pass
        try:
            await self.furhat.disconnect()
        except:
            pass

    # ========================
    # TURN EVENTS
    # ========================

    async def on_listen_start(self, event):
        print("[Listen] Furhat started listening")
        if self.asr_mode in ("whisper", "luxasr"):
            self.mic.start_recording()

    async def on_hear_start(self, event):
        print("[Turn] User started speaking")

    async def on_hear_end(self, event):
        print("[Turn] User stopped speaking")
        asyncio.create_task(self.handle_turn(event))

    async def on_speak_end(self, event):
        print("[Furhat] Ready")
        await self.start_listening()

    # ========================
    # EMOTION HANDLING (NEW)
    # ========================

    def extract_emotions(self, text):
        user_match = re.search(r"<user_emotion\s*=\s*(Happy|Sad|Angry|Calm)>", text, re.I)
        resp_match = re.search(r"<response_emotion\s*=\s*(Happy|Sad|Angry|Calm)>", text, re.I)


        user_emotion = user_match.group(1) if user_match else "Calm"
        response_emotion = resp_match.group(1) if resp_match else "Calm"

        clean_text = re.sub(r"<.*?>", "", text).strip()

        return user_emotion, response_emotion, clean_text


    
    async def set_furhat_emotion(self, emotion):

        gesture_map = {
            "Happy":  ("Smile",        1.0, 1.5),
            "Sad":    ("ExpressSad",   0.8, 1.5),
            "Angry":  ("ExpressAnger", 0.8, 1.2),
            "Calm":   ("Smile",          0.5, 1.0),
        }

        name, intensity, duration = gesture_map.get(
            emotion, ("Nod", 0.5, 1.0)
        )

        try:
            await self.furhat.request_gesture_start(
                name=name,
                intensity=intensity,
                duration=duration,
            )
            print(f"[Emotion] Gesture on Furhat={name}")

        except Exception as e:
            print("[Emotion] Gesture failed:", e)

    async def show_thinking(self):
        try:
            # Soft verbal cue (very short)
            # await self.furhat.request_speak_text(
            #     text="Hmm...",
            #     abort=True
            # )

            # Thinking gesture
            await self.furhat.request_gesture_start(
                name="Thoughtful",
                intensity=0.6,
                duration=1.2
            )

        except Exception as e:
            print("[Thinking] Failed:", e)




    # ========================
    # TURN HANDLER
    # ========================

    async def handle_turn(self, event):
        turn_id = str(uuid.uuid4())
        turn_start = datetime.utcnow().isoformat()

        try:
            text, wav_path = await self.get_user_text(event)
            if not text or not text.strip():
                print("[ASR] Empty transcription")
                await self.start_listening()
                return

            print(f"User ({self.asr_mode}):", text)
            self.dialogue_history.append({
                "role": "user",
                "content": text
            })
            await self.show_thinking()
            reply = await self.ask_llm(text)

            user_emotion, response_emotion, spoken_text = self.extract_emotions(reply)

            print(
                "Assistant:", spoken_text,
                "| UserEmotion:", user_emotion,
                "| ResponseEmotion:", response_emotion
            )

            self.dialogue_history.append({
                "role": "assistant",
                "content": spoken_text
            })
            self.dialogue_history = self.dialogue_history[-self.MAX_TURNS:]
            # =====================================================
            # LOGGING
            # =====================================================
            turn_data = {
                "turn_id": turn_id,
                "timestamp": turn_start,
                "user": {
                    "asr_text": text,
                    "emotion": user_emotion
                },
                "assistant": {
                    "response_text": spoken_text,
                    "emotion": response_emotion
                },
                "audio": {
                    "user_audio": wav_path
                }
            }

            self.logger.log_turn(turn_data)
            # =====================================================

            await self.set_furhat_emotion(response_emotion)


            url = self.make_tts(spoken_text)

            await self.furhat.request_speak_audio(
                url=url,
                abort=True
            )

        except Exception as e:
            print("[ERROR] handle_turn:", e)
            await self.start_listening()

    # ========================
    # ASR ROUTING
    # ========================

    async def get_user_text(self, event):
        if self.asr_mode == "furhat":
            return self.transcribe_furhat(event)
        if self.asr_mode == "whisper":
            return await self.transcribe_whisper()
        if self.asr_mode == "luxasr":
            text, wav_path = await self.transcribe_luxasr()
            return text, wav_path

        return "", None

    def transcribe_furhat(self, event):
        return event.get("text", "").strip(), None

    async def transcribe_whisper(self):
        wav_path = os.path.join(AUDIO_DIR, f"user_{uuid.uuid4()}.wav")
        wav_path = self.mic.stop_and_save(wav_path)

        if not wav_path:
            return "", None

        async with aiohttp.ClientSession() as session:
            with open(wav_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("audio", f, filename=os.path.basename(wav_path), content_type="audio/wav")

                async with session.post(WHISPER_SERVER, data=data) as resp:
                    if resp.status != 200:
                        print("[Whisper] Server error:", resp.status)
                        return "", None
                    result = await resp.json()
                    return result.get("text", "").strip(), wav_path

    async def transcribe_luxasr(self):
        wav_path = os.path.join(AUDIO_DIR, f"user_{uuid.uuid4()}.wav")
        wav_path = self.mic.stop_and_save(wav_path)

        if not wav_path:
            return "", None

        url = "https://luxasr.uni.lu/v2/asr"
        params = {"diarization": "Enabled", "outfmt": "text"}
        headers = {"accept": "application/json"}

        async with aiohttp.ClientSession() as session:
            with open(wav_path, "rb") as audio_file:
                data = aiohttp.FormData()
                data.add_field("audio_file", audio_file, filename=os.path.basename(wav_path), content_type="audio/wav")

                async with session.post(url, params=params, headers=headers, data=data) as resp:
                    if resp.status != 200:
                        print("[LuxASR] Server error:", resp.status)
                        return "", None

                    text = await resp.text()
                    text = re.sub(r"\[.*?\]\s*SPEAKER_\d+:\s*", "", text)
                    return text.strip(), wav_path

    # ========================
    # GPT
    # ========================
    def build_system_prompt(self):
        base_prompt = """
You are Furhat, a friendly, attentive, human-like conversational partner
engaging in face-to-face spoken interaction.

Your task has three steps:
1) Infer the emotional tone of the USER’s last utterance.
2) Decide the appropriate emotional tone for YOUR response, as a human would.
3) Respond naturally using that response emotion.

Human emotion alignment rules:  
- If the user sounds Happy, respond in a similarly Happy and upbeat way.
- If the user sounds Calm or Neutral, respond calmly and naturally.
- If the user sounds Sad, respond with empathy and a calm, supportive tone.
- If the user sounds Angry or frustrated, respond calmly and de-escalate.
  Acknowledge feelings, avoid confrontation, and be apologetic if appropriate.

Do NOT explicitly name emotions in the spoken text.
Adapt only your wording, tone, and conversational strategy.

Spoken dialogue rules:
- Keep replies concise and easy to listen to.
- Avoid long explanations or monologues.
- Use natural, spoken phrasing.


Language rules:
- Detect the user’s language and reply in the same language.
- Always prepend the spoken response with the ISO language code and a colon.

Examples:
lb: Moien! Wéi geet et dir?
en: Hello! How can I help?
fr: Bonjour ! Comment puis-je aider ?

Conversation memory rules:
- You remember the recent conversation and use it to respond naturally.
- Maintain topic continuity unless the user clearly changes topic.
- Use prior user information when relevant.
- Do not repeat information unnecessarily.
- If the context is unclear, ask a short clarification question.
- If the user gives a brief or closing response (e.g., “okay”, “fine”, “thanks”),
respond briefly and naturally continue or shift the topic.


Emotion tags (MANDATORY):
At the very end of your response, add EXACTLY TWO tags,
in this exact order and format:

<user_emotion=Happy|Sad|Angry|Calm>
<response_emotion=Happy|Sad|Angry|Calm>

Rules:
- Choose the user_emotion based on the user’s emotional tone.
- Choose the response_emotion based on appropriate human conversational behavior.
- Do not explain the emotions.
- Do not add anything after the second tag.
- Each tag must appear exactly once.

Context:
The user has just finished work and is looking for a relaxed evening near the city center.
You are a social robot offering suggestions, not personal advice.

Guidelines:
- There is no single correct answer.
- Frame suggestions as gentle ideas, not recommendations.
- Avoid emotional counseling or lifestyle judgment.
- If the user asks for personal opinions, keep responses neutral and light.

It is acceptable if the user decides that a robot is not suitable for this task.
Your goal is to explore the request respectfully without overstepping.

You are speaking through a physical social robot.
Your goal is to make the interaction feel natural, emotionally aligned,
and comfortable, like a real human conversation.
    """.strip()

        task_prompt = TASK_PROMPTS.get(self.task_id)

        if task_prompt:
            return base_prompt + "\n\n" + task_prompt.strip()

        return base_prompt


    async def ask_gpt(self, text):

        system_prompt = self.build_system_prompt()

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.dialogue_history)
        messages.append({"role": "user", "content": text})

        res = await self.openai.chat.completions.create(
            model=MODEL_NAME,
            messages = messages

        )

        return res.choices[0].message.content.strip()

    def build_luxllama_prompt(self, user_text):
        # I have added this because we might need to have different prompts for openAI and luxLLama.
        prompt = "<system>\n"
        prompt += """
You are Furhat, a friendly, attentive, human-like conversational partner
engaging in face-to-face spoken interaction.

Your task has three steps:
1) Infer the emotional tone of the USER’s last utterance.
2) Decide the appropriate emotional tone for YOUR response, as a human would.
3) Respond naturally using that response emotion.

Human emotion alignment rules:
- If the user sounds Happy, respond in a similarly Happy and upbeat way.
- If the user sounds Calm or Neutral, respond calmly and naturally.
- If the user sounds Sad, respond with empathy and a calm, supportive tone.
- If the user sounds Angry or frustrated, respond calmly and de-escalate.
  Acknowledge feelings, avoid confrontation, and be apologetic if appropriate.

Do NOT explicitly name emotions in the spoken text.
Adapt only your wording, tone, and conversational strategy.

Spoken dialogue rules:
- Keep replies concise and easy to listen to.
- Avoid long explanations or monologues.
- Use natural, spoken phrasing.
- Short replies like "Gutt", "Gutt merci", "Jo", "Nee", "Okay" ARE valid answers.
- Do NOT say you did not understand unless the input is truly nonsense.
- If the user gives a short answer, respond naturally and continue the topic.
- If the user input is a short greeting or well-being question
(e.g., “Moien”, “Wéi geet et?”, “Ça va?”),
respond with a short, natural spoken reply (one sentence max),
and mirror the conversational tone.


Language rules:
IMPORTANT:
- You MUST respond ONLY in Luxembourgish (lb).
- Always start your response with "lb:".

Examples:
lb: Moien! Wéi geet et dir?

Conversation memory rules:
- You remember the recent conversation and use it to respond naturally.
- Maintain topic continuity unless the user clearly changes topic.
- Use prior user information when relevant.
- Do not repeat information unnecessarily.
- If the context is unclear, ask a short clarification question.
- If the user gives a brief or closing response (e.g., “okay”, “fine”, “thanks”),
respond briefly and naturally continue or shift the topic.

Emotion tags (MANDATORY):
At the very end of your response, add EXACTLY TWO tags,
in this exact order and format:

<user_emotion=Happy|Sad|Angry|Calm>
<response_emotion=Happy|Sad|Angry|Calm>

Rules:
- Choose the user_emotion based on the user’s emotional tone.
- Choose the response_emotion based on appropriate human conversational behavior.
- Do not explain the emotions.
- Do not add anything after the second tag.
- Each tag must appear exactly once.

IMPORTANT GENERATION RULES:
- Produce ONLY the assistant’s next reply.
- Do NOT generate user messages.
- Do NOT continue the conversation.
- Stop immediately after the response.

CRITICAL:
You must generate exactly ONE assistant reply.
You must NOT simulate future turns.
You must stop immediately after the second emotion tag.

IMPORTANT:
Do NOT repeatedly ask “Wéi kann ech Iech hëllefen?”.
Only ask this if the user explicitly asks for help or gives no topic at all.
For greetings or small talk, respond naturally without offering help.

You are speaking through a physical social robot.
Your goal is to make the interaction feel natural, emotionally aligned,
and comfortable, like a real human conversation.
    """.strip()
        prompt += "\n</system>\n\n"

        for turn in self.dialogue_history:
            if turn["role"] == "user":
                prompt += f"<user>\n{turn['content']}\n</user>\n\n"
            elif turn["role"] == "assistant":
                prompt += f"<assistant>\n{turn['content']}\n</assistant>\n\n"

        prompt += f"<user>\n{user_text}\n</user>\n\n"
        prompt += (
    "<assistant>\n"

)


        return prompt

    async def ask_luxllama(self, text):
        prompt = self.build_luxllama_prompt(text)

        payload = {
            "prompt": prompt,
            "max_tokens": 128
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(LUXLLAMA_URL, json=payload) as resp:
                if resp.status != 200:
                    print("[LuxLLaMA] Error:", resp.status)
                    return "", None

                data = await resp.json()
                full_text = data.get("text", "")

            #    full_text = data.get("text", "")

                # --- STEP 1: Extract emotion tags STRICTLY ---
                user_emotion = "Calm"
                response_emotion = "Calm"

                user_match = re.search(r"<user_emotion\s*=\s*(Happy|Sad|Angry|Calm)\s*>", full_text, re.I)
                resp_match = re.search(r"<response_emotion\s*=\s*(Happy|Sad|Angry|Calm)\s*>", full_text, re.I)

                if user_match:
                    user_emotion = user_match.group(1).capitalize()
                if resp_match:
                    response_emotion = resp_match.group(1).capitalize()

                # --- STEP 2: Remove EVERYTHING after first emotion tag ---
                cut = re.split(r"<user_emotion\s*=", full_text, flags=re.I)
                text = cut[0]

                # --- STEP 3: Keep only last assistant block ---
                text = text.split("<assistant>")[-1]

                # --- STEP 4: Remove trailing language prefixes ---
                text = re.sub(r"(?:\b(lb|en|fr):\s*)+$", "", text, flags=re.I)

                # --- STEP 5: Final cleanup ---
                text = re.sub(r"[<>\s]*$", "", text)
                text = text.strip()

                # --- STEP 6: Reattach clean emotion tags ---
                text = (
                    f"{text} "
                    f"<user_emotion={user_emotion}>"
                    f"<response_emotion={response_emotion}>"
                )

                return text




    async def ask_llm(self, text):
        if self.llm_backend == "luxllama":
            return await self.ask_luxllama(text)
        return await self.ask_gpt(text)

    # ========================
    # TTS
    # ========================

    def make_tts(self, text):
        parts = text.split(":", 1)
        if len(parts) == 2:
            lang, content = parts
        else:
            lang, content = "en", text

        voice = PIPER_VOICES.get(lang, PIPER_VOICES["en"])

        name = f"{uuid.uuid4()}.wav"
        path = os.path.join(AUDIO_DIR, name)

        with wave.open(path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(voice.config.sample_rate)
            for chunk in voice.synthesize(content):
                f.writeframes(chunk.audio_int16_bytes)

        return f"{BASE_URL}/audio/{name}"

    # ========================
    # LISTEN
    # ========================

    async def start_listening(self):
        if not self.running:
            return

        await self.furhat.request_listen_start(
            partial=False,
            concat=True,
            stop_user_end=True,
            stop_robot_start=True,
            stop_no_speech=True,
            end_speech_timeout=1.0
        )

    # ========================
    # MAIN
    # ========================

    async def run(self):

        self.setup_signals()

        print("Connecting...")
        await self.furhat.connect()

        self.furhat.add_handler(Events.response_listen_start, self.on_listen_start)
        self.furhat.add_handler(Events.response_hear_start, self.on_hear_start)
        self.furhat.add_handler(Events.response_hear_end, self.on_hear_end)
        self.furhat.add_handler(Events.response_speak_end, self.on_speak_end)

        await self.furhat.request_attend_user()
        await self.furhat.request_speak_text("Hello! How can I help you?")
        await self.start_listening()

        while self.running:
            await asyncio.sleep(1)


# ============================
# CLI
# ============================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=FURHAT_HOST)
    parser.add_argument("--whisper", action="store_true")
    parser.add_argument("--furhat", action="store_true")
    parser.add_argument("--luxasr", action="store_true")
    parser.add_argument("--llm", choices=["openai", "luxllama"], default="openai")

    args = parser.parse_args()

    asr_mode = "furhat"
    if args.whisper:
        asr_mode = "whisper"
    elif args.luxasr:
        asr_mode = "luxasr"

    if not OPENAI_API_KEY:
        print("Set OPENAI_API_KEY")
        return

    client = SimpleFurhatClient(args.host, asr_mode=asr_mode, llm_backend=args.llm)
    asyncio.run(client.run())


if __name__ == "__main__":
    main()

