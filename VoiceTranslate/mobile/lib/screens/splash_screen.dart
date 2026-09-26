import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';
import '../models/user.dart';
import '../routing/app_router.dart';
import '../services/auth_service.dart';
import '../widgets/app_surface.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _continue();
  }

  Future<void> _continue() async {
    await Future<void>.delayed(const Duration(milliseconds: 650));
    User? user;
    try {
      user = await AuthService().currentUser();
    } catch (_) {
      user = null;
    }
    if (!mounted) return;
    Navigator.pushReplacementNamed(
      context,
      user == null ? AppRouter.login : AppRouter.home,
      arguments: user,
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: AppBackdrop(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const BrandLockup(),
                const SizedBox(height: 28),
                const SizedBox.square(
                  dimension: 21,
                  child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.mint),
                ),
              ],
            ),
          ),
        ),
      );
}