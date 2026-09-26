# VoiceTranslate Mobile

Flutter client for the existing FastAPI backend. Login, registration, profile loading, and logout use the backend's existing API schemas. Contact entries are labeled sample data. The call UI uses a separate `CallService` boundary backed by an unavailable implementation. WebSocket audio, microphone capture, VAD, Whisper, translation, and TTS are not connected; the in-call screen is an explicit disconnected preview.

## API configuration

The default URL is `http://10.0.2.2:8000` for Android Emulator access to a host-machine backend. Override it at runtime:

```text
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Use the computer's LAN address for a physical device and an HTTPS URL for production. No production secret is stored in the client.

Android builds connecting to a local `http://` backend need internet permission and cleartext HTTP enabled in the debug Android manifest. Keep cleartext disabled for release builds and use HTTPS in production.

## Run

```text
flutter pub get
flutter analyze
flutter test
```

This checkout currently contains the Flutter package source but no generated `android/` or `ios/` platform folders. After installing Flutter, add the target platform scaffolding from this directory with `flutter create --platforms=android,ios .` before building for devices.
