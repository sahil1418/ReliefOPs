import 'dart:convert';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

const String kApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000', // Android emulator → host loopback
);

class ApiException implements Exception {
  ApiException(this.code, this.message, this.status);
  final String code;
  final String message;
  final int status;

  @override
  String toString() => 'ApiException($status, $code): $message';
}

/// Adds Authorization: Bearer <ID token> automatically when a Firebase user is signed in.
class ApiClient {
  ApiClient(this._client);
  final http.Client _client;

  Future<Map<String, String>> _headers({bool body = false}) async {
    final headers = <String, String>{'Accept': 'application/json'};
    if (body) headers['Content-Type'] = 'application/json';
    final user = FirebaseAuth.instance.currentUser;
    if (user != null) {
      final token = await user.getIdToken();
      if (token != null) headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Future<T> get<T>(String path) async {
    final res = await _client.get(Uri.parse('$kApiBaseUrl$path'), headers: await _headers());
    return _decode<T>(res);
  }

  Future<T> post<T>(String path, [Object? body]) async {
    final res = await _client.post(
      Uri.parse('$kApiBaseUrl$path'),
      headers: await _headers(body: body != null),
      body: body == null ? null : jsonEncode(body),
    );
    return _decode<T>(res);
  }

  T _decode<T>(http.Response res) {
    final payload = jsonDecode(res.body) as Map<String, dynamic>;
    final error = payload['error'] as Map<String, dynamic>?;
    if (error != null || res.statusCode >= 400) {
      throw ApiException(
        error?['code'] as String? ?? 'HTTP_${res.statusCode}',
        error?['message'] as String? ?? res.reasonPhrase ?? 'Request failed',
        res.statusCode,
      );
    }
    return payload['data'] as T;
  }
}

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient(http.Client()));
