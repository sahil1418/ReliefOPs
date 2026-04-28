/// Riverpod auth state for the volunteer app.
///
/// - Watches Firebase `authStateChanges()` so sign-in / sign-out drive the router.
/// - On sign-in, fetches `/api/auth/me` to pick up the role custom claim and caches
///   it to Hive so the home screen has a role even when offline.
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive/hive.dart';

import '../../core/api_client.dart';

class CurrentUser {
  CurrentUser({
    required this.uid,
    this.email,
    this.phone,
    this.displayName,
    this.role,
    this.orgId,
  });

  final String uid;
  final String? email;
  final String? phone;
  final String? displayName;
  final String? role;
  final String? orgId;

  Map<String, dynamic> toJson() => {
        'uid': uid,
        'email': email,
        'phone': phone,
        'displayName': displayName,
        'role': role,
        'orgId': orgId,
      };

  factory CurrentUser.fromJson(Map<dynamic, dynamic> json) => CurrentUser(
        uid: json['uid'] as String,
        email: json['email'] as String?,
        phone: json['phone'] as String?,
        displayName: json['displayName'] as String?,
        role: json['role'] as String?,
        orgId: json['orgId'] as String?,
      );
}

class AuthNotifier extends AsyncNotifier<CurrentUser?> {
  late final ApiClient _api;
  late final Box<dynamic> _box;

  @override
  Future<CurrentUser?> build() async {
    _api = ref.read(apiClientProvider);
    _box = Hive.box<dynamic>('user_cache');

    // Stream-driven: any auth change re-runs build() via invalidateSelf below.
    final fbUser = FirebaseAuth.instance.currentUser;
    if (fbUser == null) {
      await _box.delete('current');
      return null;
    }

    // Try fresh /api/auth/me; fall back to Hive when offline.
    try {
      final data = await _api.get<Map<String, dynamic>>('/api/auth/me');
      final user = CurrentUser(
        uid: data['uid'] as String,
        email: data['email'] as String?,
        phone: data['phone'] as String?,
        displayName: fbUser.displayName,
        role: data['role'] as String?,
        orgId: data['orgId'] as String?,
      );
      await _box.put('current', user.toJson());
      return user;
    } catch (_) {
      final cached = _box.get('current') as Map<dynamic, dynamic>?;
      if (cached != null) return CurrentUser.fromJson(cached);
      return CurrentUser(uid: fbUser.uid, email: fbUser.email, phone: fbUser.phoneNumber);
    }
  }

  ConfirmationResult? _confirmation;

  Future<void> sendOtp(String e164PhoneNumber) async {
    state = const AsyncLoading();
    try {
      final confirmation = await FirebaseAuth.instance.signInWithPhoneNumber(e164PhoneNumber);
      _confirmation = confirmation;
      state = const AsyncData(null);
    } catch (err, st) {
      state = AsyncError(err, st);
      rethrow;
    }
  }

  Future<void> verifyOtp(String code) async {
    if (_confirmation == null) {
      throw StateError('Call sendOtp() first.');
    }
    state = const AsyncLoading();
    try {
      await _confirmation!.confirm(code);
      _confirmation = null;
      ref.invalidateSelf(); // re-run build() with the new user
    } catch (err, st) {
      state = AsyncError(err, st);
      rethrow;
    }
  }

  Future<void> signOut() async {
    state = const AsyncLoading();
    try {
      await FirebaseAuth.instance.signOut();
      await _box.delete('current');
      ref.invalidateSelf();
    } catch (err, st) {
      state = AsyncError(err, st);
      rethrow;
    }
  }
}

final authProvider = AsyncNotifierProvider<AuthNotifier, CurrentUser?>(AuthNotifier.new);

/// Side stream that re-invalidates the notifier when Firebase auth state flips
/// (e.g. token expired and rotated). Wire this from main.dart if you want the
/// notifier to react to background sign-outs.
final firebaseAuthStateProvider = StreamProvider<User?>(
  (_) => FirebaseAuth.instance.authStateChanges(),
);
