import os
import tempfile
import threading
import time
import queue
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import whisper
from whisper.audio import load_audio, SAMPLE_RATE


VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpeg", ".mpg"
}
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"
}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

LANGUAGES = [
    ("Auto-detect", None),
    ("English", "en"), ("Spanish", "es"), ("French", "fr"),
    ("German", "de"), ("Italian", "it"), ("Portuguese", "pt"),
    ("Dutch", "nl"), ("Russian", "ru"), ("Chinese", "zh"),
    ("Japanese", "ja"), ("Korean", "ko"), ("Arabic", "ar"),
    ("Hindi", "hi"), ("Turkish", "tr"), ("Polish", "pl"),
    ("Swedish", "sv"), ("Ukrainian", "uk"), ("Greek", "el"),
    ("Hebrew", "he"), ("Vietnamese", "vi"), ("Indonesian", "id"),
    ("Thai", "th"), ("Czech", "cs"), ("Danish", "da"),
    ("Finnish", "fi"), ("Norwegian", "no"), ("Romanian", "ro"),
    ("Hungarian", "hu"),
]
LANGUAGE_MAP = dict(LANGUAGES)

APP_NAME = "Video-to-Text Transcriber"
APP_VERSION = "2.0.0"
APP_AUTHOR = "Chrispin Kabuya"
COPYRIGHT_YEAR = 2026

CHUNK_SECONDS = 60
CHUNK_OVERLAP_SECONDS = 5

MODE_SINGLE_PASS = "Maximum accuracy (single-pass)"
MODE_CHUNKED = "Fast cancellation (chunked)"
PROCESSING_MODES = (MODE_SINGLE_PASS, MODE_CHUNKED)


class VideoToTextApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("760x600")
        self.root.minsize(680, 560)
        self.root.protocol("WM_DELETE_WINDOW", self.close_application)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.model_name = tk.StringVar(value="base")
        self.language_name = tk.StringVar(value="Auto-detect")
        self.processing_mode = tk.StringVar(value=MODE_SINGLE_PASS)
        self.timestamps = tk.BooleanVar(value=True)

        self.messages = queue.Queue()
        self.cancel_event = threading.Event()
        self.running = False
        self.last_output = None

        self.build_menu()
        self.build_interface()
        self.root.after(150, self.process_messages)

    # ----- UI --------------------------------------------------------------

    def build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Select input...", command=self.select_input)
        file_menu.add_command(
            label="Save transcript as...", command=self.select_output
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Exit", command=self.close_application
        )
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About...", command=self.show_about)
        help_menu.add_command(
            label="License & Privacy...", command=self.show_license_privacy
        )
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def build_interface(self):
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(
            header, text=APP_NAME, font=("Segoe UI", 17, "bold")
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                f"Version {APP_VERSION}   •   by {APP_AUTHOR}\n"
                "Transcription powered by OpenAI Whisper (MIT License)"
            ),
            font=("Segoe UI", 9), foreground="#555555",
        ).pack(anchor="w", pady=(2, 0))

        ttk.Label(frame, text="Input video or audio").grid(
            row=1, column=0, columnspan=2, sticky="w"
        )
        ttk.Entry(frame, textvariable=self.input_path).grid(
            row=2, column=0, sticky="ew", padx=(0, 8), pady=5
        )
        ttk.Button(
            frame, text="Browse...", command=self.select_input
        ).grid(row=2, column=1)

        ttk.Label(frame, text="Save transcript as").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(12, 0)
        )
        ttk.Entry(frame, textvariable=self.output_path).grid(
            row=4, column=0, sticky="ew", padx=(0, 8), pady=5
        )
        ttk.Button(
            frame, text="Save as...", command=self.select_output
        ).grid(row=4, column=1)

        options = ttk.Frame(frame)
        options.grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))

        ttk.Label(options, text="Whisper model:").pack(side="left")
        ttk.Combobox(
            options, textvariable=self.model_name,
            values=("tiny", "base", "small", "medium", "large"),
            state="readonly", width=8,
        ).pack(side="left", padx=(8, 18))

        ttk.Label(options, text="Language:").pack(side="left")
        ttk.Combobox(
            options, textvariable=self.language_name,
            values=[name for name, _ in LANGUAGES],
            state="readonly", width=13,
        ).pack(side="left", padx=(8, 18))

        ttk.Checkbutton(
            options, text="Include timestamps", variable=self.timestamps
        ).pack(side="left")

        mode_row = ttk.Frame(frame)
        mode_row.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(mode_row, text="Processing:").pack(side="left")
        ttk.Combobox(
            mode_row, textvariable=self.processing_mode,
            values=PROCESSING_MODES, state="readonly", width=30,
        ).pack(side="left", padx=(8, 12))
        ttk.Label(
            mode_row,
            text="Chunked mode gives precise progress and quicker cancel "
                 "at a small accuracy cost.",
            font=("Segoe UI", 8), foreground="#777777",
        ).pack(side="left")

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 8))
        buttons.columnconfigure(0, weight=1)

        self.start_button = ttk.Button(
            buttons, text="Start transcription", command=self.start_transcription
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.cancel_button = ttk.Button(
            buttons, text="Cancel", command=self.request_cancel,
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=1)

        self.progress = ttk.Progressbar(
            frame, mode="determinate", maximum=100
        )
        self.progress.grid(row=8, column=0, columnspan=2, sticky="ew", pady=4)

        self.status = ttk.Label(
            frame, text="Select a file to begin.", wraplength=700
        )
        self.status.grid(row=9, column=0, columnspan=2, sticky="w", pady=8)

        self.open_button = ttk.Button(
            frame, text="Open transcript", command=self.open_transcript,
            state="disabled",
        )
        self.open_button.grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=4
        )

    # ----- File selection --------------------------------------------------

    def select_input(self):
        path = filedialog.askopenfilename(
            title="Select video or audio",
            filetypes=[
                ("Supported media",
                 "*.mp4 *.mov *.mkv *.avi *.webm *.mpeg *.mpg "
                 "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.input_path.set(path)
            self.output_path.set(str(Path(path).with_suffix(".txt")))

    def select_output(self):
        path = filedialog.asksaveasfilename(
            title="Save transcript", defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
        )
        if path:
            self.output_path.set(path)

    # ----- Start / cancel / close ------------------------------------------

    def start_transcription(self):
        if self.running:
            return

        source = Path(self.input_path.get().strip().strip('"'))
        destination = Path(self.output_path.get().strip().strip('"'))

        if not source.is_file():
            messagebox.showerror(
                "Input required", "Please select an existing media file."
            )
            return
        if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            messagebox.showerror(
                "Unsupported format",
                "Please select a supported media file.",
            )
            return
        if not destination.name or destination.suffix.lower() != ".txt":
            messagebox.showerror(
                "Output required",
                "Choose a transcript filename ending in .txt.",
            )
            return
        if source.resolve() == destination.resolve():
            messagebox.showerror(
                "Invalid output",
                "The transcript cannot overwrite the input file.",
            )
            return
        if not destination.parent.is_dir():
            messagebox.showerror(
                "Invalid folder", "The output folder does not exist."
            )
            return
        if destination.exists():
            if not messagebox.askyesno(
                "Confirm overwrite",
                "This transcript file already exists. Replace it?",
            ):
                return
        if self.model_name.get() not in {
            "tiny", "base", "small", "medium", "large"
        }:
            messagebox.showerror("Invalid model", "Select a valid model.")
            return
        if self.language_name.get() not in LANGUAGE_MAP:
            messagebox.showerror(
                "Invalid language", "Select a valid language."
            )
            return
        if self.processing_mode.get() not in PROCESSING_MODES:
            messagebox.showerror(
                "Invalid processing mode", "Select a valid processing mode."
            )
            return

        self.cancel_event.clear()
        self.running = True
        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.open_button.config(state="disabled")
        self.progress["mode"] = "determinate"
        self.progress["value"] = 0
        self.status.config(text="Preparing transcription...")

        threading.Thread(
            target=self.transcription_worker,
            args=(
                source, destination, self.model_name.get(),
                self.timestamps.get(),
                LANGUAGE_MAP[self.language_name.get()],
                self.processing_mode.get(),
            ),
            daemon=True,
        ).start()

    def request_cancel(self):
        if not self.running:
            return
        self.cancel_event.set()
        self.cancel_button.config(state="disabled")
        if self.processing_mode.get() == MODE_SINGLE_PASS:
            self.status.config(
                text="Cancel requested. Note: single-pass transcription "
                     "cannot be interrupted mid-call; cancellation will "
                     "take effect when the model call returns."
            )
        else:
            self.status.config(
                text="Cancelling... waiting for the current audio chunk "
                     "to finish."
            )

    def close_application(self):
        if self.running:
            if not messagebox.askyesno(
                "Transcription in progress",
                "Request cancellation and close the application?",
            ):
                return
            self.cancel_event.set()
            self.status.config(text="Cancelling, please wait...")
            deadline = time.time() + 3.0
            while self.running and time.time() < deadline:
                self.root.update()
                time.sleep(0.05)
        self.root.destroy()

    # ----- Worker ----------------------------------------------------------

    def transcription_worker(
        self, source, destination, model_name, timestamps,
        language_code, mode,
    ):
        start_time = time.time()
        try:
            if self.cancel_event.is_set():
                self.messages.put(("cancelled",)); return

            self.messages.put(("status", "Loading Whisper model..."))
            self.messages.put(("progress", 5))
            model = whisper.load_model(model_name)

            if self.cancel_event.is_set():
                self.messages.put(("cancelled",)); return

            self.messages.put(("status", "Decoding audio track..."))
            self.messages.put(("progress", 15))
            audio = load_audio(str(source))
            if len(audio) == 0:
                raise RuntimeError(
                    "The selected file has no audio track or could not be "
                    "decoded. Ensure FFmpeg is installed and available on "
                    "PATH."
                )
            duration_s = len(audio) / SAMPLE_RATE

            if self.cancel_event.is_set():
                self.messages.put(("cancelled",)); return

            segments = []
            detected_language = None

            if mode == MODE_SINGLE_PASS:
                self.messages.put((
                    "status",
                    f"Transcribing {int(duration_s // 60)}:"
                    f"{int(duration_s % 60):02d} of audio in one pass. "
                    "This cannot be interrupted mid-call."
                ))
                self.messages.put(("progress_pulse_start",))
                result = model.transcribe(
                    audio, language=language_code,
                    fp16=False, verbose=False,
                )
                self.messages.put(("progress_pulse_stop",))
                if self.cancel_event.is_set():
                    self.messages.put(("cancelled",)); return
                segments = result["segments"]
                detected_language = result.get("language")
            else:
                chunk_samples = CHUNK_SECONDS * SAMPLE_RATE
                step_samples = (
                    (CHUNK_SECONDS - CHUNK_OVERLAP_SECONDS) * SAMPLE_RATE
                )
                total_chunks = max(
                    1, (len(audio) + step_samples - 1) // step_samples
                )
                last_committed_end = 0.0

                for i in range(total_chunks):
                    if self.cancel_event.is_set():
                        self.messages.put(("cancelled",)); return

                    chunk_start = i * (CHUNK_SECONDS - CHUNK_OVERLAP_SECONDS)
                    chunk_end_s = min(chunk_start + CHUNK_SECONDS, duration_s)
                    self.messages.put((
                        "status",
                        f"Transcribing {int(chunk_start // 60)}:"
                        f"{int(chunk_start % 60):02d}"
                        f"–{int(chunk_end_s // 60)}:"
                        f"{int(chunk_end_s % 60):02d} "
                        f"(chunk {i + 1}/{total_chunks})..."
                    ))

                    chunk_audio = audio[
                        i * step_samples : i * step_samples + chunk_samples
                    ]
                    language_to_use = language_code or detected_language
                    result = model.transcribe(
                        chunk_audio, language=language_to_use,
                        fp16=False, verbose=False,
                    )
                    if detected_language is None:
                        detected_language = result.get("language")

                    for seg in result["segments"]:
                        seg_start = seg["start"] + chunk_start
                        seg_end = seg["end"] + chunk_start
                        # Overlap dedup: keep only segments that extend
                        # past what has already been committed. Segments
                        # straddling a boundary are attributed to the
                        # chunk that started them, which is a small,
                        # documented trade-off of chunked processing.
                        if seg_end > last_committed_end + 0.01:
                            segments.append({
                                "start": seg_start,
                                "end": seg_end,
                                "text": seg["text"],
                            })
                            last_committed_end = max(
                                last_committed_end, seg_end
                            )

                    self.messages.put((
                        "progress",
                        15 + int((i + 1) / total_chunks * 75),
                    ))

            if self.cancel_event.is_set():
                self.messages.put(("cancelled",)); return

            self.messages.put(("status", "Writing transcript..."))
            self.messages.put(("progress", 95))

            if timestamps:
                lines = []
                for seg in segments:
                    sec = int(seg["start"])
                    h, r = divmod(sec, 3600)
                    m, s = divmod(r, 60)
                    lines.append(
                        f"[{h:02d}:{m:02d}:{s:02d}] {seg['text'].strip()}"
                    )
                body = "\n".join(lines)
            else:
                body = " ".join(
                    seg["text"].strip() for seg in segments
                ).strip()

            language_used = language_code or detected_language or "auto"
            header = (
                f"{APP_NAME} v{APP_VERSION}\n"
                f"Developed by {APP_AUTHOR}\n"
                "Transcription engine: OpenAI Whisper (MIT License)\n"
                f"Source file: {source.name}\n"
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Language: {language_used}\n"
                + "-" * 60 + "\n\n"
            )
            full_text = header + body

            # Atomic write: temporary file in the destination folder,
            # then os.replace so a partial write cannot damage the target.
            tmp_output = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".tmp",
                    prefix="transcript_", dir=str(destination.parent),
                    delete=False,
                ) as handle:
                    tmp_output = Path(handle.name)
                    handle.write(full_text + "\n")
                os.replace(tmp_output, destination)
            finally:
                if tmp_output and tmp_output.exists():
                    tmp_output.unlink()

            elapsed = (time.time() - start_time) / 60
            self.messages.put((
                "success",
                f"Transcript saved to {destination}\n"
                f"Language: {language_used}\n"
                f"Elapsed time: {elapsed:.1f} minutes",
                str(destination),
            ))
            self.messages.put(("progress", 100))

        except Exception as exc:
            if self.cancel_event.is_set():
                self.messages.put(("cancelled",))
            else:
                self.messages.put(("error", str(exc)))

    # ----- Message pump ----------------------------------------------------

    def process_messages(self):
        try:
            while True:
                message = self.messages.get_nowait()
                kind = message[0]

                if kind == "status":
                    self.status.config(text=message[1])

                elif kind == "progress":
                    if self.progress["mode"] != "determinate":
                        self.progress.stop()
                        self.progress["mode"] = "determinate"
                    self.progress["value"] = message[1]

                elif kind == "progress_pulse_start":
                    self.progress["mode"] = "indeterminate"
                    self.progress.start(12)

                elif kind == "progress_pulse_stop":
                    self.progress.stop()
                    self.progress["mode"] = "determinate"

                elif kind == "success":
                    self.status.config(text=message[1])
                    self.progress.stop()
                    self.progress["mode"] = "determinate"
                    self.progress["value"] = 100
                    self.last_output = Path(message[2])
                    self.open_button.config(state="normal")
                    self.running = False
                    self.start_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    messagebox.showinfo(
                        "Completed",
                        "Transcription completed successfully.",
                    )

                elif kind == "error":
                    self.status.config(text="Transcription failed.")
                    self.progress.stop()
                    self.progress["mode"] = "determinate"
                    self.progress["value"] = 0
                    self.running = False
                    self.start_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    messagebox.showerror(
                        "Transcription error", message[1]
                    )

                elif kind == "cancelled":
                    self.status.config(text="Transcription cancelled.")
                    self.progress.stop()
                    self.progress["mode"] = "determinate"
                    self.progress["value"] = 0
                    self.running = False
                    self.start_button.config(state="normal")
                    self.cancel_button.config(state="disabled")

        except queue.Empty:
            pass

        self.root.after(150, self.process_messages)

    # ----- Open transcript -------------------------------------------------

    def open_transcript(self):
        if self.last_output and self.last_output.exists():
            try:
                os.startfile(str(self.last_output))
            except OSError as exc:
                messagebox.showerror("Cannot open file", str(exc))

    # ----- Info dialogs ----------------------------------------------------

    def _make_info_window(self, title, width, height):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(f"{width}x{height}")
        win.transient(self.root)
        win.minsize(420, 320)

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="word", font=("Segoe UI", 9))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)
        return text

    def show_about(self):
        text = self._make_info_window("About", 560, 500)
        content = (
            f"{APP_NAME}\n"
            f"Version {APP_VERSION}\n\n"
            "A desktop application for transcribing video and audio "
            "files to text using OpenAI Whisper.\n\n"
            "DEVELOPER\n"
            f"Developed by {APP_AUTHOR}.\n\n"
            "If you reuse, modify, or redistribute this software, please "
            "retain the developer credit and the OpenAI Whisper attribution "
            "shown below.\n\n"
            "TRANSCRIPTION ENGINE\n"
            "OpenAI Whisper — MIT License\n"
            "https://github.com/openai/whisper\n\n"
            "THIRD-PARTY STACK\n"
            "- Python 3 — PSF License\n"
            "- Tkinter — PSF License\n"
            "- PyTorch — BSD-style License\n"
            "- FFmpeg — LGPL 2.1+ or GPL 2+ depending on build\n\n"
            "BEFORE PACKAGING OR DISTRIBUTING\n"
            "Verify the licence and redistribution requirements of the "
            "specific PyTorch and FFmpeg builds you bundle. See "
            "Help → License & Privacy for details.\n"
        )
        text.insert("1.0", content)
        text.config(state="disabled")

    def show_license_privacy(self):
        text = self._make_info_window("License & Privacy", 660, 600)
        content = (
            "LICENSE & PRIVACY\n"
            "=================\n\n"
            "PRIVACY\n"
            "-------\n"
            "Audio and video transcription is performed locally using "
            "OpenAI Whisper. This application does not intentionally "
            "transmit your media files or transcripts to a remote "
            "transcription service. Internet access may be required to "
            "download a Whisper model on first use. Once the model is "
            "available locally, transcription can run offline, provided "
            "the required dependencies (FFmpeg, PyTorch, and the Python "
            "runtime) are installed. This application does not implement "
            "telemetry or analytics.\n\n"
            "Model weights are cached locally, typically under "
            "~/.cache/whisper (Linux/macOS) or "
            "%USERPROFILE%\\.cache\\whisper (Windows).\n\n"
            "THIRD-PARTY COMPONENTS AND LICENCES\n"
            "-----------------------------------\n"
            "- OpenAI Whisper — MIT License\n"
            "  https://github.com/openai/whisper/blob/main/LICENSE\n"
            "- PyTorch — BSD-style License\n"
            "  https://github.com/pytorch/pytorch/blob/main/LICENSE\n"
            "- FFmpeg — LGPL 2.1+ or GPL 2+ depending on the build used\n"
            "  https://ffmpeg.org/legal.html\n"
            "- Python and Tkinter — Python Software Foundation License\n"
            "  https://docs.python.org/3/license.html\n\n"
            "You are responsible for verifying the licences of any "
            "binaries you bundle or redistribute. This application's own "
            "MIT licence does not override the licences of the third-party "
            "components listed above.\n\n"
            "APPLICATION LICENCE (MIT)\n"
            "-------------------------\n"
            f"Copyright (c) {COPYRIGHT_YEAR} {APP_AUTHOR}\n\n"
            "Permission is hereby granted, free of charge, to any person "
            "obtaining a copy of this software and associated documentation "
            "files (the \"Software\"), to deal in the Software without "
            "restriction, including without limitation the rights to use, "
            "copy, modify, merge, publish, distribute, sublicense, and/or "
            "sell copies of the Software, and to permit persons to whom "
            "the Software is furnished to do so, subject to the following "
            "conditions:\n\n"
            "The above copyright notice and this permission notice shall "
            "be included in all copies or substantial portions of the "
            "Software.\n\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY "
            "KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE "
            "WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR "
            "PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR "
            "COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER "
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR "
            "OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE "
            "SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.\n"
        )
        text.insert("1.0", content)
        text.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoToTextApp(root)
    root.mainloop()