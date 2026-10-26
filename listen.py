import speech_recognition as sr
from audio_processing import record_processed_audio


def transcribe(audio, language="en-IN"):
    recognizer = sr.Recognizer()
    recognizer.operation_timeout = 15
    return recognizer.recognize_google(audio, language=language)


def listen_with_recording(language="en-IN", recordings_dir=None, check_cancelled=None,
                          on_status=None, call=None):
    check = check_cancelled or (lambda: None)
    status = on_status or (lambda message: None)
    invoke = call or (lambda function, *args: function(*args))
    processed, audio_path = record_processed_audio(recordings_dir, check, status)
    check()
    status("Converting speech to text...")
    transcript = invoke(transcribe, processed, language)
    check()
    return transcript, audio_path


def listen(language="en-IN", recordings_dir=None):
    return listen_with_recording(language, recordings_dir)[0]


if __name__ == "__main__":
    try:
        print("Stay quiet for one second, then speak.")
        print("You said:", listen())
    except (sr.WaitTimeoutError, sr.UnknownValueError, sr.RequestError, ValueError, OSError) as error:
        print(f"Speech recognition failed: {error}")
    except KeyboardInterrupt:
        print("Recording cancelled.")
