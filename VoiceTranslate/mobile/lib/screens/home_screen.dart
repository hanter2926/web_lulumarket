import 'package:flutter/material.dart';

import '../routing/app_router.dart';
import '../services/auth_service.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Home')),
        body: Center(
          child: FilledButton.tonal(
            onPressed: () async {
              await AuthService().logout();
              if (context.mounted) Navigator.pushReplacementNamed(context, AppRouter.login);
            },
            child: const Text('Log out'),
          ),
        ),
      );
}
