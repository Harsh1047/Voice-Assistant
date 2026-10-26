from pathlib import Path
import pandas as pd
import soundfile as sf
from utils import clean_audio, clean_text


def run_pipeline(base_dir=None):
    base = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    processed_dir = base / "processed_data"
    processed_dir.mkdir(parents=True, exist_ok=True)
    metadata = pd.read_csv(base / "rawdata" / "metadata.csv")
    records = []
    for _, row in metadata.iterrows():
        source = base / "rawdata" / row["file_name"]
        try:
            samples = clean_audio(source)
            filename = f"clean_{source.stem}.wav"
            sf.write(processed_dir / filename, samples, 16000, subtype="PCM_16")
            records.append({"file_name": filename, "clean_transcript": clean_text(row["raw_transcript"])})
            print(f"Processed: {filename}")
        except (ValueError, OSError, RuntimeError) as error:
            print(f"Skipped {source.name}: {error}")
    pd.DataFrame(records, columns=["file_name", "clean_transcript"]).to_csv(
        processed_dir / "train_manifest.csv", index=False
    )
    return records


if __name__ == "__main__":
    run_pipeline()
