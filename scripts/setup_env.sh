#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "[OmniReader] Setting up Python virtual environment with uv..."

# Find Python 3.12 or 3.11
PYTHON_BIN="$(which python3.12 2>/dev/null || which python3.11 2>/dev/null || which python3)"

if [ -z "$PYTHON_BIN" ]; then
    echo "[Error] Python 3.11+ is required." >&2
    exit 1
fi

if [ ! -d ".venv" ]; then
    uv venv .venv --python "$PYTHON_BIN"
fi

echo "[OmniReader] Installing core dependencies..."
uv pip install kokoro-onnx sounddevice numpy pillow pystray pynput pyperclip pyobjc-framework-cocoa pyobjc-framework-applicationservices pyobjc-framework-quartz --python ".venv/bin/python"

# Verify model files
MODELS_DIR="$HOME/.local/share/omni_reader/models"
mkdir -p "$MODELS_DIR"

if [ ! -f "$MODELS_DIR/kokoro-v1.0.int8.onnx" ]; then
    echo "[OmniReader] Downloading Kokoro INT8 ONNX model..."
    curl -L -o "$MODELS_DIR/kokoro-v1.0.int8.onnx" "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
fi

if [ ! -f "$MODELS_DIR/voices-v1.0.bin" ]; then
    echo "[OmniReader] Downloading Kokoro voice embeddings..."
    curl -L -o "$MODELS_DIR/voices-v1.0.bin" "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
fi

mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/scripts/omnisay" "$HOME/.local/bin/omnisay"

echo "[OmniReader] Setup complete! Executable available at ~/.local/bin/omnisay"
