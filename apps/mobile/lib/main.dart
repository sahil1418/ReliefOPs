/// ReliefOps mobile entry point.
///
/// COMMIT 3: phone-OTP sign-in lands the volunteer on `/home`. The home screen
/// is intentionally minimal — assigned routes, GPS service, and POD capture all
/// land in COMMITs 6 and 8.
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'core/router.dart';
import 'core/theme.dart';
import 'firebase_options.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  await Hive.initFlutter();
  await Hive.openBox<dynamic>('user_cache');
  runApp(const ProviderScope(child: ReliefApp()));
}

class ReliefApp extends ConsumerWidget {
  const ReliefApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'ReliefOps',
      debugShowCheckedModeBanner: false,
      theme: reliefTheme,
      routerConfig: router,
    );
  }
}
