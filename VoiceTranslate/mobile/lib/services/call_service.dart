class CallRequest {
  const CallRequest({
    required this.contactName,
    required this.sourceLanguage,
    required this.targetLanguage,
  });

  final String contactName;
  final String sourceLanguage;
  final String targetLanguage;
}

abstract interface class CallService {
  Future<void> connect(CallRequest request);
}

class CallConnectionException implements Exception {
  const CallConnectionException(this.message);

  final String message;
}

class UnavailableCallService implements CallService {
  const UnavailableCallService();

  @override
  Future<void> connect(CallRequest request) async {
    throw const CallConnectionException(
      'Live calling is not connected in this version of the app.',
    );
  }
}