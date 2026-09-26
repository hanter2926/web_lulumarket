import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:voice_translate_mobile/core/theme/app_theme.dart';
import 'package:voice_translate_mobile/screens/auth/login_screen.dart';
import 'package:voice_translate_mobile/screens/auth/register_screen.dart';
import 'package:voice_translate_mobile/screens/call_screen.dart';

Widget _testApp(Widget screen) => MaterialApp(
      theme: AppTheme.dark,
      home: screen,
    );

void main() {
  testWidgets('login screen validates before submitting', (tester) async {
    await tester.pumpWidget(_testApp(const LoginScreen()));
    expect(find.text('Speak beyond\nborders.'), findsOneWidget);
    await tester.tap(find.text('Sign in'));
    await tester.pump();
    expect(find.text('Enter a valid email address'), findsOneWidget);
  });

  testWidgets('registration screen explains the required password policy', (tester) async {
    await tester.pumpWidget(_testApp(const RegisterScreen()));
    expect(find.text('Create account'), findsOneWidget);
    expect(find.text('8+ characters with uppercase, lowercase, and a number'), findsOneWidget);
  });

  testWidgets('call screen clearly indicates it is disconnected', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(_testApp(const CallScreen(contactName: 'Sofia Martinez')));
    expect(find.text('Not connected'), findsOneWidget);
    expect(find.text('Live calling is not available yet.'), findsOneWidget);
    await tester.tap(find.text('Try connection'));
    await tester.pumpAndSettle();
    expect(find.text('Live calling is not connected in this version of the app.'), findsOneWidget);
  });
}
