import 'package:flutter_test/flutter_test.dart';

import 'package:voice_translate_mobile/main.dart';

void main() {
  testWidgets('shows the login screen', (tester) async {
    await tester.pumpWidget(const VoiceTranslateApp());
    expect(find.text('Sign in'), findsOneWidget);
  });
}
