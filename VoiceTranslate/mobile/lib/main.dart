import 'package:flutter/material.dart';

import 'core/theme/app_theme.dart';
import 'routing/app_router.dart';

void main() {
  runApp(const VoiceTranslateApp());
}

class VoiceTranslateApp extends StatelessWidget {
  const VoiceTranslateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VoiceTranslate',
      theme: AppTheme.light,
      initialRoute: AppRouter.login,
      onGenerateRoute: AppRouter.onGenerateRoute,
    );
  }
}
