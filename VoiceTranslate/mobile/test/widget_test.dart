// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:voice_translate_mobile/main.dart';

void main() {
  testWidgets('VoiceTranslate app starts on its splash screen', (WidgetTester tester) async {
    await tester.pumpWidget(const VoiceTranslateApp());

    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.title, 'VoiceTranslate');
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 650));
    await tester.pump(const Duration(milliseconds: 500));
  });
}
