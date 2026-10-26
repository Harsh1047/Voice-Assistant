import ast
import importlib
import json
import shutil
import sqlite3
import threading
import unittest
import uuid
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import soundfile as sf
import speech_recognition as sr

import app_gui
import assistant
import audio_processing
import benchmark
import database
import evaluation
import listen
import pipeline
import speech
from text_cleaner import format_text_for_speech


ROOT = Path(__file__).resolve().parent


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = ROOT / "test_outputs" / uuid.uuid4().hex[:10]
        cls.output.mkdir(parents=True)
        samples = (6000 * np.sin(2 * np.pi * 440 * np.arange(16000) / 16000)).astype("<i2")
        cls.raw = sr.AudioData(samples.tobytes(), 16000, 2)

    def test_all_modules_import_and_parse(self):
        names = ["app_gui", "assistant", "audio_processing", "benchmark", "build_executable",
                 "database", "evaluation", "listen", "main", "pipeline", "speech",
                 "startup_checks", "text_cleaner", "utils", "windows_tools"]
        for name in names:
            with self.subTest(module=name):
                path = ROOT / (name + ".py")
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                module = importlib.import_module(name)
                self.assertEqual(Path(module.__file__).resolve(), path)

    def test_invalid_audio_rejected_without_warnings(self):
        cases = [np.array([], dtype="<i2"), np.zeros(16000, dtype="<i2"),
                 np.random.default_rng(42).integers(-2, 3, 16000, dtype=np.int16)]
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            for samples in cases:
                with self.subTest(size=len(samples)), self.assertRaises(audio_processing.InvalidAudioError):
                    audio_processing.process_audio(sr.AudioData(samples.tobytes(), 16000, 2))

    def test_audio_trim_volume_and_wav_files(self):
        raw = sr.AudioData(b"\0\0" * 16000 + self.raw.frame_data + b"\0\0" * 16000, 16000, 2)
        output = audio_processing.process_audio(raw)
        samples = np.frombuffer(output, dtype="<i2")
        self.assertLess(len(samples), 48000)
        self.assertGreaterEqual(len(samples), 16000)
        self.assertLessEqual(np.max(np.abs(samples.astype(np.int32))), 29491)
        paths = audio_processing.save_audio_pair(raw, sr.AudioData(output, 16000, 2), self.output / "recordings")
        for path in paths:
            info = sf.info(path)
            self.assertEqual((info.samplerate, info.channels, info.subtype), (16000, 1, "PCM_16"))

    def test_recording_to_transcription_connection(self):
        statuses = []
        with patch.object(audio_processing, "record_audio", return_value=self.raw), patch.object(listen, "transcribe", return_value="hello") as transcriber:
            transcript, path = listen.listen_with_recording(recordings_dir=self.output / "recordings", on_status=statuses.append)
        self.assertEqual(transcript, "hello")
        self.assertTrue(path.is_file())
        self.assertEqual(transcriber.call_args.args[0].sample_rate, 16000)
        self.assertEqual(len(statuses), 3)

    def test_failed_microphone_has_useful_error(self):
        source = MagicMock(stream=None)
        with patch.object(audio_processing.sr, "Microphone", return_value=source):
            with self.assertRaisesRegex(OSError, "Cannot open the default microphone"):
                with audio_processing.open_microphone():
                    self.fail("Unavailable microphone accepted")
        source.__exit__.assert_not_called()

    def test_cancel_before_recording(self):
        stop = threading.Event()
        stop.set()
        with patch.object(audio_processing, "record_audio") as recorder:
            with self.assertRaises(app_gui.RequestCancelled):
                listen.listen_with_recording(check_cancelled=lambda: app_gui.check_cancelled({"stop": stop}))
        recorder.assert_not_called()

    def test_cancel_network_wait(self):
        stop, started, release = threading.Event(), threading.Event(), threading.Event()
        def slow_call():
            started.set()
            release.wait(2)
            return "late result"
        timer = threading.Timer(0.1, stop.set)
        timer.start()
        try:
            with self.assertRaises(app_gui.RequestCancelled):
                app_gui.cancellable_call({"stop": stop}, slow_call)
            self.assertTrue(started.is_set())
        finally:
            release.set()
            timer.cancel()

    def test_conversation_and_backend(self):
        history = assistant.Conversation()
        for index in range(8):
            history.add(str(index), "answer")
        self.assertEqual(len(history.snapshot()), 5)
        snapshot = history.snapshot()
        snapshot.clear()
        self.assertEqual(len(history.snapshot()), 5)
        with patch.object(assistant.genai, "Client") as client:
            generate = client.return_value.__enter__.return_value.models.generate_content
            generate.return_value = SimpleNamespace(function_calls=None, text="response")
            self.assertEqual(assistant.get_response("hello", "test-key", history=history.snapshot()), ("response", "None"))
            self.assertEqual(len(generate.call_args.kwargs["contents"]), 11)
        history.clear()
        self.assertEqual(history.snapshot(), [])

    def test_tools_dispatch_without_launching_apps(self):
        action = Mock(return_value="Done")
        with patch.object(assistant.genai, "Client") as client, patch.dict(assistant.TOOLS, {"test_action": action}):
            generate = client.return_value.__enter__.return_value.models.generate_content
            generate.return_value = SimpleNamespace(function_calls=[SimpleNamespace(name="test_action", args={})], text=None)
            self.assertEqual(assistant.get_response("run", "test-key"), ("Done", "test_action"))
            action.assert_called_once_with()
            generate.return_value = SimpleNamespace(function_calls=[SimpleNamespace(name="missing", args={})], text=None)
            self.assertEqual(assistant.get_response("run", "test-key")[1], "None")

    def test_speech_format_settings_and_cancellation(self):
        self.assertEqual(format_text_for_speech("### Hello **world**\n- [Open](https://example.com) `code`"), "Hello world Open code")
        voice = Mock()
        voice.GetAudioOutputs.return_value.Count = 1
        voice.WaitUntilDone.return_value = True
        with patch.object(speech.pythoncom, "CoInitialize"), patch.object(speech.pythoncom, "CoUninitialize"), patch.object(speech.win32com.client, "Dispatch", return_value=voice):
            self.assertTrue(speech.speak("**Hello**", rate=2, volume=75))
            voice.Speak.assert_called_with("Hello", 17)
            self.assertEqual((voice.Rate, voice.Volume), (2, 75))
            stop = threading.Event()
            def interrupted(_):
                stop.set()
                return False
            voice.WaitUntilDone.side_effect = interrupted
            self.assertFalse(speech.speak("Hello again", stop_event=stop))
            voice.Speak.assert_called_with("", 3)

    def test_no_audio_output_is_reported(self):
        voice = Mock()
        voice.GetAudioOutputs.return_value.Count = 0
        with patch.object(speech.pythoncom, "CoInitialize"), patch.object(speech.pythoncom, "CoUninitialize"), patch.object(speech.win32com.client, "Dispatch", return_value=voice):
            with self.assertRaisesRegex(OSError, "No Windows audio output"):
                speech.speak("Hello")

    def test_evaluation_and_report(self):
        result = evaluation.evaluate_transcripts("Open the calculator.", "open calculator", "Open the calculator!")
        self.assertGreater(result["raw_wer"], 0)
        self.assertEqual(result["processed_wer"], 0)
        path = evaluation.save_result(result, self.output / "evaluation.json")
        evaluation.save_result(result, path)
        self.assertEqual(len(json.loads(path.read_text())), 2)

    def test_database_exports_and_portable_paths(self):
        db = database.SessionDatabase(self.output / "history.db")
        self.assertFalse(db.export_to_json(self.output / "empty.json"))
        path = self.output / "recordings" / "example.wav"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(self.raw.get_wav_data())
        db.add_record("test", "hello", "response", audio_path=path)
        record = db.get_all_records()[0]
        self.assertFalse(Path(record["audio_path"]).is_absolute())
        self.assertEqual(database.resolve_audio_path(record["audio_path"]), path)
        self.assertTrue(db.export_to_csv(self.output / "history.csv"))
        self.assertTrue(db.export_to_json(self.output / "history.json"))

    def test_batch_preprocessing(self):
        base = self.output / "batch"
        shutil.copytree(ROOT / "rawdata", base / "rawdata")
        records = pipeline.run_pipeline(base)
        self.assertEqual(len(records), 4)
        for row in records:
            info = sf.info(base / "processed_data" / row["file_name"])
            self.assertEqual((info.samplerate, info.channels, info.subtype), (16000, 1, "PCM_16"))

    def test_benchmark_connections(self):
        with patch.object(benchmark, "ROOT", self.output), patch.object(benchmark, "transcribe", side_effect=["open calculator", "open the calculator"]):
            result = benchmark.benchmark(self.raw, "open the calculator")
        self.assertEqual(result["processed_wer"], 0)
        self.assertGreater(result["raw_wer"], 0)
        self.assertGreaterEqual(result["processing_seconds"], 0)

    def test_gui_voice_flow_and_new_session(self):
        db = database.SessionDatabase(self.output / "gui.db")
        original_init = app_gui.tk.Tk.__init__
        def hidden_init(instance, *args, **kwargs):
            original_init(instance, *args, **kwargs)
            instance.withdraw()
        with patch.object(app_gui.tk.Tk, "__init__", hidden_init), patch.object(app_gui, "SessionDatabase", return_value=db), patch.object(app_gui.VoiceAssistantApp, "_run_checks_and_populate"), patch.object(app_gui, "RECORDINGS_DIR", self.output / "recordings"), patch.object(audio_processing, "record_audio", return_value=self.raw), patch.object(listen, "transcribe", return_value="test transcript"), patch.object(app_gui, "get_response", return_value=("test answer", "None")):
            app = app_gui.VoiceAssistantApp()
            try:
                request = {"stop": threading.Event(), "language": "en-IN", "api_key": "test-key", "model": "test-model", "rate": 0, "volume": 100, "speak": False, "session": "gui-test", "history": []}
                app._request = request
                app._request_worker(request, None)
                app._drain_ui_events()
                self.assertEqual(db.get_all_records()[0]["transcript"], "test transcript")
                self.assertEqual(app.conversation.snapshot(), [("test transcript", "test answer")])
                self.assertIsNone(app._request)
                app.reset_session()
                self.assertEqual(app.conversation.snapshot(), [])
            finally:
                app.destroy()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProjectTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"tests_run": result.testsRun, "passed": result.wasSuccessful(),
              "failures": [str(test) for test, _ in result.failures],
              "errors": [str(test) for test, _ in result.errors],
              "scope": "Local integration tests; microphone, network APIs and audible playback are mocked.",
              "artifacts": str(ProjectTests.output.relative_to(ROOT))}
    (ROOT / "UNIT_TEST_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
