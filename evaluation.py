import json
import re
from pathlib import Path
from jiwer import wer


def normalize_transcript(text):
    return " ".join(re.sub(r"[^\w\s]", "", str(text).lower()).split())


def evaluate_transcripts(reference, raw_text, processed_text):
    reference = normalize_transcript(reference)
    if not reference:
        raise ValueError("Enter a non-empty reference sentence.")
    return {
        "reference": reference,
        "raw_wer": wer(reference, normalize_transcript(raw_text)),
        "processed_wer": wer(reference, normalize_transcript(processed_text)),
    }


def save_result(result, path=None):
    path = Path(path) if path is not None else Path(__file__).with_name("audio_report.json")
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    records.append(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    result = evaluate_transcripts(input("Reference: "), input("Raw transcript: "), input("Processed transcript: "))
    print(json.dumps(result, indent=2))
    print(save_result(result))
