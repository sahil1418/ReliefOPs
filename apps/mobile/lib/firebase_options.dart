/// Generated-style Firebase config — replace with the real `flutterfire configure`
/// output once you have a Firebase project linked.
///
/// For COMMIT 3 the values are placeholders so the file compiles. The
/// emulator wiring below routes the SDK to local 127.0.0.1:9099 / :8080 / :9000
/// when `--dart-define=USE_EMULATORS=true` is passed.
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (defaultTargetPlatform == TargetPlatform.android) {
      return android;
    }
    throw UnsupportedError('Add iOS/web options after running `flutterfire configure`.');
  }

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'demo-api-key',
    appId: '1:0000000000:android:0000000000000000',
    messagingSenderId: '0000000000',
    projectId: 'relief-logistics',
    storageBucket: 'relief-logistics.appspot.com',
    databaseURL: 'https://relief-logistics-default-rtdb.firebaseio.com',
  );
}
