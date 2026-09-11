# OmniReader — Universal Low-Latency Local Screen & Document Reader

A platform-agnostic, privacy-first local text-to-speech reader engineered to run entirely on your local machine's hardware processing power with near-zero latency (<250ms TTFA).

Triggerable from **any application across your OS** (Safari, Chrome, PDF viewers, Apple Books, Kindle, Notes, Slack, VS Code, Terminal) via macOS Quick Actions, global hotkeys, system tray menu, or CLI pipes.

---

## 1. Features

- **Pipelined Streaming**: Sentence $N$ is synthesized while Sentence $N-1$ is already playing. Audio starts instantly (<250ms) regardless of text length.
- **Visual Follow-Along Teleprompter HUD**: A floating, translucent dark-glass overlay highlights the active sentence, dims completed sentences, and auto-scrolls to keep you in visual scope.
- **Active Window Auto-Scroll**: Issues progressive smooth downward scroll events to the frontmost application (Safari, Chrome, Preview, Notes, VS Code) as speech advances.
- **Dual TTS Engine**:
  - **Kokoro Neural (ONNX int8)**: Studio-grade broadcast quality (82M parameters, 24kHz float32 audio, 54 voices).
  - **System Native**: Instant zero-dependency fallback (macOS `say` / Linux `espeak-ng`).
- **Sample-Accurate Controls**: Non-blocking audio queue with pause, resume, skip, and stop controls.
- **100% Offline & Private**: Zero data leaves your computer.

---

## 2. Quick Installation

### macOS & Linux (Automated Installer)
```bash
git clone https://github.com/stargazer29999/omni-reader.git
cd omni-reader
./install.sh
```
`install.sh` automatically checks for Python 3.11+, builds the virtual environment, downloads the Kokoro model weights, links the `omnisay` executable to `~/.local/bin/omnisay`, and registers macOS Quick Actions.

### Windows
1. Set up Python 3.11+ environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -e .
   ```
2. Run `windows\omni_shortcut.ahk` with [AutoHotkey v2](https://www.autohotkey.com/) to bind **`Alt + Escape`**.

---

## 3. Global Shortcuts Setup

### macOS
1. Open **System Settings** → **Accessibility** → **Spoken Content** and disable native **Speak selection** (to free up `Option + Escape`).
2. Open **System Settings** → **Keyboard** → **Keyboard Shortcuts...** → **Services** → **Text**.
3. Check **Read with OmniReader** and assign **`Option + Escape`** (or `Control + Option + R`).
4. Highlight any text in any app and press **`Option + Escape`**.

### Linux
1. Install clipboard and audio tools:
   ```bash
   sudo apt install -y espeak-ng xclip  # (or wl-clipboard on Wayland)
   ```
2. Go to **Settings** → **Keyboard** → **Custom Shortcuts** → **Add (+)**:
   - **Name**: Read with OmniReader
   - **Command**: `omnisay -s`
   - **Shortcut**: `Alt + Escape`

---

## 4. CLI & Pipe Usage

The `omnisay` binary is linked in `~/.local/bin/omnisay`:

```bash
# Speak arbitrary text with visual HUD
omnisay "Local hardware execution ensures complete data privacy."

# Pipe an article, file, or clipboard
cat article.txt | omnisay
pbpaste | omnisay

# Read active selection or clipboard
omnisay --selection
omnisay --clipboard

# Playback controls
omnisay --pause
omnisay --resume
omnisay --toggle
omnisay --stop
omnisay --next

# Visual options
omnisay --no-hud "Reads without floating teleprompter HUD."
omnisay --no-scroll "Reads without scrolling background window."

# Engine & voice settings
omnisay --speed 1.4
omnisay --voice af_sky
omnisay --engine kokoro
omnisay --status
```

---

## 5. Architecture

```text
[ Trigger: Global Shortcut / Quick Action / Tray / CLI ]
                           │
                           ▼
              [ Active Text Capture ]
       (Direct selection or clipboard buffer)
                           │
                           ▼
          [ Sentence & Markdown Splitter ]
   (Normalizes markdown, links, handles abbreviations)
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
[ Kokoro / System ]  [ Visual HUD ]     [ Window Scroller ]
(Streams audio via   (Highlights active (Auto-scrolls active
 sounddevice queue)   sentence in scope) app to follow text)
```

---

## 6. License
MIT License.
