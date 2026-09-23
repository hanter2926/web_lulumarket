# VoiceTranslate Mobile

Flutter client foundation for the existing FastAPI backend. Calling, WebSocket audio, microphone capture, VAD, Whisper, translation, and TTS are intentionally not implemented.

## API configuration

The default URL is `http://localhost:8000`. Configure the target at runtime:

```text
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Use a LAN URL for a physical device and an HTTPS URL for production. No production secret is stored in the client.

## Run

```text
flutter pub get
flutter analyze
flutter test
```
