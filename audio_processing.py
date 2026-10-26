from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
import uuid

import numpy as np
import noisereduce as nr
import speech_recognition as sr

SAMPLE_RATE = 16000


class InvalidAudioError(ValueError):
    pass


@contextmanager
def open_microphone():
    source = sr.Microphone()
    source.__enter__()
    if source.stream is None:
        raise OSError(
            "Cannot open the default microphone. Check Windows microphone permissions, "
            "the selected input device, and whether another application is using it."
        )
    try:
        yield source
    finally:
        source.__exit__(None, None, None)


def process_samples(samples):
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim != 1 or samples.size < 1280 or not np.isfinite(samples).all():
        raise InvalidAudioError("Recording is empty, too short, or invalid.")
    if np.sqrt(np.mean(samples ** 2)) < 0.001:
        raise InvalidAudioError("Recording is silent or too quiet. Please speak closer to the microphone.")
    reduced = nr.reduce_noise(y=samples, sr=SAMPLE_RATE, prop_decrease=0.5)
    if not np.isfinite(reduced).all():
        raise InvalidAudioError("Audio processing failed. Please record again.")
    frame_size = 320
    padded = np.pad(reduced, (0, (-len(reduced)) % frame_size))
    levels = np.sqrt(np.mean(padded.reshape(-1, frame_size) ** 2, axis=1))
    active = np.flatnonzero(levels >= max(0.001, float(levels.max()) * 0.04))
    if not active.size:
        raise InvalidAudioError("No usable audio remains after processing.")
    start = max(0, int(active[0]) * frame_size - 1280)
    end = min(len(reduced), (int(active[-1]) + 1) * frame_size + 1280)
    reduced = reduced[start:end]
    gain = min(4.0, 0.9 / float(np.max(np.abs(reduced))))
    return np.clip(reduced * gain, -0.9, 0.9).astype(np.float32)


def process_audio(audio):
    raw = audio.get_raw_data(convert_rate=SAMPLE_RATE, convert_width=2)
    if len(raw) % 2:
        raise InvalidAudioError("Recording contains incomplete audio samples.")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return (process_samples(samples) * 32767).astype("<i2").tobytes()


def save_audio_pair(raw_audio, processed_audio, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
    raw_path = directory / f"{name}_raw.wav"
    processed_path = directory / f"{name}_processed.wav"
    raw_path.write_bytes(raw_audio.get_wav_data(convert_rate=SAMPLE_RATE, convert_width=2))
    processed_path.write_bytes(processed_audio.get_wav_data(convert_rate=SAMPLE_RATE, convert_width=2))
    return raw_path, processed_path


def record_processed_audio(directory=None, check_cancelled=None, on_status=None):
    check = check_cancelled or (lambda: None)
    status = on_status or (lambda message: None)
    directory = directory if directory is not None else Path(__file__).resolve().parent / "recordings"
    check()
    status("Listening... Stay quiet for calibration, then speak.")
    raw = record_audio(check_cancelled=check)
    check()
    status("Cleaning audio...")
    processed = sr.AudioData(process_audio(raw), SAMPLE_RATE, 2)
    check()
    _, audio_path = save_audio_pair(raw, processed, directory)
    check()
    return processed, audio_path


def record_audio(recognizer=None, check_cancelled=None, calibrate=True):
    recognizer = recognizer or sr.Recognizer()
    check = check_cancelled or (lambda: None)

    class CheckedStream:
        def __init__(self, stream):
            self.stream = stream

        def read(self, size):
            check()
            data = self.stream.read(size)
            check()
            return data

        def close(self):
            self.stream.close()

    check()
    with open_microphone() as source:
        source.stream = CheckedStream(source.stream)
        if calibrate:
            recognizer.adjust_for_ambient_noise(source, duration=1)
        audio = recognizer.listen(source, timeout=10, phrase_time_limit=12)
    check()
    return audio
