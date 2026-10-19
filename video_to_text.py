
import os
import tempfile
import threading
import time
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import whisper
from moviepy.video.io.VideoFileClip import VideoFileClip


VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpeg", ".mpg"
}
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"
}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


class VideoToTextApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video-to-Text Transcriber")
        self.root.geometry("690x440")
        self.root.minsize(600, 400)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.model_name = tk.StringVar(value="base")
        self.timestamps = tk.BooleanVar(value=True)

        self.messages = queue.Queue()
        self.running = False

        self.build_interface()
        self.root.after(150, self.process_messages)

    def build_interface(self):
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(
            frame,
            text="Video-to-Text Transcriber",
            font=("Segoe UI", 17, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))

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
        options.grid(row=5, column=0, columnspan=2, sticky="w", pady=12)

        ttk.Label(options, text="Whisper model:").pack(side="left")

        ttk.Combobox(
            options,
            textvariable=self.model_name,
            values=("tiny", "base", "small", "medium", "large"),
            state="readonly",
            width=10
        ).pack(side="left", padx=(8, 18))

        ttk.Checkbutton(
            options,
            text="Include timestamps",
            variable=self.timestamps
        ).pack(side="left")

        self.start_button = ttk.Button(
            frame,
            text="Start transcription",
            command=self.start_transcription
        )
        self.start_button.grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(4, 12)
        )

        self.progress = ttk.Progressbar(
            frame, mode="indeterminate"
        )
        self.progress.grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=4
        )

        self.status = ttk.Label(
            frame, text="Select a file to begin.", wraplength=640
        )
        self.status.grid(
            row=8, column=0, columnspan=2, sticky="w", pady=8
        )

        self.open_button = ttk.Button(
            frame,
            text="Open transcript",
            command=self.open_transcript,
            state="disabled"
        )
        self.open_button.grid(
            row=9, column=0, columnspan=2, sticky="ew", pady=4
        )

        self.last_output = None

    def select_input(self):
        path = filedialog.askopenfilename(
            title="Select video or audio",
            filetypes=[
                ("Supported media", "*.mp4 *.mov *.mkv *.avi *.webm "
                 "*.mpeg *.mpg *.mp3 *.wav *.m4a *.aac *.flac "
                 "*.ogg *.opus *.wma"),
                ("All files", "*.*")
            ]
        )
        if path:
            self.input_path.set(path)
            default_output = str(Path(path).with_suffix(".txt"))
            self.output_path.set(default_output)

    def select_output(self):
        path = filedialog.asksaveasfilename(
            title="Save transcript",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if path:
            self.output_path.set(path)

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
                "Unsupported format", "Please select a supported media file."
            )
            return

        if not destination.name or destination.suffix.lower() != ".txt":
            messagebox.showerror(
                "Output required", "Choose a transcript filename ending in .txt."
            )
            return

        if source.resolve() == destination.resolve():
            messagebox.showerror(
                "Invalid output", "The transcript cannot overwrite the input file."
            )
            return

        if not destination.parent.is_dir():
            messagebox.showerror(
                "Invalid folder", "The output folder does not exist."
            )
            return

        if destination.exists():
            overwrite = messagebox.askyesno(
                "Confirm overwrite",
                "This transcript file already exists. Replace it?"
            )
            if not overwrite:
                return

        if self.model_name.get() not in {
            "tiny", "base", "small", "medium", "large"
        }:
            messagebox.showerror("Invalid model", "Select a valid model.")
            return

        self.running = True
        self.start_button.config(state="disabled")
        self.open_button.config(state="disabled")
        self.progress.start(12)
        self.status.config(text="Preparing transcription...")

        threading.Thread(
            target=self.transcription_worker,
            args=(source, destination, self.model_name.get(),
                  self.timestamps.get()),
            daemon=True
        ).start()

    def transcription_worker(self, source, destination, model_name, timestamps):
        temp_audio = None
        start = time.time()

        try:
            self.messages.put(("status", "Loading Whisper model..."))

            # Model downloads may occur on first use.
            model = whisper.load_model(model_name)

            audio_source = source

            if source.suffix.lower() in VIDEO_EXTENSIONS:
                self.messages.put(("status", "Extracting audio from video..."))

                handle = tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                )
                temp_audio = Path(handle.name)
                handle.close()

                with VideoFileClip(str(source)) as video:
                    if video.audio is None:
                        raise ValueError("The video has no audio track.")

                    video.audio.write_audiofile(
                        str(temp_audio),
                        codec="pcm_s16le",
                        logger=None
                    )

                audio_source = temp_audio

            self.messages.put((
                "status",
                "Transcribing audio. Longer recordings may take considerable time..."
            ))

            result = model.transcribe(
                str(audio_source),
                fp16=False,
                verbose=False
            )

            if timestamps:
                lines = []
                for segment in result["segments"]:
                    seconds = int(segment["start"])
                    hours, remainder = divmod(seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    stamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    lines.append(f"[{stamp}] {segment['text'].strip()}")
                text = "\n".join(lines)
            else:
                text = result["text"].strip()

            # Write to a temporary file first to reduce partial output
            # if writing fails.
            temp_output = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    suffix=".tmp",
                    prefix="transcript_",
                    dir=str(destination.parent),
                    delete=False
                ) as output:
                    temp_output = Path(output.name)
                    output.write(text + "\n")

                os.replace(temp_output, destination)
            finally:
                if temp_output and temp_output.exists():
                    temp_output.unlink()

            elapsed = (time.time() - start) / 60
            self.messages.put((
                "success",
                f"Transcript saved to {destination}\n"
                f"Elapsed time: {elapsed:.1f} minutes",
                str(destination)
            ))

        except Exception as exc:
            self.messages.put(("error", str(exc)))

        finally:
            if temp_audio and temp_audio.exists():
                try:
                    temp_audio.unlink()
                except OSError:
                    pass

    def process_messages(self):
        try:
            while True:
                message = self.messages.get_nowait()
                kind = message[0]

                if kind == "status":
                    self.status.config(text=message[1])

                elif kind == "success":
                    self.status.config(text=message[1])
                    self.last_output = Path(message[2])
                    self.open_button.config(state="normal")
                    self.progress.stop()
                    self.running = False
                    self.start_button.config(state="normal")
                    messagebox.showinfo(
                        "Completed", "Transcription completed successfully."
                    )

                elif kind == "error":
                    self.status.config(text="Transcription failed.")
                    self.progress.stop()
                    self.running = False
                    self.start_button.config(state="normal")
                    messagebox.showerror("Transcription error", message[1])

        except queue.Empty:
            pass

        self.root.after(150, self.process_messages)

    def open_transcript(self):
        if self.last_output and self.last_output.exists():
            try:
                os.startfile(str(self.last_output))
            except OSError as exc:
                messagebox.showerror("Cannot open file", str(exc))


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoToTextApp(root)
    root.mainloop()
