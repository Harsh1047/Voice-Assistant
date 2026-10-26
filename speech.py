import locale
import threading
import pythoncom
import win32com.client
from text_cleaner import format_text_for_speech

_speech_lock = threading.Lock()


def available_voices(voice):
    voices = list(voice.GetVoices())
    for root in ("HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER"):
        try:
            category = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
            category.SetId(root + r"\SOFTWARE\Microsoft\Speech_OneCore\Voices", False)
            voices.extend(category.EnumerateTokens())
        except pythoncom.com_error:
            continue
    return voices


def select_voice(voices, language):
    matching = None
    for token in voices:
        try:
            codes = token.GetAttribute("Language").split(";")
            locales = [locale.windows_locale.get(int(code.strip(), 16), "").replace("_", "-").lower() for code in codes]
        except (ValueError, pythoncom.com_error):
            continue
        if language.lower() in locales:
            return token
        if any(code.split("-")[0] == language.split("-")[0] for code in locales):
            matching = token
    return matching


def speak(text, rate=0, volume=100, language=None, stop_event=None):
    text = format_text_for_speech(text)
    if not text:
        return True
    stop_event = stop_event or threading.Event()
    while not _speech_lock.acquire(timeout=0.05):
        if stop_event.is_set():
            return False
    voice = token = None
    initialized = False
    try:
        if stop_event.is_set():
            return False
        pythoncom.CoInitialize()
        initialized = True
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        if voice.GetAudioOutputs().Count == 0:
            raise OSError("No Windows audio output device is available. Connect speakers or headphones and check the default output.")
        if language:
            token = select_voice(available_voices(voice), language)
            if token is None:
                raise ValueError(f"No Windows text-to-speech voice is installed for {language}.")
            voice.Voice = token
        voice.Rate = max(-10, min(10, int(rate)))
        voice.Volume = max(0, min(100, int(volume)))
        if stop_event.is_set():
            return False
        voice.Speak(text, 1 | 16)
        while not voice.WaitUntilDone(50):
            if stop_event.is_set():
                return False
        return not stop_event.is_set()
    finally:
        try:
            if voice is not None and stop_event.is_set():
                voice.Speak("", 1 | 2)
        finally:
            voice = token = None
            if initialized:
                pythoncom.CoUninitialize()
            _speech_lock.release()


if __name__ == "__main__":
    speak("The voice assistant is ready.")
