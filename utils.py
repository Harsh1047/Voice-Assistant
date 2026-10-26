import re
from math import gcd
import soundfile as sf
from scipy.signal import resample_poly
from audio_processing import process_samples


def clean_audio(file_path):
    samples, sample_rate = sf.read(file_path, dtype="float32", always_2d=True)
    samples = samples.mean(axis=1)
    if sample_rate != 16000:
        divisor = gcd(sample_rate, 16000)
        samples = resample_poly(samples, 16000 // divisor, sample_rate // divisor)
    return process_samples(samples)


def clean_text(transcript):
    text = re.sub(r"[^\w\s]", "", str(transcript).lower())
    return " ".join(text.split())
