import '../core/config/app_config.dart';
import '../core/constants/api_paths.dart';
import '../core/network/api_client.dart';
import '../core/storage/token_storage.dart';
import '../models/user.dart';

class AuthService {
  AuthService({ApiClient? client, TokenStorage? storage})
      : _client = client ?? ApiClient(baseUrl: AppConfig.apiBaseUrl),
        _storage = storage ?? TokenStorage();

  final ApiClient _client;
  final TokenStorage _storage;

  Future<User> register(String email, String password, String displayName) async {
    final json = await _client.post(ApiPaths.register, body: {
      'email': email,
      'password': password,
      'display_name': displayName,
    });
    return User.fromJson(json);
  }

  Future<User> login(String email, String password) async {
    final tokens = await _client.post(ApiPaths.login, body: {'email': email, 'password': password});
    await _storage.saveTokens(tokens['access_token'] as String, tokens['refresh_token'] as String);
    return currentUser();
  }

  Future<User> currentUser() async {
    final token = await _storage.accessToken();
    if (token == null) throw const ApiException(401, 'Not authenticated');
    return User.fromJson(await _client.get(ApiPaths.currentUser, accessToken: token));
  }

  Future<void> logout() async {
    final token = await _storage.accessToken();
    if (token != null) {
      try {
        await _client.post(ApiPaths.logout, accessToken: token);
      } finally {
        await _storage.clear();
      }
    }
  }
}
