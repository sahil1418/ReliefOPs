# ReliefOps Mobile (Flutter)

Field volunteer / driver app — offline-first, low-connectivity friendly.

## Status

**Code-complete for COMMIT 3** — phone-OTP auth flow, Riverpod auth provider,
Hive role cache, go_router redirects, and a placeholder home screen are all in
[lib/](lib/). They have not been compiled because the Flutter SDK is not yet
installed on this machine. Run `flutter pub get && flutter run` once you have
the SDK and an Android emulator.

## To bootstrap (when you're ready)

```bash
# 1. Install Flutter SDK to D:\flutter (or wherever)
#    https://docs.flutter.dev/get-started/install/windows

# 2. From the repo root:
cd apps
rm -rf mobile/README.md mobile/pubspec.yaml   # back up first if you've edited them
flutter create --org com.reliefops --project-name relief_mobile mobile
cd mobile

# 3. Restore pubspec.yaml (this directory's existing one) and run:
flutter pub get
flutter run            # against an Android emulator or connected device
```

## What lands here in later commits

| Commit | Adds |
|---|---|
| 3 | Phone-OTP auth screen, Riverpod auth provider, `/api/auth/me` sync, Hive role cache |
| 6 | (none — backend) |
| 8 | Background `geolocator` GPS service → RTDB, Hive offline queue, foreground notification |
| 9 | Photo capture → `/api/predict/damage-assess` |
| 10 | FCM push handlers, route-update banner |

See [BLUEPRINT.md](../../../compass_artifact_wf-543b7ba2-928e-4f88-94ab-da72e5c36b42_text_markdown.md) Phase 6 Module 1, 6, 12 for full specs.
