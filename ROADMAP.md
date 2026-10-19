# 🗺️ Project Roadmap: Video-to-Text Transcriber

This document outlines the planned features, improvements, and long-term goals for the Video-to-Text Transcriber. 

**Current Version:** `v2.0.0`

---

## 🟢 v2.0.0 (Current Release)
*Core functionality and stability.*
- [x] Video and audio decoding via Whisper & FFmpeg.
- [x] Single-pass and chunked processing modes.
- [x] Auto-detect and manual language selection.
- [x] Safe cancellation and shutdown handling.
- [x] In-app License & Privacy dialogs.
- [x] Developer attribution in app and output transcripts.

---

## 🟡 v2.1.0 (Quality of Life & Usability)
*Focus: Making the app easier and more pleasant to use for everyday tasks.*
- [ ] **SRT/VTT Export:** Add the ability to save transcripts as standard subtitle formats (`.srt`, `.vtt`).
- [ ] **Drag-and-Drop:** Allow users to drag media files directly into the application window.
- [ ] **Bundled FFmpeg:** Include `ffmpeg.exe` inside the PyInstaller build and automatically configure the `PATH` so users don't need to install it separately.
- [ ] **In-App Editor:** Add a text box to the GUI where users can review and correct the transcript before saving.
- [ ] **Word-Level Timestamps:** Add an option to generate word-by-word timestamps for precise subtitle alignment.

---

## 🔵 v3.0.0 (Power User & Performance)
*Focus: Massive speed improvements, batch processing, and professional tooling.*
- [ ] **`faster-whisper` Integration:** Migrate the backend from OpenAI's standard Whisper to `faster-whisper` (CTranslate2) for up to 4x faster transcription and lower RAM usage.
- [ ] **GPU Acceleration (CUDA):** Add a toggle to utilize Nvidia GPUs, significantly speeding up large models.
- [ ] **Batch Processing:** Allow users to select a folder or multiple files to process in a queue.
- [ ] **Professional Installer:** Package the application using Inno Setup to provide a standard Windows `Setup.exe` with Start Menu shortcuts and an uninstaller.
- [ ] **Custom Model Directory:** Allow users to specify where Whisper models are downloaded and stored (e.g., to save space on the C: drive).

---

## 🟣 v4.0.0 (Advanced Audio & Professional Workflows)
*Focus: Advanced audio analysis and meeting transcriptions.*
- [ ] **Speaker Diarization:** Integrate `pyannote.audio` to identify and label different speakers (e.g., `[Speaker 1]`, `[Speaker 2]`).
- [ ] **Audio Trimming:** UI controls to trim the start and end times of a media file before transcription.
- [ ] **Dark Mode:** Add a toggle for a native dark theme (using `sv-ttk` or `customtkinter`).
- [ ] **Translation:** Add an option to transcribe in one language and translate the output text into English (or vice versa).

---

## ❌ Out of Scope (Won't Do)
To keep the application focused, fast, and privacy-respecting, we will *not* be adding:
- **Cloud-based transcription:** The app will always remain 100% offline and local.
- **Video Editing features:** We are focused on text extraction, not video manipulation.
- **Built-in LLM Summarization:** We recommend passing the generated `.txt` files into a dedicated tool like ChatGPT or Claude for summaries.

---

## 🤝 Contributing
Have an idea that isn't on this list? Feel free to open an **Issue** with the `enhancement` tag to discuss it! Pull Requests are always welcome.
