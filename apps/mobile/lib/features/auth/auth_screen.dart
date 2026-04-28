import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth_provider.dart';

class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({super.key});

  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final _phoneCtl = TextEditingController(text: '+');
  final _codeCtl = TextEditingController();
  bool _codeSent = false;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _phoneCtl.dispose();
    _codeCtl.dispose();
    super.dispose();
  }

  Future<void> _sendCode() async {
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      await ref.read(authProvider.notifier).sendOtp(_phoneCtl.text.trim());
      setState(() => _codeSent = true);
    } catch (err) {
      setState(() => _error = err.toString());
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _verify() async {
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      await ref.read(authProvider.notifier).verifyOtp(_codeCtl.text.trim());
      // Router redirect picks it up.
    } catch (err) {
      setState(() => _error = err.toString());
    } finally {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('ReliefOps',
                    style: Theme.of(context).textTheme.displaySmall,
                    textAlign: TextAlign.center),
                const SizedBox(height: 8),
                Text(
                  'Field volunteer sign-in',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                const SizedBox(height: 32),
                if (!_codeSent) ...[
                  TextField(
                    controller: _phoneCtl,
                    keyboardType: TextInputType.phone,
                    decoration: const InputDecoration(
                      labelText: 'Phone (E.164)',
                      hintText: '+8801712345678',
                    ),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: _busy ? null : _sendCode,
                    child: Text(_busy ? 'Sending…' : 'Send code'),
                  ),
                ] else ...[
                  TextField(
                    controller: _codeCtl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: '6-digit code'),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: _busy ? null : _verify,
                    child: Text(_busy ? 'Verifying…' : 'Verify & sign in'),
                  ),
                  TextButton(
                    onPressed: _busy ? null : () => setState(() => _codeSent = false),
                    child: const Text('Use a different number'),
                  ),
                ],
                if (_error != null) ...[
                  const SizedBox(height: 16),
                  Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
