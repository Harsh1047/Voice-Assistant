import os
import uuid
import threading
import winsound
import queue
from time import perf_counter
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import speech_recognition as sr
from dotenv import load_dotenv, set_key
from assistant import DEFAULT_MODEL, LANGUAGES, Conversation, get_response
from listen import listen_with_recording
from speech import speak
from database import ENV_PATH, RECORDINGS_DIR, SessionDatabase, resolve_audio_path
from startup_checks import run_startup_diagnostics


class RequestCancelled(Exception):
    pass


def check_cancelled(request):
    if request["stop"].is_set():
        raise RequestCancelled()


def cancellable_call(request, function, *args, **kwargs):
    """Discard a cancelled network result even if the HTTP call is still finishing."""
    check_cancelled(request)
    result = queue.Queue(maxsize=1)

    def run():
        try:
            check_cancelled(request)
            result.put((True, function(*args, **kwargs)))
        except Exception as error:
            result.put((False, error))

    threading.Thread(target=run, daemon=True).start()
    while not request["stop"].wait(0.05):
        try:
            succeeded, value = result.get_nowait()
        except queue.Empty:
            continue
        check_cancelled(request)
        if succeeded:
            return value
        raise value
    raise RequestCancelled()


class VoiceAssistantApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gemini Windows Voice Assistant")
        self.geometry("950x680")
        self.minsize(850, 600)

        # State & Modules
        self.db = SessionDatabase()
        self.session_id = datetime.now().strftime("sess_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
        self.is_recording = False
        self._request = None
        self._ui_events = queue.Queue()
        self.conversation = Conversation()

        # Load Configuration
        load_dotenv(ENV_PATH, override=True)
        self.api_key_var = tk.StringVar(value=os.getenv("GEMINI_API_KEY", "").strip())
        self.model_var = tk.StringVar(value=os.getenv("GEMINI_MODEL", DEFAULT_MODEL))
        self.lang_var = tk.StringVar(value="en-IN")
        self.tts_rate_var = tk.IntVar(value=0)
        self.tts_vol_var = tk.IntVar(value=100)
        self.auto_speak_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._run_checks_and_populate()
        self._refresh_history_table()
        self.after(50, self._drain_ui_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        # Top Header Bar
        header = ttk.Frame(self, padding=(15, 10))
        header.pack(fill=tk.X)

        ttk.Label(
            header,
            text="Gemini Windows Voice Assistant",
            font=("Segoe UI", 16, "bold")
        ).pack(side=tk.LEFT)

        status_frame = ttk.Frame(header)
        status_frame.pack(side=tk.RIGHT)
        ttk.Label(status_frame, text="Status:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            foreground="#0066cc"
        )
        self.status_label.pack(side=tk.LEFT)

        # Main Notebook (Tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.tab_assistant = ttk.Frame(self.notebook, padding=12)
        self.tab_history = ttk.Frame(self.notebook, padding=12)
        self.tab_settings = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.tab_assistant, text="  Voice Assistant  ")
        self.notebook.add(self.tab_history, text="  Session History & Playback  ")
        self.notebook.add(self.tab_settings, text="  Configuration & Startup Checks  ")

        self._build_assistant_tab()
        self._build_history_tab()
        self._build_settings_tab()

    # -------------------------------------------------------------------------
    # TAB 1: VOICE ASSISTANT INTERFACE
    # -------------------------------------------------------------------------
    def _build_assistant_tab(self):
        # Controls Row
        ctrl_frame = ttk.LabelFrame(self.tab_assistant, text="Voice & Session Controls", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_record = ttk.Button(
            ctrl_frame,
            text="Start Listening",
            command=self.start_listening_thread
        )
        self.btn_record.pack(side=tk.LEFT, padx=(0, 8), ipadx=10, ipady=4)

        self.btn_stop = ttk.Button(
            ctrl_frame,
            text="Stop",
            command=self.stop_listening,
            state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 15), ipadx=8, ipady=4)

        ttk.Checkbutton(
            ctrl_frame,
            text="Speak Responses Aloud",
            variable=self.auto_speak_var
        ).pack(side=tk.LEFT, padx=(0, 15))

        ttk.Button(
            ctrl_frame,
            text="New Conversation Session",
            command=self.reset_session
        ).pack(side=tk.RIGHT, ipadx=6, ipady=4)

        # Manual Text Input Row (Helpful for testing or quiet environments)
        input_frame = ttk.Frame(self.tab_assistant)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(input_frame, text="Or type a prompt:").pack(side=tk.LEFT, padx=(0, 8))
        self.text_input = ttk.Entry(input_frame, font=("Segoe UI", 10))
        self.text_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=3)
        self.text_input.bind("<Return>", lambda e: self.send_typed_message())

        ttk.Button(
            input_frame,
            text="Send",
            command=self.send_typed_message
        ).pack(side=tk.RIGHT, ipadx=8, ipady=3)

        # Transcript & Response Display
        display_frame = ttk.LabelFrame(self.tab_assistant, text="Live Transcript & Gemini Response Log", padding=8)
        display_frame.pack(fill=tk.BOTH, expand=True)

        self.chat_display = tk.Text(
            display_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            state=tk.DISABLED,
            bg="#fafafa",
            padx=10,
            pady=10
        )
        scrollbar = ttk.Scrollbar(display_frame, command=self.chat_display.yview)
        self.chat_display.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Text formatting tags
        self.chat_display.tag_configure("user", foreground="#004d99", font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_configure("assistant", foreground="#1b5e20", font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_configure("system", foreground="#666666", font=("Segoe UI", 9, "italic"))
        self.chat_display.tag_configure("error", foreground="#b71c1c", font=("Segoe UI", 10, "bold"))

        self._append_chat("System", f"Session {self.session_id} initialized. Click 'Start Listening' or type a command below.", "system")

    # -------------------------------------------------------------------------
    # TAB 2: SESSION HISTORY, PLAYBACK & EXPORT
    # -------------------------------------------------------------------------
    def _build_history_tab(self):
        toolbar = ttk.Frame(self.tab_history)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text="Play Selected Recording", command=self.play_selected_audio).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="Refresh", command=self._refresh_history_table).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="Export CSV", command=lambda: self.export_history("csv")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="Export JSON", command=lambda: self.export_history("json")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="Clear All History", command=self.clear_history).pack(side=tk.RIGHT)

        # Table of SQLite records
        headings = {
            "id": ("ID", 45),
            "timestamp": ("Timestamp", 135),
            "session_id": ("Session", 120),
            "transcript": ("User Transcript", 190),
            "response": ("Gemini Response", 220),
            "tool_called": ("Tool Used", 95),
            "latency_sec": ("Time (s)", 65),
            "audio_path": ("Audio File", 120)
        }
        self.history_tree = ttk.Treeview(self.tab_history, columns=tuple(headings), show="headings", height=14)
        for col, (title, width) in headings.items():
            self.history_tree.heading(col, text=title)
            self.history_tree.column(col, width=width, anchor=tk.W)

        tree_scroll = ttk.Scrollbar(self.tab_history, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=tree_scroll.set)

        self.history_tree.pack(fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.bind("<<TreeviewSelect>>", self._on_history_select)

        # Detailed Record Inspector
        detail_frame = ttk.LabelFrame(self.tab_history, text="Selected Record Details", padding=8)
        detail_frame.pack(fill=tk.X, pady=(10, 0))
        self.history_detail_text = tk.Text(detail_frame, height=5, wrap=tk.WORD, font=("Segoe UI", 9), state=tk.DISABLED)
        self.history_detail_text.pack(fill=tk.X)

    # -------------------------------------------------------------------------
    # TAB 3: CONFIGURATION & STARTUP DIAGNOSTICS
    # -------------------------------------------------------------------------
    def _build_settings_tab(self):
        config_frame = ttk.LabelFrame(self.tab_settings, text="Application & Model Configuration", padding=12)
        config_frame.pack(fill=tk.X, pady=(0, 12))

        # Grid Settings
        ttk.Label(config_frame, text="Gemini API Key:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        api_entry = ttk.Entry(config_frame, textvariable=self.api_key_var, width=48, show="*")
        api_entry.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Button(config_frame, text="Save Key to .env", command=self.save_api_key).grid(row=0, column=2, padx=8, pady=5)

        ttk.Label(config_frame, text="Gemini Model:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=5)
        model_combo = ttk.Combobox(
            config_frame,
            textvariable=self.model_var,
            values=[DEFAULT_MODEL],
            width=30
        )
        model_combo.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)

        ttk.Label(config_frame, text="Input & Response Language:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=5)
        lang_combo = ttk.Combobox(
            config_frame,
            textvariable=self.lang_var,
            values=list(LANGUAGES),
            state="readonly",
            width=30
        )
        lang_combo.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)

        ttk.Label(config_frame, text="Speech Rate (-5 to +5):").grid(row=3, column=0, sticky=tk.W, pady=5, padx=5)
        rate_scale = tk.Scale(config_frame, from_=-5, to=5, orient=tk.HORIZONTAL, variable=self.tts_rate_var, length=200)
        rate_scale.grid(row=3, column=1, sticky=tk.W, padx=5)

        ttk.Label(config_frame, text="Speech Volume (0 to 100):").grid(row=4, column=0, sticky=tk.W, pady=5, padx=5)
        vol_scale = tk.Scale(config_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.tts_vol_var, length=200)
        vol_scale.grid(row=4, column=1, sticky=tk.W, padx=5)

        # Startup Diagnostics Section
        diag_frame = ttk.LabelFrame(self.tab_settings, text="Startup Hardware & Configuration Checks", padding=12)
        diag_frame.pack(fill=tk.BOTH, expand=True)

        btn_bar = ttk.Frame(diag_frame)
        btn_bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(btn_bar, text="Re-run System Checks", command=self._run_checks_and_populate).pack(side=tk.LEFT)

        cols = ("component", "status", "details")
        self.diag_tree = ttk.Treeview(diag_frame, columns=cols, show="headings", height=6)
        self.diag_tree.heading("component", text="System Component")
        self.diag_tree.heading("status", text="Status")
        self.diag_tree.heading("details", text="Diagnostic Details")

        self.diag_tree.column("component", width=210)
        self.diag_tree.column("status", width=90)
        self.diag_tree.column("details", width=550)
        self.diag_tree.pack(fill=tk.BOTH, expand=True)

    # -------------------------------------------------------------------------
    # LOGIC: STARTUP CHECKS & SETTINGS
    # -------------------------------------------------------------------------
    def _run_checks_and_populate(self):
        for item in self.diag_tree.get_children():
            self.diag_tree.delete(item)
        results = run_startup_diagnostics()
        for res in results:
            self.diag_tree.insert("", tk.END, values=(res["component"], res["status"], res["details"]))

    def save_api_key(self):
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("Missing Key", "Please enter a valid Gemini API key.")
            return
        if not ENV_PATH.exists():
            ENV_PATH.write_text(f"GEMINI_API_KEY={key}\n", encoding="utf-8")
        else:
            set_key(str(ENV_PATH), "GEMINI_API_KEY", key)
        os.environ["GEMINI_API_KEY"] = key
        self._run_checks_and_populate()
        messagebox.showinfo("Saved", "GEMINI_API_KEY saved to .env and updated for this session.")

    # -------------------------------------------------------------------------
    # LOGIC: RECORDING, SPEECH-TO-TEXT, GEMINI API, TOOLS & TTS
    # -------------------------------------------------------------------------
    def _append_chat(self, sender, message, tag="user"):
        self.chat_display.configure(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_display.insert(tk.END, f"[{timestamp}] {sender}: ", tag)
        self.chat_display.insert(tk.END, f"{message}\n\n")
        self.chat_display.see(tk.END)
        self.chat_display.configure(state=tk.DISABLED)

    def _set_status(self, text):
        self.status_var.set(text)

    def reset_session(self):
        self.stop_listening()
        self.session_id = datetime.now().strftime("sess_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
        self.conversation.clear()
        self._append_chat("System", f"Started new session: {self.session_id}", "system")

    def start_listening_thread(self):
        self._start_request(None)

    def stop_listening(self):
        winsound.PlaySound(None, 0)
        if self._request is not None:
            self._request["stop"].set()
            self._set_status("Stopping...")
        else:
            self._set_status("Stopped")
        self.btn_stop.configure(state=tk.DISABLED)

    def send_typed_message(self):
        text = self.text_input.get().strip()
        if not text or self.is_recording:
            return
        self.text_input.delete(0, tk.END)
        self._start_request(text)

    def _start_request(self, text):
        if self.is_recording:
            return
        # Snapshot Tk settings on the UI thread; workers never read Tk variables.
        request = {
            "stop": threading.Event(), "language": self.lang_var.get(),
            "api_key": self.api_key_var.get().strip(), "model": self.model_var.get().strip(),
            "rate": self.tts_rate_var.get(), "volume": self.tts_vol_var.get(),
            "speak": self.auto_speak_var.get(), "session": self.session_id,
            "history": self.conversation.snapshot()
        }
        self._request = request
        self.is_recording = True
        self.btn_record.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        threading.Thread(target=self._request_worker, args=(request, text), daemon=True).start()

    def _post(self, request, callback, *args):
        self._ui_events.put((request, callback, args))

    def _drain_ui_events(self):
        try:
            while True:
                request, callback, args = self._ui_events.get_nowait()
                if request is self._request:
                    if callback == self._finish_request or not request["stop"].is_set():
                        callback(*args)
        except queue.Empty:
            pass
        finally:
            self.after(50, self._drain_ui_events)

    def _finish_request(self, request):
        self.is_recording = False
        self._request = None
        self._set_status("Stopped" if request["stop"].is_set() else "Ready")
        self.btn_record.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)

    def _close(self):
        self.stop_listening()
        self.destroy()

    def _request_worker(self, request, text):
        try:
            check_cancelled(request)
            audio_path = None
            if text is None:
                text, audio_path = self._voice_pipeline_worker(request)
            self._process_query_worker(request, text, audio_path)
        except RequestCancelled:
            pass
        except sr.WaitTimeoutError:
            self._post(request, self._append_chat, "System", "No speech detected (timeout).", "system")
        except sr.UnknownValueError:
            self._post(request, self._append_chat, "System", "Could not understand audio. Please try again.", "error")
        except sr.RequestError as e:
            self._post(request, self._append_chat, "Error", f"Speech recognition service unavailable: {e}", "error")
        except Exception as e:
            error = str(e)
            if request["api_key"]:
                error = error.replace(request["api_key"], "[REDACTED]")
            self._post(request, self._append_chat, "Error", error, "error")
        finally:
            self._post(request, self._finish_request, request)

    def _voice_pipeline_worker(self, request):
        return listen_with_recording(
            language=request["language"], recordings_dir=RECORDINGS_DIR,
            check_cancelled=lambda: check_cancelled(request),
            on_status=lambda message: self._post(request, self._set_status, message),
            call=lambda function, *args: cancellable_call(request, function, *args),
        )

    def _process_query_worker(self, request, transcript, audio_path):
        check_cancelled(request)
        self._post(request, self._append_chat, "You", transcript, "user")
        self._post(request, self._set_status, "Querying Gemini...")
        start_t = perf_counter()
        answer, tool_used = self._call_gemini_with_tools(request, transcript)
        check_cancelled(request)
        self._post(request, self._save_response, request, transcript, answer, tool_used, audio_path, perf_counter() - start_t)
        if request["speak"]:
            self._post(request, self._set_status, "Speaking response...")
            self._speak_in_thread(request, answer)

    def _save_response(self, request, transcript, answer, tool_used, audio_path, elapsed):
        self.conversation.add(transcript, answer)
        self._append_chat("Assistant", f"{answer}  ({elapsed:.1f}s)", "assistant")
        self.db.add_record(
            session_id=request["session"], transcript=transcript, response=answer,
            tool_called=tool_used, audio_path=audio_path, latency_sec=elapsed
        )
        self._refresh_history_table()

    def _call_gemini_with_tools(self, request, user_text):
        return get_response(
            user_text, request["api_key"], model=request["model"],
            history=request["history"], language=request["language"],
            call=lambda function: cancellable_call(request, function),
            check_cancelled=lambda: check_cancelled(request),
        )

    def _speak_in_thread(self, request, text):
        check_cancelled(request)
        try:
            speak(text, rate=request["rate"], volume=request["volume"],
                  language=request["language"], stop_event=request["stop"])
        except Exception as error:
            self._post(request, self._append_chat, "Error", f"Speech playback failed: {error}", "error")
        check_cancelled(request)

    def _refresh_history_table(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for row in self.db.get_all_records():
            values = tuple(row[column] for column in self.history_tree["columns"])
            self.history_tree.insert("", tk.END, values=values)

    def _on_history_select(self, event):
        selected = self.history_tree.selection()
        if not selected:
            return
        vals = self.history_tree.item(selected[0], "values")
        detail = (
            f"Record #{vals[0]} | Timestamp: {vals[1]} | Session: {vals[2]} | Tool: {vals[5]} | Latency: {vals[6]}s\n"
            f"User Said: {vals[3]}\n"
            f"Assistant Replied: {vals[4]}\n"
            f"Audio File: {vals[7] or 'Text input (No audio file)'}"
        )
        self.history_detail_text.configure(state=tk.NORMAL)
        self.history_detail_text.delete("1.0", tk.END)
        self.history_detail_text.insert(tk.END, detail)
        self.history_detail_text.configure(state=tk.DISABLED)

    def play_selected_audio(self):
        selected = self.history_tree.selection()
        if not selected:
            messagebox.showinfo("Select Record", "Please select a conversation row first.")
            return
        audio_path = resolve_audio_path(self.history_tree.item(selected[0], "values")[7])
        if audio_path is None:
            messagebox.showwarning("No Audio Recording", "No saved WAV recording exists for this entry.")
            return
        winsound.PlaySound(str(audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        self.btn_stop.configure(state=tk.NORMAL)

    def export_history(self, file_format):
        exporters = {"csv": self.db.export_to_csv, "json": self.db.export_to_json}
        path = filedialog.asksaveasfilename(
            defaultextension=f".{file_format}",
            filetypes=[(f"{file_format.upper()} Files", f"*.{file_format}")],
            initialfile=f"session_history.{file_format}"
        )
        if path:
            if exporters[file_format](path):
                messagebox.showinfo("Export Complete", f"Session history exported to:\n{path}")
            else:
                messagebox.showwarning("Empty History", "No records available to export.")

    def clear_history(self):
        if messagebox.askyesno("Confirm Clear", "Delete all saved session records from SQLite?"):
            self.db.clear_history()
            self._refresh_history_table()


if __name__ == "__main__":
    app = VoiceAssistantApp()
    app.mainloop()
