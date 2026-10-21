import os
import sys
import json
import threading
import time
import queue
import logging
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD
from faster_whisper import WhisperModel

# Suppress HuggingFace symlink warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR) 

# --- FFMPEG BUNDLING LOGIC ---
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    os.environ["PATH"] += os.pathsep + bundle_dir

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpeg", ".mpg"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

LANGUAGES = [
    ("Auto-detect", None), ("English", "en"), ("Spanish", "es"), ("French", "fr"),
    ("German", "de"), ("Italian", "it"), ("Portuguese", "pt"), ("Dutch", "nl"),
    ("Russian", "ru"), ("Chinese", "zh"), ("Japanese", "ja"), ("Korean", "ko"),
    ("Arabic", "ar"), ("Hindi", "hi"), ("Turkish", "tr"), ("Polish", "pl"),
    ("Swedish", "sv"), ("Ukrainian", "uk"), ("Greek", "el"), ("Hebrew", "he"),
    ("Vietnamese", "vi"), ("Indonesian", "id"), ("Thai", "th"), ("Czech", "cs"),
    ("Danish", "da"), ("Finnish", "fi"), ("Norwegian", "no"), ("Romanian", "ro"),
    ("Hungarian", "hu"),
]
LANGUAGE_MAP = dict(LANGUAGES)

APP_NAME = "Video-to-Text Transcriber"
APP_VERSION = "3.0.0-rc" 
APP_AUTHOR = "Chrispin Kabuya"
CONFIG_FILE = Path.home() / ".video_to_text_config.json"

class VideoToTextApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1000x750")
        self.root.minsize(950, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.close_application)

        # Settings Variables
        self.output_format = tk.StringVar(value=".txt")
        self.model_name = tk.StringVar(value="base")
        self.language_name = tk.StringVar(value="Auto-detect")
        self.timestamps = tk.BooleanVar(value=True)
        self.word_timestamps = tk.BooleanVar(value=False)
        
        # Phase 3 Variables
        self.use_gpu = tk.BooleanVar(value=False)
        self.custom_model_dir = tk.StringVar()

        self.messages = queue.Queue()
        self.cancel_event = threading.Event()
        self.running = False
        self.file_queue = []
        
        self.load_config()
        
        self.build_menu()
        self.build_interface()
        
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.handle_drop)

        self.root.after(100, self.process_messages)

    # ----- CONFIG MANAGEMENT -----
    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.use_gpu.set(config.get("use_gpu", False))
                    self.custom_model_dir.set(config.get("model_dir", ""))
            except Exception:
                pass # Ignore corrupted config

    def save_config(self):
        config = {
            "use_gpu": self.use_gpu.get(),
            "model_dir": self.custom_model_dir.get().strip()
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f)
        except Exception:
            pass

    def build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Add Files...", command=self.add_files)
        file_menu.add_command(label="Clear Queue", command=self.clear_queue)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close_application)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

    def build_interface(self):
        main_frame = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        left_panel = ttk.Frame(main_frame, padding=10)
        right_panel = ttk.Frame(main_frame, padding=10)
        main_frame.add(left_panel, weight=2)
        main_frame.add(right_panel, weight=3)

        # --- LEFT PANEL (Settings & Queue) ---
        ttk.Label(left_panel, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(left_panel, text=f"v{APP_VERSION} • by {APP_AUTHOR}", font=("Segoe UI", 9), foreground="#555").pack(anchor="w", pady=(0, 10))

        # Basic Settings Grid
        settings_frame = ttk.LabelFrame(left_panel, text="Transcription Settings", padding=10)
        settings_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(settings_frame, text="Model:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(settings_frame, textvariable=self.model_name, values=("tiny", "base", "small", "medium", "large-v3", "distil-large-v3"), state="readonly", width=15).grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(settings_frame, text="Language:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Combobox(settings_frame, textvariable=self.language_name, values=[name for name, _ in LANGUAGES], state="readonly", width=15).grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(settings_frame, text="Export:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Combobox(settings_frame, textvariable=self.output_format, values=(".txt", ".srt", ".vtt"), state="readonly", width=15).grid(row=2, column=1, sticky="w", padx=5)

        ttk.Checkbutton(settings_frame, text="Segment timestamps", variable=self.timestamps).grid(row=3, column=0, columnspan=2, sticky="w", pady=(5,0))
        ttk.Checkbutton(settings_frame, text="Word-level timestamps", variable=self.word_timestamps).grid(row=4, column=0, columnspan=2, sticky="w")

        # Advanced Settings (Phase 3)
        adv_frame = ttk.LabelFrame(left_panel, text="Advanced (GPU & Storage)", padding=10)
        adv_frame.pack(fill="x", pady=(0, 10))

        ttk.Checkbutton(adv_frame, text="Use Nvidia GPU (CUDA) if available", variable=self.use_gpu).pack(anchor="w", pady=(0, 5))

        ttk.Label(adv_frame, text="Model Download Folder (Leave blank for default):").pack(anchor="w")
        dir_frame = ttk.Frame(adv_frame)
        dir_frame.pack(fill="x", pady=(2, 0))
        
        ttk.Entry(dir_frame, textvariable=self.custom_model_dir).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(dir_frame, text="...", width=3, command=self.browse_model_dir).pack(side="right")

        # Batch Queue
        ttk.Label(left_panel, text="Batch Queue (Drag & Drop here):", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        queue_frame = ttk.Frame(left_panel)
        queue_frame.pack(fill="both", expand=True, pady=(2, 10))
        
        self.queue_tree = ttk.Treeview(queue_frame, columns=("File", "Status"), show="headings", height=5)
        self.queue_tree.heading("File", text="File Name")
        self.queue_tree.heading("Status", text="Status")
        self.queue_tree.column("File", width=180)
        self.queue_tree.column("Status", width=80)
        
        q_scroll = ttk.Scrollbar(queue_frame, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=q_scroll.set)
        q_scroll.pack(side="right", fill="y")
        self.queue_tree.pack(side="left", fill="both", expand=True)
        self.queue_tree.bind("<<TreeviewSelect>>", self.on_queue_select)

        # Controls
        controls_frame = ttk.Frame(left_panel)
        controls_frame.pack(fill="x")
        
        ttk.Button(controls_frame, text="Add Files...", command=self.add_files).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(controls_frame, text="Clear", command=self.clear_queue).pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.start_button = ttk.Button(controls_frame, text="▶ Start Batch", command=self.start_transcription)
        self.start_button.pack(side="left", expand=True, fill="x")

        self.cancel_button = ttk.Button(left_panel, text="Cancel Processing", command=self.request_cancel, state="disabled")
        self.cancel_button.pack(fill="x", pady=(5, 10))

        self.progress = ttk.Progressbar(left_panel, mode="determinate", maximum=100)
        self.progress.pack(fill="x")

        self.status = ttk.Label(left_panel, text="Ready. Add files to begin.", wraplength=350)
        self.status.pack(anchor="w", pady=5)

        # --- RIGHT PANEL (Transcript Editor) ---
        ttk.Label(right_panel, text="Transcript Viewer", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        editor_frame = ttk.Frame(right_panel)
        editor_frame.pack(fill="both", expand=True, pady=5)
        
        self.editor = tk.Text(editor_frame, wrap="word", font=("Consolas", 10))
        scroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self.editor.yview)
        self.editor.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.editor.pack(side="left", fill="both", expand=True)

    def browse_model_dir(self):
        path = filedialog.askdirectory(title="Select Model Download Folder")
        if path:
            self.custom_model_dir.set(path)

    def handle_drop(self, event):
        if self.running: return
        files = self.root.tk.splitlist(event.data)
        added = 0
        for f in files:
            path = Path(f)
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                self.add_file_to_queue(path)
                added += 1
        if added > 0:
            self.status.config(text=f"Added {added} file(s) to queue.")

    def add_files(self):
        if self.running: return
        paths = filedialog.askopenfilenames(filetypes=[("Supported media", "*.mp4 *.mkv *.mp3 *.wav *.m4a *.flac"), ("All files", "*.*")])
        for p in paths:
            self.add_file_to_queue(Path(p))

    def add_file_to_queue(self, path):
        for item in self.file_queue:
            if item['path'] == path: return
        item_id = self.queue_tree.insert("", tk.END, values=(path.name, "Pending"))
        self.file_queue.append({"path": path, "id": item_id, "status": "Pending"})

    def clear_queue(self):
        if self.running: return
        self.queue_tree.delete(*self.queue_tree.get_children())
        self.file_queue.clear()
        self.status.config(text="Queue cleared.")

    def on_queue_select(self, event):
        if self.running: return
        selected = self.queue_tree.selection()
        if not selected: return
        item_id = selected[0]
        
        for item in self.file_queue:
            if item["id"] == item_id:
                if item.get("segments"):
                    self.editor.delete("1.0", tk.END)
                    fmt = self.output_format.get()
                    segments = item["segments"]
                    
                    if fmt == ".srt":
                        text = "".join([f"{i+1}\n{self.format_timestamp(s['start'], 'srt')} --> {self.format_timestamp(s['end'], 'srt')}\n{s['text'].strip()}\n\n" for i, s in enumerate(segments)])
                    elif fmt == ".vtt":
                        text = "WEBVTT\n\n" + "".join([f"{self.format_timestamp(s['start'], 'vtt')} --> {self.format_timestamp(s['end'], 'vtt')}\n{s['text'].strip()}\n\n" for s in segments])
                    elif self.timestamps.get():
                        text = "".join([f"[{self.format_timestamp(s['start'], 'txt')}] {s['text'].strip()}\n" for s in segments])
                    else:
                        text = " ".join([s['text'].strip() for s in segments])
                        
                    self.editor.insert("1.0", text)
                else:
                    self.editor.delete("1.0", tk.END)
                    self.editor.insert("1.0", f"File '{item['path'].name}' is {item['status']}.")
                break

    def start_transcription(self):
        if self.running or not self.file_queue: return
        
        self.save_config() # Save settings for next time
        
        self.cancel_event.clear()
        self.running = True
        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.progress["value"] = 0
        self.status.config(text="Starting batch process...")

        for item in self.file_queue:
            self.queue_tree.set(item["id"], "Status", "Pending")

        threading.Thread(
            target=self.transcription_worker,
            args=(
                self.model_name.get(), 
                LANGUAGE_MAP[self.language_name.get()], 
                self.timestamps.get(), 
                self.word_timestamps.get(),
                self.output_format.get(),
                self.use_gpu.get(),
                self.custom_model_dir.get().strip()
            ),
            daemon=True
        ).start()

    def request_cancel(self):
        if not self.running: return
        self.cancel_event.set()
        self.status.config(text="Cancelling batch...")

    def transcription_worker(self, model_name, lang_code, ts_seg, ts_word, out_fmt, use_gpu, custom_dir):
        try:
            download_root = custom_dir if custom_dir else None
            
            # --- GPU FALLBACK LOGIC ---
            if use_gpu:
                try:
                    self.messages.put(("status", f"Loading model '{model_name}' on GPU (CUDA)..."))
                    model = WhisperModel(model_name, device="cuda", compute_type="float16", download_root=download_root)
                except Exception as e:
                    self.messages.put(("status", "GPU failed. Falling back to CPU..."))
                    time.sleep(2) # Let user read the warning
                    model = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=download_root)
            else:
                self.messages.put(("status", f"Loading model '{model_name}' on CPU..."))
                model = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=download_root)
            
            total_files = len(self.file_queue)
            
            for index, item in enumerate(self.file_queue):
                if self.cancel_event.is_set():
                    self.messages.put(("update_status", item["id"], "Cancelled"))
                    continue

                file_path = item["path"]
                self.messages.put(("update_status", item["id"], "Processing..."))
                self.messages.put(("status", f"Processing {index + 1}/{total_files}: {file_path.name}"))
                
                try:
                    segments_generator, info = model.transcribe(
                        str(file_path), language=lang_code, word_timestamps=ts_word, vad_filter=True
                    )
                    
                    self.messages.put(("lang", info.language))
                    extracted_segments = []
                    
                    for segment in segments_generator:
                        if self.cancel_event.is_set(): break
                        file_pct = min(100, (segment.end / info.duration) * 100) if info.duration > 0 else 0
                        overall_pct = int(((index / total_files) * 100) + ((file_pct / total_files)))
                        self.messages.put(("progress", overall_pct))
                        
                        extracted_segments.append({
                            "start": segment.start,
                            "end": segment.end,
                            "text": segment.text
                        })

                    if self.cancel_event.is_set():
                        self.messages.put(("update_status", item["id"], "Cancelled"))
                        continue

                    out_path = file_path.with_suffix(out_fmt)
                    self.save_file(out_path, extracted_segments, file_path.name, info.language, out_fmt, ts_seg)
                    
                    self.messages.put(("update_status", item["id"], "Done"))
                    self.messages.put(("update_editor", extracted_segments, ts_seg))
                    item["segments"] = extracted_segments

                except Exception as e:
                    self.messages.put(("update_status", item["id"], "Error"))
                    self.messages.put(("status", f"Error on {file_path.name}: {str(e)}"))

            self.messages.put(("batch_done",))
            
        except Exception as exc:
            self.messages.put(("error", str(exc)))

    def save_file(self, out_path, segments, source_name, lang, fmt, include_ts):
        if fmt in (".srt", ".vtt"):
            out = "WEBVTT\n\n" if fmt == ".vtt" else ""
            for i, s in enumerate(segments, 1):
                start = self.format_timestamp(s['start'], fmt[1:])
                end = self.format_timestamp(s['end'], fmt[1:])
                if fmt == ".srt": out += f"{i}\n"
                out += f"{start} --> {end}\n{s['text'].strip()}\n\n"
        else:
            if include_ts:
                lines = [f"[{self.format_timestamp(s['start'], 'txt')}] {s['text'].strip()}" for s in segments]
                body = "\n".join(lines)
            else:
                body = " ".join([s['text'].strip() for s in segments])
                
            header = (
                f"{APP_NAME} v{APP_VERSION}\n"
                f"Developed by {APP_AUTHOR}\n"
                f"Source file: {source_name}\n"
                f"Language: {lang}\n"
                + "-" * 60 + "\n\n"
            )
            out = header + body

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(out)

    def format_timestamp(self, seconds, format="srt"):
        h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        if format == "srt": return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        elif format == "vtt": return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
        return f"{h:02d}:{m:02d}:{s:02d}"

    def process_messages(self):
        try:
            while True:
                msg = self.messages.get_nowait()
                kind = msg[0]

                if kind == "status": self.status.config(text=msg[1])
                elif kind == "progress": self.progress["value"] = msg[1]
                elif kind == "lang": self.detected_language = msg[1]
                elif kind == "update_status":
                    self.queue_tree.set(msg[1], "Status", msg[2])
                elif kind == "update_editor":
                    segments = msg[1]
                    show_ts = msg[2]
                    fmt = self.output_format.get()
                    self.editor.delete("1.0", tk.END)
                    
                    if fmt == ".srt":
                        text = "".join([f"{i+1}\n{self.format_timestamp(s['start'], 'srt')} --> {self.format_timestamp(s['end'], 'srt')}\n{s['text'].strip()}\n\n" for i, s in enumerate(segments)])
                    elif fmt == ".vtt":
                        text = "WEBVTT\n\n" + "".join([f"{self.format_timestamp(s['start'], 'vtt')} --> {self.format_timestamp(s['end'], 'vtt')}\n{s['text'].strip()}\n\n" for s in segments])
                    elif show_ts:
                        text = "".join([f"[{self.format_timestamp(s['start'], 'txt')}] {s['text'].strip()}\n" for s in segments])
                    else:
                        text = " ".join([s['text'].strip() for s in segments])
                        
                    self.editor.insert("1.0", text)
                
                elif kind == "batch_done":
                    self.progress["value"] = 100
                    self.running = False
                    self.start_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    self.status.config(text="Batch processing complete!")
                    messagebox.showinfo("Batch Complete", "All files in the queue have been processed.")

                elif kind == "error":
                    self.progress["value"] = 0
                    self.running = False
                    self.start_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    self.status.config(text="Fatal Error.")
                    messagebox.showerror("Transcription Error", msg[1])

        except queue.Empty:
            pass
        self.root.after(100, self.process_messages)

    def close_application(self):
        if self.running:
            if not messagebox.askyesno("In Progress", "Cancel and exit?"): return
            self.cancel_event.set()
        self.root.destroy()

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = VideoToTextApp(root)
    root.mainloop()