#!/usr/bin/env bash
set -e

# OmniReader Master Universal Installer
# Compatible with macOS and Linux

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=================================================="
echo "    OmniReader Universal Installer (v1.0.0)"
echo "=================================================="

# 1. Detect OS
OS_TYPE="$(uname -s)"
echo "[1/5] Detected Operating System: $OS_TYPE"

# 2. Check Python 3.11+
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        VER="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        MAJOR="$(echo "$VER" | cut -d. -f1)"
        MINOR="$(echo "$VER" | cut -d. -f2)"
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 11 ]; then
            PYTHON_BIN="$(command -v "$candidate")"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[Error] Python 3.11 or newer is required to run OmniReader." >&2
    echo "Please install Python 3.11+ and run this script again." >&2
    exit 1
fi
echo "[2/5] Using Python binary: $PYTHON_BIN ($VER)"

# 3. Create Virtual Environment & Install Dependencies
echo "[3/5] Setting up environment and installing dependencies..."
if command -v uv >/dev/null 2>&1; then
    if [ ! -d ".venv" ]; then
        uv venv .venv --python "$PYTHON_BIN"
    fi
    uv pip install -e . --python ".venv/bin/python"
else
    if [ ! -d ".venv" ]; then
        "$PYTHON_BIN" -m venv .venv
    fi
    .venv/bin/pip install --upgrade pip setuptools wheel
    .venv/bin/pip install -e .
fi

# 4. Download Neural Model Weights if missing
MODELS_DIR="$HOME/.local/share/omni_reader/models"
mkdir -p "$MODELS_DIR"

echo "[4/5] Checking neural speech model assets..."
if [ ! -f "$MODELS_DIR/kokoro-v1.0.int8.onnx" ]; then
    echo "  -> Downloading Kokoro INT8 ONNX model (~88MB)..."
    curl -L --progress-bar -o "$MODELS_DIR/kokoro-v1.0.int8.onnx" \
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
fi

if [ ! -f "$MODELS_DIR/voices-v1.0.bin" ]; then
    echo "  -> Downloading voice embeddings (~27MB)..."
    curl -L --progress-bar -o "$MODELS_DIR/voices-v1.0.bin" \
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
fi

# Link executable into ~/.local/bin
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/scripts/omnisay" "$HOME/.local/bin/omnisay"
chmod +x "$DIR/scripts/omnisay"

# 5. OS-Specific Integration
echo "[5/5] Configuring OS integration..."
if [ "$OS_TYPE" = "Darwin" ]; then
    # Run macOS Quick Action installer
    bash "$DIR/scripts/install_macos_service.sh"
elif [ "$OS_TYPE" = "Linux" ]; then
    echo "[OmniReader] Linux integration:"
    echo "  Ensure you have audio and clipboard dependencies installed:"
    echo "  sudo apt install -y espeak-ng xclip  # (or wl-clipboard on Wayland)"
    echo ""
    echo "  To set up your global shortcut:"
    echo "  Settings -> Keyboard -> Custom Shortcuts -> Add (+)"
    echo "    Name:    Read with OmniReader"
    echo "    Command: $HOME/.local/bin/omnisay -s"
    echo "    Key:     Alt + Escape"
fi

echo ""
echo "=================================================="
echo "    Installation Complete!"
echo "=================================================="
echo "Executable linked to: $HOME/.local/bin/omnisay"
echo "Test playback now with: omnisay 'OmniReader is ready to read.'"
