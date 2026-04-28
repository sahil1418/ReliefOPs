/// Listens for connectivity changes and flushes the offline queue when the
/// device comes back online. Pairs with [LocationService]'s in-line draining.
library;

import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:hive/hive.dart';

import '../../core/api_client.dart';

const String _outboxBox = 'tracking_outbox';

class ConnectivityService {
  ConnectivityService(this._api);
  final ApiClient _api;

  StreamSubscription<List<ConnectivityResult>>? _sub;

  Future<void> start() async {
    _sub = Connectivity().onConnectivityChanged.listen((results) async {
      final online = results.any((r) => r != ConnectivityResult.none);
      if (online) {
        await _flushOutbox();
      }
    });
  }

  Future<void> stop() async {
    await _sub?.cancel();
    _sub = null;
  }

  Future<int> _flushOutbox() async {
    final box = await Hive.openBox<String>(_outboxBox);
    if (box.isEmpty) return 0;
    int sent = 0;
    final keys = List.of(box.keys);
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
        sent++;
      } catch (_) {
        // Network flap — abort the flush; another reconnect event will retry.
        break;
      }
    }
    return sent;
  }
}
