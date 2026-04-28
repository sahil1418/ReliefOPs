/// Background GPS streamer for the volunteer app.
///
/// Pipeline (BLUEPRINT Phase 6 Module 6):
///   geolocator → every 15s →
///     if online → write to RTDB `/locations/{uid}` + POST /api/tracking/event
///     else → enqueue in Hive box "tracking_outbox"; flush on reconnect.
///
/// Foreground notification keeps the OS from killing the stream during a delivery.
library;

import 'dart:async';
import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:geolocator/geolocator.dart';
import 'package:hive/hive.dart';

import '../../core/api_client.dart';

const String _outboxBox = 'tracking_outbox';

class LocationService {
  LocationService(this._api);
  final ApiClient _api;

  StreamSubscription<Position>? _sub;
  String? _activeShipmentId;

  Future<void> ensurePermissions() async {
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.deniedForever) {
      throw StateError('Location permission permanently denied');
    }
  }

  Future<void> start({String? shipmentId}) async {
    if (_sub != null) await stop();
    _activeShipmentId = shipmentId;
    await ensurePermissions();

    final settings = AndroidSettings(
      accuracy: LocationAccuracy.high,
      intervalDuration: const Duration(seconds: 15),
      distanceFilter: 5,
      foregroundNotificationConfig: const ForegroundNotificationConfig(
        notificationTitle: 'ReliefOps · on route',
        notificationText: 'Sharing GPS for relief coordination',
        enableWakeLock: true,
        notificationIcon: AndroidResource(name: 'mipmap/ic_launcher'),
      ),
    );

    _sub = Geolocator.getPositionStream(locationSettings: settings).listen(_onPosition);
  }

  Future<void> stop() async {
    await _sub?.cancel();
    _sub = null;
    _activeShipmentId = null;
  }

  Future<void> _onPosition(Position pos) async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return;

    final entry = {
      'lat': pos.latitude,
      'lng': pos.longitude,
      'ts': DateTime.now().toUtc().toIso8601String(),
      'speedKmh': (pos.speed * 3.6).clamp(0, 400),
      'accuracy': pos.accuracy,
      'heading': pos.heading,
      'shipmentId': _activeShipmentId,
      'volunteerId': user.uid,
    };

    bool wrote = false;
    try {
      // 1. RTDB write (cheap, designed for high-frequency presence-style data).
      await FirebaseDatabase.instance
          .ref('locations/${user.uid}')
          .set(entry);
      // 2. API event for Firestore aggregation + Pub/Sub fanout.
      await _api.post('/api/tracking/event', {
        'shipmentId': _activeShipmentId,
        'location': {'lat': pos.latitude, 'lng': pos.longitude},
        'speedKmh': entry['speedKmh'],
        'accuracy': pos.accuracy,
        'heading': pos.heading,
      });
      wrote = true;
    } catch (_) {
      // Network down — queue locally; ConnectivityService flushes on reconnect.
      final box = await Hive.openBox<String>(_outboxBox);
      await box.add(jsonEncode(entry));
    }

    if (wrote) {
      // Best-effort: drain a few queued items per successful write.
      await _drainOutboxBatch();
    }
  }

  Future<void> _drainOutboxBatch({int maxItems = 5}) async {
    final box = await Hive.openBox<String>(_outboxBox);
    if (box.isEmpty) return;
    final keys = box.keys.toList().take(maxItems).toList();
    for (final k in keys) {
      final raw = box.get(k);
      if (raw == null) continue;
      try {
        final entry = jsonDecode(raw) as Map<String, dynamic>;
        await _api.post('/api/tracking/event', {
          'shipmentId': entry['shipmentId'],
          'location': {'lat': entry['lat'], 'lng': entry['lng']},
          'speedKmh': entry['speedKmh'],
          'accuracy': entry['accuracy'],
          'heading': entry['heading'],
        });
        await box.delete(k);
      } catch (_) {
        // Stop on first failure; we'll retry on the next online ping.
        break;
      }
    }
  }
}
