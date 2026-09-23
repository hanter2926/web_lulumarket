# Model Management

AI models are intentionally not downloaded or loaded in the current milestone.

## Planned model families

- Whisper: speech-to-text.
- Translation: SeamlessM4T text/audio translation services.
- TTS: XTTS-v2 speech synthesis.

Development targets CPU-compatible model sizes and explicit `DEVICE=cpu` configuration. Production GPU deployment will use a separately provisioned worker image and explicit CUDA support.

Model files should live outside source control in a configured model cache or mounted volume. Pin model identifiers and revisions in deployment configuration, record checksums where possible, and never download models during API startup.

See each subdirectory README for requirements and operational constraints.
