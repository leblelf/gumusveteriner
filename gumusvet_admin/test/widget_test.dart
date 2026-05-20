import 'package:flutter_test/flutter_test.dart';

import 'package:gumusvet_admin/main.dart';

void main() {
  testWidgets('Admin uygulamasi login ekranini acar', (WidgetTester tester) async {
    await tester.pumpWidget(const GumusVetAdminApp());
    await tester.pump();

    expect(find.text('Giriş Yap'), findsWidgets);
  });
}
