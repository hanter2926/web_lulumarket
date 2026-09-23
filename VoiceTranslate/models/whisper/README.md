# Whisper Models

## Planned use

Faster-Whisper will provide speech-to-text after the audio/VAD phases are complete.

## Requirements

Model size, compute type, device, and cache directory must be environment-configured. CPU development should use a small model and avoid assuming CUDA. Production GPU workers will need VRAM sized for the selected model and concurrency.

Do not download or load a model from this repository yet.
