#!/usr/bin/env bash
set -euo pipefail

echo "=== smoke-test-ai installer ==="

OS="$(uname -s)"
case "$OS" in
    Linux)
        echo "Installing libusb on Linux..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y libusb-1.0-0-dev libudev-dev
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y libusb1-devel
        fi
        ;;
    Darwin)
        echo "Installing libusb on macOS..."
        brew install libusb
        ;;
    *)
        echo "Unsupported OS: $OS. Please install libusb manually."
        ;;
esac

echo "Installing Python dependencies..."
pip install -e ".[dev]"

echo "=== Installation complete ==="
