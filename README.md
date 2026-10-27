# 🎙️ Gemini Windows Voice Assistant

A Python-based desktop voice assistant for Windows that integrates speech recognition, pretrained **Google Gemini AI** models, automated Windows system actions (function calling), and native Windows SAPI speech synthesis. 

Built with a complete graphical user interface (GUI), SQLite session persistence, audio recording playback, automated hardware diagnostics, and standalone executable packaging.

---

## 🏗️ System Architecture & Pipeline

The application follows a modular end-to-end voice interaction pipeline:

```text
Voice Input (Mic) ➔ Record & Calibrate Audio ➔ Speech-to-Text ➔ Gemini AI (+ Windows Tools) ➔ Response Text & SQLite Storage ➔ Windows SAPI Voice Output
```

### Engineering Approach
* **Pretrained AI Integration:** This assistant integrates Google's pretrained Gemini models (`google-genai`) for natural language understanding and tool-calling, paired with Google Web Speech Recognition for speech-to-text conversion.
* **Experimental Model Benchmarking:** The repository also includes an offline `Data Analysis` experiment (TF-IDF + Logistic Regression in `train_model.py` and audio-cleaning pipelines) whose recordings and transcripts serve as a benchmark test dataset for evaluating transcription accuracy and response quality.

---

## ✨ Key Features

* **Desktop GUI (`app_gui.py`):** Clean multi-tab Windows interface with Start/Stop recording controls, live status updates, manual text input fallback, and a color-coded conversation log.
* **Multi-Turn Conversation Memory:** Remembers context across follow-up questions within a session and allows one-click session resets.
* **Windows Function Calling (`windows_tools.py`):** Safely triggers local Windows tools—such as launching **Notepad**, **Calculator**, or **Google Browser**—only when explicitly requested by the user.
* **SQLite Session History & Audio Playback (`database.py`):** Automatically logs every conversation turn, latency timing, and tool execution to `assistant_history.db`, saves `.wav` recordings to `recordings/`, and supports one-click audio replay and **CSV / JSON export**.
* **Automated Startup Diagnostics (`startup_checks.py`):** Pre-flight checks on launch to verify `.env` API key configuration, microphone hardware availability, Windows SAPI voices, and storage permissions.
* **Standalone Windows Packaging (`build_executable.py`):** Packages the entire Python setup into a distributable `.exe` application via PyInstaller that runs outside the development environment.

---

## 👥 Team Roles & Module Ownership

| Member | Role Title | Responsibilities & Modules |
| :--- | :--- | :--- |
| **Member 1** | **Audio Capture & Preprocessing Developer** | Microphone input handling, ambient noise calibration, timeout management, saving raw `.wav` recordings with timestamps (`listen.py`, `recordings/`). |
| **Member 2** | **Speech Recognition & Gemini Integration Developer** | Speech-to-text conversion, Gemini API integration, function-calling logic (`windows_tools.py`), conversation memory, and error handling (`assistant.py`, `gemini_test.py`). |
| **Member 3** | **Speech Synthesis & Evaluation Developer** | Windows SAPI text-to-speech engine (`speech.py`), Markdown formatting cleanup, adjustable speech rate/volume settings, and transcription/latency evaluation. |
| **Member 4** | **Application Integration & Deployment Developer** | Desktop GUI (`app_gui.py`), module integration, SQLite session storage & CSV/JSON export (`database.py`), hardware startup diagnostics (`startup_checks.py`), and `.exe` packaging (`build_executable.py`). |

---

## 📂 Project Directory Structure

```text
├── app_gui.py               # Main Windows Desktop GUI application (Member 4)
├── database.py              # SQLite session storage and CSV/JSON export module (Member 4)
├── startup_checks.py        # Pre-launch configuration and hardware diagnostics (Member 4)
├── build_executable.py      # PyInstaller packaging script for standalone .exe delivery (Member 4)
├── listen.py                # Microphone calibration and speech-to-text module (Member 1)
├── assistant.py             # CLI Gemini API and tool-calling module (Member 2)
├── gemini_test.py           # CLI end-to-end voice assistant loop with latency timers (Member 2)
├── windows_tools.py         # Local Windows actions: Notepad, Calculator, Browser (Member 2)
├── speech.py                # Windows SAPI Text-to-Speech output module (Member 3)
├── voice_demo.py            # Rule-based voice command prototype
├── requirements.txt         # Required Python dependencies
├── .env                     # Private environment variables (GEMINI_API_KEY)
├── .gitignore               # Git exclusions (.venv, __pycache__, .env)
├── Setup.txt                # Quick-start notes
├── recordings/              # Saved session .wav audio files (auto-created)
└── Data Analysis/           # Offline TF-IDF/Logistic Regression experiment & test dataset
```

---

## ⚙️ Prerequisites & Installation

### 1. System Requirements
* **OS:** Windows 10 or Windows 11 (required for `pywin32` SAPI speech and Windows tools)
* **Python:** Python 3.10 or newer
* **Hardware:** Working Microphone, Speakers/Headphones, and an active Internet connection

### 2. Install Dependencies
Open a terminal (PowerShell or Command Prompt) in the project root folder and run:

```powershell
python -m pip install -r requirements.txt
```

*(Note: If you also want to run the offline experiment inside the `Data Analysis` folder, install `pandas` and `scikit-learn` via `pip install pandas scikit-learn`.)*

### 3. Configure Your Gemini API Key
Open the `.env` file in the root directory and replace the placeholder with your Google Gemini API key:

```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```
*(Alternatively, you can paste and save your API key directly inside the **Configuration & Startup Checks** tab of the desktop GUI.)*

---

## 🚀 Usage Guide

### Option A: Launch the Full Desktop Application (Recommended)
Run the integrated GUI application:

```powershell
python app_gui.py
```
1. **Voice Assistant Tab:** Click **🎤 Start Listening** and speak a question (e.g., *"Explain Python lists in two sentences"*) or a system command (e.g., *"Open Calculator"*, *"Open Notepad"*, or *"Open Google"*). You can also type prompts directly into the text bar.
2. **Session History & Playback Tab:** Browse past interactions stored in SQLite, click **▶ Play Selected Recording** to listen to captured `.wav` audio, or click **📥 Export CSV / JSON** to save reports.
3. **Configuration & Startup Checks Tab:** Switch Gemini models, change recognition language (`en-IN`, `en-US`, etc.), adjust speech speed/volume sliders, or re-run hardware diagnostics.

### Option B: Run Individual CLI Modules (For Testing)
* **Test Voice-to-Gemini CLI Loop:**
  ```powershell
  python gemini_test.py
  ```
* **Test Text-to-Gemini CLI with Tools:**
  ```powershell
  python assistant.py
  ```
* **Test Microphone & STT Only:**
  ```powershell
  python listen.py
  ```
* **Test Windows SAPI Text-to-Speech Only:**
  ```powershell
  python speech.py
  ```

---

## 📦 Packaging as a Standalone Windows `.exe`

To build a standalone Windows application that runs outside of your Python development environment:

```powershell
python build_executable.py
```

Once the build finishes, navigate to:
```text
dist/GeminiVoiceAssistant/GeminiVoiceAssistant.exe
```
You can zip and distribute the `dist/GeminiVoiceAssistant` folder to run the assistant on another Windows PC.

---

## 🛠️ Troubleshooting

* **"Missing or placeholder GEMINI_API_KEY":** Ensure `.env` exists in the project folder and contains a valid key from Google AI Studio, or save it via the GUI Settings tab.
* **"No speech detected":** Check the **Configuration & Startup Checks** tab to verify your default microphone is detected. Stay quiet during the 1-second ambient noise calibration before speaking.
* **PyAudio Installation Issues:** Because `requirements.txt` uses `SpeechRecognition[audio]`, `pip` will automatically pull precompiled `PyAudio` wheels for Windows. Ensure you are running Python 3.10+.
