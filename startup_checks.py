import os
from pathlib import Path
from dotenv import load_dotenv
import speech_recognition as sr
import win32com.client
from audio_processing import open_microphone
from database import ENV_PATH, RECORDINGS_DIR


def run_startup_diagnostics():
    """
    Runs pre-flight checks for required configuration and hardware devices.
    Returns a list of dicts with check results.
    """
    results = []
    env_path = ENV_PATH

    # 1. Check .env file & API Key
    load_dotenv(env_path, override=True)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key and api_key != "replace_with_your_own_key":
        results.append({
            "component": "Gemini API Key (.env)",
            "status": "OK",
            "details": "API key configured"
        })
    else:
        results.append({
            "component": "Gemini API Key (.env)",
            "status": "WARNING",
            "details": "Missing or placeholder GEMINI_API_KEY in .env. Set it in the Settings tab."
        })

    # 2. Check Microphone Device
    try:
        with open_microphone() as source:
            results.append({
                "component": "Microphone Device",
                "status": "OK",
                "details": f"Default input opened at {source.SAMPLE_RATE} Hz."
            })
    except Exception as e:
        results.append({
            "component": "Microphone Device",
            "status": "ERROR",
            "details": f"Microphone access error: {e}"
        })

    # 3. Check Windows SAPI Speech Engine
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voices = voice.GetVoices()
        outputs = voice.GetAudioOutputs().Count
        results.append({
            "component": "Windows Speech Output (SAPI)",
            "status": "OK" if voices.Count and outputs else "ERROR",
            "details": f"{voices.Count} voice(s), {outputs} audio output device(s) available."
        })
    except Exception as e:
        results.append({
            "component": "Windows Speech Output (SAPI)",
            "status": "ERROR",
            "details": f"TTS initialization failed: {e}"
        })

    # 4. Check Recordings Storage Folder
    rec_dir = RECORDINGS_DIR
    try:
        rec_dir.mkdir(exist_ok=True)
        results.append({
            "component": "Session Audio Storage",
            "status": "OK",
            "details": f"Directory ready at {rec_dir.name}/"
        })
    except Exception as e:
        results.append({
            "component": "Session Audio Storage",
            "status": "ERROR",
            "details": f"Cannot create recordings folder: {e}"
        })

    return results
