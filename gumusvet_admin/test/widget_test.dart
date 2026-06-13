import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:gumusvet_admin/main.dart';

void main() {
  testWidgets('Admin uygulaması giriş ekranını açar',
      (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAdminTheme(Brightness.light),
        home: LoginPage(
          storage: const FlutterSecureStorage(),
          themeMode: ThemeMode.light,
          onToggleTheme: () {},
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Giriş Yap'), findsWidgets);
    expect(find.text('Beni hatırla'), findsOneWidget);
    expect(find.text('Şifremi unuttum'), findsOneWidget);
  });
}
