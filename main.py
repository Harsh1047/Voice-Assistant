from pathlib import Path
import speech_recognition as sr
from audio_processing import process_audio, record_audio, save_audio_pair


def main():
    try:
        print("Stay quiet for one second, then speak. Press Ctrl+C to cancel.")
        raw = record_audio()
        processed = sr.AudioData(process_audio(raw), 16000, 2)
        paths = save_audio_pair(raw, processed, Path(__file__).resolve().parent / "recordings")
        for path in paths:
            print(path)
    except (ValueError, OSError, sr.WaitTimeoutError) as error:
        print(f"Recording failed: {error}")
    except KeyboardInterrupt:
        print("Recording cancelled.")


if __name__ == "__main__":
    main()
