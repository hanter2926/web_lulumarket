# WebSocket Protocol

## Status

The call WebSocket is planned and is not currently implemented. No client should connect to `/ws/calls/{call_id}` yet.

## Planned control messages

```json
{"type":"audio_start"}
{"type":"language_change","source_language":"en","target_language":"hi"}
{"type":"audio_stop"}
{"type":"ping"}
```

## Planned server events

```json
{"type":"transcript","text":"Hello"}
{"type":"translation","text":"नमस्ते"}
{"type":"processing","status":"processing"}
{"type":"error","code":"...","message":"..."}
```

Authentication, participant authorization, binary PCM frames, reconnects, and heartbeat behavior will be specified when the WebSocket phase begins.
