# WebSocket Protocol

## Status

The secure WebSocket foundation is implemented at `/ws/calls/{call_id}`. Audio and translation messages are intentionally not implemented yet.

Clients authenticate with the existing access JWT as the `token` query parameter. The server validates the JWT signature, expiration, token type, active user, and token version before accepting the socket. It then verifies that the user is the call initiator or an existing call participant. Use HTTPS/WSS in deployed environments; tokens are never logged.

## Implemented control messages

```json
{"type":"ping"}
{"type":"language.change","language":"hi"}
```

## Implemented server events

```json
{"type":"connection.ready","call_id":"...","user_id":"..."}
{"type":"pong"}
{"type":"language.changed","language":"hi"}
{"type":"error","code":"...","message":"..."}
```

Malformed JSON, unsupported message types, unsupported languages, and binary frames receive an `INVALID_MESSAGE` error. Disconnects remove the socket from the connection manager. Audio frames, reconnects, and translation events remain planned.
