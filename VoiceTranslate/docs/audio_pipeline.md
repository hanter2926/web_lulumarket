# Audio Pipeline

## Status

Audio processing is not implemented. The current backend does not accept microphone frames and does not store raw recordings.

## Planned pipeline

```mermaid
flowchart LR
    PCM[16 kHz mono PCM] --> Validate[Validate frame and size]
    Validate --> Buffer[Bounded buffer]
    Buffer --> VAD[Voice activity detection]
    VAD --> STT[Speech-to-text]
```

Planned safeguards include bounded memory, supported-format checks, sample-rate validation, silence filtering, and configurable speech/silence thresholds.
