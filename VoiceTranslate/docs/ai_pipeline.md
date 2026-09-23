# AI Pipeline

## Status

No AI model packages are installed or loaded. CPU development remains the current supported local mode.

## Planned pipeline

```mermaid
flowchart LR
    Audio[Validated PCM] --> VAD[VAD]
    VAD --> Whisper[Faster-Whisper]
    Whisper --> Translation[SeamlessM4T]
    Translation --> TTS[XTTS-v2]
    TTS --> Client[WebSocket audio response]
```

Model loading will be isolated behind service interfaces and moved off the event loop. Model sizes, device selection, and storage paths will be environment-configured.
