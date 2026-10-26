import argparse
from datetime import datetime
from pathlib import Path
from time import perf_counter
import speech_recognition as sr

ROOT = Path(__file__).resolve().parent

from audio_processing import process_audio, record_audio, save_audio_pair
from listen import transcribe
from evaluation import evaluate_transcripts, save_result


def timed_transcription(audio):
    start = perf_counter()
    try:
        return transcribe(audio), perf_counter() - start, None
    except (sr.UnknownValueError, sr.RequestError, OSError) as error:
        return "", perf_counter() - start, f"{type(error).__name__}: {error}"


def benchmark(raw, reference):
    start = perf_counter()
    processed = sr.AudioData(process_audio(raw), 16000, 2)
    processing_time = perf_counter() - start
    paths = save_audio_pair(raw, processed, ROOT / "recordings")
    raw_text, raw_time, raw_error = timed_transcription(raw)
    processed_text, processed_time, processed_error = timed_transcription(processed)
    result = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "raw_transcript": raw_text, "processed_transcript": processed_text,
        "processing_seconds": round(processing_time, 3),
        "raw_recognition_seconds": round(raw_time, 3),
        "processed_recognition_seconds": round(processed_time, 3),
        "raw_error": raw_error, "processed_error": processed_error,
        "raw_audio": str(paths[0]), "processed_audio": str(paths[1]),
    }
    result.update(evaluate_transcripts(reference, raw_text, processed_text))
    if raw_error:
        result["raw_wer"] = None
    if processed_error:
        result["processed_wer"] = None
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--reference")
    args = parser.parse_args()
    reference = args.reference or input("Sentence you will say: ").strip()
    if not reference.strip():
        parser.error("A non-empty reference sentence is required.")
    try:
        if args.audio:
            with sr.AudioFile(str(args.audio)) as source:
                raw = sr.Recognizer().record(source)
        else:
            print("Stay quiet for one second, then say the sentence. Ctrl+C cancels.")
            raw = record_audio()
        result = benchmark(raw, reference)
    except (ValueError, OSError, sr.WaitTimeoutError) as error:
        result = {"reference": reference, "error": f"{type(error).__name__}: {error}"}
    except KeyboardInterrupt:
        print("Recording cancelled.")
        return
    print(result)
    print(save_result(result))


if __name__ == "__main__":
    main()
