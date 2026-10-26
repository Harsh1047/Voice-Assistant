import importlib.util
import subprocess
import sys
from pathlib import Path


def build_app():
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError("Install the build dependency: python -m pip install pyinstaller")
    folder = Path(__file__).resolve().parent
    build_dir = folder / "build"
    build_dir.mkdir(exist_ok=True)
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
        "--name", "GeminiVoiceAssistant", "--hidden-import", "win32timezone",
        "--collect-all", "noisereduce",
        "--distpath", str(folder / "dist"), "--workpath", str(build_dir),
        "--specpath", str(build_dir),
    ]
    cmd.append(str(folder / "app_gui.py"))
    subprocess.run(cmd, cwd=folder, check=True)
    destination = folder / "dist" / "GeminiVoiceAssistant"
    env_path = destination / ".env"
    if not env_path.exists():
        env_path.write_text("GEMINI_API_KEY=\nGEMINI_MODEL=gemini-2.5-flash\n", encoding="utf-8")
    (destination / "recordings").mkdir(exist_ok=True)
    print(destination / "GeminiVoiceAssistant.exe")


if __name__ == "__main__":
    build_app()
