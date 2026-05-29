import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'core/constants/app_constants.dart';
import 'core/network/api_service.dart';

// -----------------------------------------------------------------------------
// Gumus Vet Admin
// -----------------------------------------------------------------------------
// Bu dosya Flutter admin uygulamasinin ana dosyasidir.
//
// Okuma sirasi:
// 1. Tema ve uygulama girisi
// 2. Login ekrani
// 3. AdminShell: ust bar, sol menu ve sayfa gecisleri
// 4. Yonetim sayfalari: Dashboard, Randevular, Petler, Yatan Hastalar...
// 5. Veri modelleri ve ornek kayitlar
// -----------------------------------------------------------------------------

void main() {
  runApp(const GumusVetAdminApp());
}

class GumusVetAdminApp extends StatefulWidget {
  const GumusVetAdminApp({super.key});

  @override
  State<GumusVetAdminApp> createState() => _GumusVetAdminAppState();
}

class _GumusVetAdminAppState extends State<GumusVetAdminApp> {
  ThemeMode themeMode = ThemeMode.light;

  void toggleTheme() {
    setState(() {
      themeMode =
          themeMode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConstants.appName,
      debugShowCheckedModeBanner: false,
      theme: buildAdminTheme(Brightness.light),
      darkTheme: buildAdminTheme(Brightness.dark),
      themeMode: themeMode,
      home: AuthGate(themeMode: themeMode, onToggleTheme: toggleTheme),
    );
  }
}

ThemeData buildAdminTheme(Brightness brightness) {
  // Web sitesindeki yesil/temiz klinik hissini admin uygulamasina tasir.
  final dark = brightness == Brightness.dark;
  final background = dark ? const Color(0xFF07110F) : const Color(0xFFF4F8F6);
  final surface = dark ? const Color(0xFF101C19) : Colors.white;
  final border = dark ? const Color(0xFF263A34) : const Color(0xFFE1EEE9);
  final fill = dark ? const Color(0xFF0D211D) : const Color(0xFFF2FBF8);
  const siteTeal = Color(0xFF0F6E56);
  const siteTealMid = Color(0xFF1D9E75);
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    scaffoldBackgroundColor: background,
    colorScheme: ColorScheme.fromSeed(
      seedColor: siteTeal,
      brightness: brightness,
      primary: dark ? const Color(0xFF4BD0A7) : siteTeal,
      secondary: dark ? const Color(0xFFF1B35D) : siteTealMid,
    ),
    fontFamily: 'Arial',
    cardTheme: CardThemeData(
      elevation: 0,
      color: surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: border),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: fill,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide:
            BorderSide(color: dark ? const Color(0xFF4BD0A7) : siteTeal),
      ),
    ),
    dividerTheme: DividerThemeData(color: border),
  );
}

Color appSurface(BuildContext context) =>
    Theme.of(context).cardTheme.color ?? Theme.of(context).colorScheme.surface;
Color appBackground(BuildContext context) =>
    Theme.of(context).scaffoldBackgroundColor;
Color appBorder(BuildContext context) =>
    Theme.of(context).dividerTheme.color ?? const Color(0xFFDDE7ED);
Color appMuted(BuildContext context) =>
    Theme.of(context).colorScheme.onSurface.withOpacity(.62);
Color appOrange(BuildContext context) => Theme.of(context).colorScheme.primary;

class ApiClient {
  // Backend API ile konusmak icin kucuk bir yardimci sinif.
  // Token saklama isi login sonrasinda FlutterSecureStorage ile yapilir.
  ApiClient(this.storage);

  final FlutterSecureStorage storage;

  Future<Map<String, dynamic>> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? body,
  }) {
    return ApiService.instance.request(path, method: method, body: body);
  }
}

class AuthGate extends StatefulWidget {
  const AuthGate(
      {super.key, required this.themeMode, required this.onToggleTheme});

  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  final storage = const FlutterSecureStorage();
  bool loading = true;
  String? token;

  @override
  void initState() {
    super.initState();
    _loadSession();
  }

  Future<void> _loadSession() async {
    final prefs = await SharedPreferences.getInstance();
    final remember = prefs.getBool(AppConstants.rememberMeKey) ?? true;
    if (!remember) {
      await storage.delete(key: AppConstants.tokenKey);
    }
    final value = await storage.read(key: AppConstants.tokenKey);
    if (!mounted) return;
      setState(() {
        token = value;
        loading = false;
      });
  }

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return token == null
        ? LoginPage(
            storage: storage,
            themeMode: widget.themeMode,
            onToggleTheme: widget.onToggleTheme)
        : AdminShell(
            storage: storage,
            themeMode: widget.themeMode,
            onToggleTheme: widget.onToggleTheme);
  }
}

class LoginPage extends StatefulWidget {
  const LoginPage(
      {super.key,
      required this.storage,
      required this.themeMode,
      required this.onToggleTheme});

  final FlutterSecureStorage storage;
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final username = TextEditingController(text: 'gumusveterinermuayenehanesi@gmail.com');
  final password = TextEditingController();
  bool loading = false;
  bool rememberMe = true;
  String? error;

  @override
  void initState() {
    super.initState();
    _loadRememberedLogin();
  }

  Future<void> _loadRememberedLogin() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(AppConstants.savedUsernameKey);
    final remember = prefs.getBool(AppConstants.rememberMeKey) ?? true;
    if (!mounted) return;
    setState(() {
      rememberMe = remember;
      if (saved != null && saved.isNotEmpty) username.text = saved;
    });
  }

  Future<void> login() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final response = await ApiClient(widget.storage).request(
        AppConstants.loginEndpoint,
        method: 'POST',
        body: {'username': username.text.trim(), 'password': password.text},
      );
      final token = response['data']['token'] as String;
      await widget.storage.write(key: AppConstants.tokenKey, value: token);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(AppConstants.rememberMeKey, rememberMe);
      if (rememberMe) {
        await prefs.setString(AppConstants.savedUsernameKey, username.text.trim());
      } else {
        await prefs.remove(AppConstants.savedUsernameKey);
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => AdminShell(
            storage: widget.storage,
            themeMode: widget.themeMode,
            onToggleTheme: widget.onToggleTheme,
          ),
        ),
      );
    } catch (e) {
      final message = e.toString().replaceFirst('Exception: ', '');
      setState(() => error = message.isEmpty ? 'Giriş başarısız.' : message);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> forgotPassword() async {
    final email = username.text.trim();
    if (!email.contains('@')) {
      setState(() => error = 'Şifre sıfırlama için e-posta adresinizi yazın.');
      return;
    }
    try {
      await ApiClient(widget.storage).request(
        AppConstants.forgotPasswordEndpoint,
        method: 'POST',
        body: {'email': email},
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Şifre sıfırlama bağlantısı e-posta adresine gönderildi.')));
    } catch (e) {
      setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: appBackground(context),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 430),
          child: Card(
            margin: const EdgeInsets.all(20),
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const BrandHeader(compact: false),
                  const SizedBox(height: 26),
                  TextField(
                    controller: username,
                    decoration: const InputDecoration(
                      labelText: 'Kullanıcı adı',
                      prefixIcon: Icon(Icons.person_outline),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: password,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'Şifre',
                      prefixIcon: Icon(Icons.lock_outline),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Checkbox(
                        value: rememberMe,
                        onChanged: (value) =>
                            setState(() => rememberMe = value ?? true),
                      ),
                      const Text('Beni hatırla'),
                      const Spacer(),
                      TextButton(
                        onPressed: forgotPassword,
                        child: const Text('Şifremi unuttum'),
                      ),
                    ],
                  ),
                  if (error != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text(error!,
                          style: const TextStyle(color: Color(0xFFD93025))),
                    ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: loading ? null : login,
                    icon: const Icon(Icons.login),
                    label: Text(loading ? 'Giriş yapılıyor...' : 'Giriş Yap'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AdminShell extends StatefulWidget {
  const AdminShell(
      {super.key,
      required this.storage,
      required this.themeMode,
      required this.onToggleTheme});

  final FlutterSecureStorage storage;
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
  // Admin girisinden sonra gorunen ana iskelet.
  // selected sol menude hangi sayfanin acik oldugunu tutar.
  int selected = 2;
  String query = '';

  @override
  Widget build(BuildContext context) {
    final api = ApiClient(widget.storage);
    final pages = [
      DashboardPage(api: api),
      AppointmentPage(api: api, query: query),
      PetListPage(query: query),
      HospitalizedPage(query: query),
      ProductPage(api: api, query: query),
      OrdersPage(api: api, query: query),
      ReviewReplyPage(api: api, query: query),
      ContactReplyPage(api: api, query: query),
      SiteTextPage(api: api, query: query),
      UserManagementPage(api: api, query: query),
      SendSmsPage(api: api),
      AppointmentSlotsPage(api: api),
      ClinicSettingsPage(storage: widget.storage),
      AdminProfilePage(api: api, storage: widget.storage),
    ];
    final mobile = MediaQuery.sizeOf(context).width < 820;
    final content = Column(
      children: [
        TopBar(
          onLogout: logout,
          onProfile: () => setState(() => selected = 13),
          isDark: widget.themeMode == ThemeMode.dark,
          onToggleTheme: widget.onToggleTheme,
        ),
        Expanded(child: pages[selected]),
      ],
    );

    return Scaffold(
      drawer: mobile
          ? Drawer(
              child: Sidebar(
                selected: selected,
                onSelected: (value) {
                  Navigator.pop(context);
                  setState(() => selected = value);
                },
                onLogout: logout,
              ),
            )
          : null,
      body: Row(
        children: [
          if (!mobile)
            Sidebar(
              selected: selected,
              onSelected: (value) => setState(() => selected = value),
              onLogout: logout,
            ),
          Expanded(
            child: mobile
                ? Builder(
                    builder: (context) => Column(
                      children: [
                        Container(
                          height: 54,
                          color: appSurface(context),
                          alignment: Alignment.centerLeft,
                          child: IconButton(
                            icon: const Icon(Icons.menu),
                            onPressed: () => Scaffold.of(context).openDrawer(),
                          ),
                        ),
                        Expanded(child: content),
                      ],
                    ),
                  )
                : content,
          ),
        ],
      ),
    );
  }

  Future<void> logout() async {
    await widget.storage.delete(key: AppConstants.tokenKey);
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => LoginPage(
          storage: widget.storage,
          themeMode: widget.themeMode,
          onToggleTheme: widget.onToggleTheme,
        ),
      ),
    );
  }
}

class Sidebar extends StatelessWidget {
  const Sidebar({
    super.key,
    required this.selected,
    required this.onSelected,
    required this.onLogout,
  });

  final int selected;
  final ValueChanged<int> onSelected;
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context) {
    final items = [
      MenuItem(Icons.dashboard_outlined, 'Dashboard'),
      MenuItem(Icons.calendar_month_outlined, 'Randevular'),
      MenuItem(Icons.pets_outlined, 'Pet Listesi'),
      MenuItem(Icons.local_hospital_outlined, 'Yatan Hastalar'),
      MenuItem(Icons.inventory_2_outlined, 'Ürünler'),
      MenuItem(Icons.shopping_bag_outlined, 'Gelen Siparişler'),
      MenuItem(Icons.reviews_outlined, 'Yorumlar'),
      MenuItem(Icons.contact_mail_outlined, 'Sorular'),
      MenuItem(Icons.edit_note_outlined, 'Site Yazıları'),
      MenuItem(Icons.groups_outlined, 'Üyeler'),
      MenuItem(Icons.sms_outlined, 'SMS Gönder'),
      MenuItem(Icons.schedule_outlined, 'Randevu Saatleri'),
    ];
    return Container(
      width: 245,
      color: appSurface(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(24, 22, 24, 26),
            child: BrandHeader(compact: true),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.only(bottom: 18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (var i = 0; i < items.length; i++)
                    SidebarTile(
                      icon: items[i].icon,
                      label: items[i].label,
                      active: selected == i,
                      onTap: () => onSelected(i),
                    ),
                  const SizedBox(height: 12),
                  const Divider(height: 1),
                  SidebarTile(
                    icon: Icons.settings_outlined,
                    label: 'Ayarlar & Klinik',
                    active: selected == 12,
                    onTap: () => onSelected(12),
                  ),
                  SidebarTile(
                      icon: Icons.logout,
                      label: 'Çıkış Yap',
                      active: false,
                      onTap: onLogout),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class MenuItem {
  const MenuItem(this.icon, this.label);
  final IconData icon;
  final String label;
}

class SidebarTile extends StatelessWidget {
  const SidebarTile({
    super.key,
    required this.icon,
    required this.label,
    required this.active,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final activeBg = Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFF32261C)
        : const Color(0xFFFFF3E8);
    final activeBorder = Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFF5A3B22)
        : const Color(0xFFFFD9B7);
    final inactiveColor = appMuted(context);
    final activeColor = appOrange(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: active ? activeBg : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
            border: active ? Border.all(color: activeBorder) : null,
          ),
          child: Row(
            children: [
              Icon(icon, size: 20, color: active ? activeColor : inactiveColor),
              const SizedBox(width: 12),
              Text(
                label,
                style: TextStyle(
                  color: active ? activeColor : inactiveColor,
                  fontWeight: active ? FontWeight.w700 : FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class BrandHeader extends StatelessWidget {
  const BrandHeader({super.key, required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ClipOval(
          child: Image.asset(
            'assets/images/logo.jpeg',
            width: compact ? 40 : 48,
            height: compact ? 40 : 48,
            fit: BoxFit.cover,
          ),
        ),
        const SizedBox(width: 10),
        Flexible(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  'Gümüş Veteriner',
                  maxLines: 1,
                  style: TextStyle(
                    color: appOrange(context),
                    fontWeight: FontWeight.w800,
                    fontSize: compact ? 18 : 23,
                    height: 1,
                  ),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'PET YÖNETİMİ',
                maxLines: 1,
                style: TextStyle(
                  color: appMuted(context),
                  fontSize: compact ? 9 : 12,
                  letterSpacing: 1.5,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class TopBar extends StatelessWidget {
  const TopBar({
    super.key,
    required this.onLogout,
    required this.onProfile,
    required this.isDark,
    required this.onToggleTheme,
  });

  final VoidCallback onLogout;
  final VoidCallback onProfile;
  final bool isDark;
  final VoidCallback onToggleTheme;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 70,
      padding: const EdgeInsets.symmetric(horizontal: 28),
      color: appSurface(context),
      child: Row(
        children: [
          Expanded(child: PawPatternStrip(color: appOrange(context))),
          const Spacer(),
          IconButton(
            onPressed: onToggleTheme,
            icon: Icon(
                isDark ? Icons.light_mode_outlined : Icons.dark_mode_outlined),
            tooltip: isDark ? 'Açık moda geç' : 'Karanlık moda geç',
          ),
          CircleAvatar(
            backgroundColor: const Color(0xFFE1F5EE),
            child: Text('Profil'.substring(0, 1),
                style: const TextStyle(color: Color(0xFF0F6E56))),
          ),
          const SizedBox(width: 10),
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Dr. Gümüş',
                  style: TextStyle(fontWeight: FontWeight.w800)),
              Text('Klinik yöneticisi',
                  style: TextStyle(fontSize: 12, color: appMuted(context))),
            ],
          ),
          PopupMenuButton<String>(
            onSelected: (value) {
              if (value == 'profile') onProfile();
              if (value == 'logout') onLogout();
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'profile', child: Text('Profil')),
              PopupMenuItem(value: 'logout', child: Text('Çıkış Yap')),
            ],
          ),
        ],
      ),
    );
  }
}

class PageHeader extends StatelessWidget {
  const PageHeader({
    super.key,
    required this.title,
    required this.subtitle,
    this.action,
  });

  final String title;
  final String subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(28, 26, 28, 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        color: Theme.of(context).colorScheme.onSurface)),
                const SizedBox(height: 4),
                Text(subtitle, style: TextStyle(color: appMuted(context))),
              ],
            ),
          ),
          if (action != null) action!,
        ],
      ),
    );
  }
}

class PawPatternStrip extends StatelessWidget {
  const PawPatternStrip({super.key, required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    final icons = [
      Icons.pets,
      Icons.favorite_outline,
      Icons.cruelty_free_outlined,
      Icons.medical_services_outlined,
      Icons.pets,
    ];
    return SizedBox(
      height: 42,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          for (var i = 0; i < icons.length; i++)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Icon(
                icons[i],
                size: i.isEven ? 17 : 14,
                color: color.withOpacity(i.isEven ? .20 : .12),
              ),
            ),
        ],
      ),
    );
  }
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  final noteController = TextEditingController();
  List<String> notes = [];

  @override
  void initState() {
    super.initState();
    _loadNotes();
  }

  Future<void> _loadNotes() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() => notes = prefs.getStringList(AppConstants.quickNotesKey) ??
        ['Düşük stok ürünleri kontrol et', 'Aşı hatırlatmalarını gönder']);
  }

  Future<void> _saveNotes() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(AppConstants.quickNotesKey, notes);
  }

  void addNote() {
    final text = noteController.text.trim();
    if (text.isEmpty) return;
    setState(() {
      notes.insert(0, text);
      noteController.clear();
    });
    _saveNotes();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: Future.wait([
        widget.api.request(AppConstants.productsEndpoint),
        widget.api.request(AppConstants.servicesEndpoint),
        widget.api.request(AppConstants.appointmentsEndpoint),
      ]),
      builder: (context, snapshot) {
        final loading = snapshot.connectionState != ConnectionState.done;
        final data = snapshot.data as List<Map<String, dynamic>>?;
        final products = data == null ? 0 : (data[0]['data'] as List).length;
        final services = data == null ? 0 : (data[1]['data'] as List).length;
        final appointments =
            data == null ? 0 : (data[2]['data'] as List).length;
        final today = DateTime.now().toIso8601String().split('T').first;
        final todayAppointments = data == null
            ? <Map<String, dynamic>>[]
            : (data[2]['data'] as List)
                .whereType<Map<String, dynamic>>()
                .where((item) => item['appt_date']?.toString() == today)
                .toList();
        return ListView(
          padding: EdgeInsets.zero,
          children: [
            const PageHeader(
                title: 'Dashboard',
                subtitle: 'Kliniğinizin genel durumunu takip edin.'),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  MetricCard(
                      title: 'Toplam Pet',
                      value: '${samplePets.length}',
                      icon: Icons.pets_outlined,
                      loading: false),
                  MetricCard(
                      title: 'Randevular',
                      value: '$appointments',
                      icon: Icons.calendar_month_outlined,
                      loading: loading),
                  MetricCard(
                      title: 'Ürünler',
                      value: '$products',
                      icon: Icons.inventory_2_outlined,
                      loading: loading),
                  MetricCard(
                      title: 'Hizmetler',
                      value: '$services',
                      icon: Icons.medical_services_outlined,
                      loading: loading),
                ],
              ),
            ),
            const SizedBox(height: 18),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                      child: InfoPanel(
                          title: 'Bugünün Yapılacakları',
                          lines: todayAppointments.isEmpty
                              ? ['Bugün için kayıtlı randevu görünmüyor.']
                              : todayAppointments
                                  .map((item) =>
                                      '${item['appt_time']} • ${item['first_name']} ${item['last_name']} • ${item['service'] ?? item['pet_type']}')
                                  .toList())),
                  const SizedBox(width: 16),
                  Expanded(
                    child: QuickNotesCard(
                      notes: notes,
                      controller: noteController,
                      onAdd: addNote,
                      onDelete: (index) {
                        setState(() => notes.removeAt(index));
                        _saveNotes();
                      },
                    ),
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

class MetricCard extends StatelessWidget {
  const MetricCard({
    super.key,
    required this.title,
    required this.value,
    required this.icon,
    required this.loading,
  });

  final String title;
  final String value;
  final IconData icon;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 230,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              CircleAvatar(
                backgroundColor: const Color(0xFFE1F5EE),
                child: Icon(icon, color: const Color(0xFF0F6E56)),
              ),
              const SizedBox(width: 14),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: TextStyle(color: appMuted(context))),
                  Text(loading ? '...' : value,
                      style: const TextStyle(
                          fontSize: 24, fontWeight: FontWeight.w800)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class InfoPanel extends StatelessWidget {
  const InfoPanel({super.key, required this.title, required this.lines});

  final String title;
  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 12),
            for (final line in lines)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 7),
                child: Row(
                  children: [
                    Icon(Icons.check_circle_outline,
                        size: 18, color: appOrange(context)),
                    const SizedBox(width: 10),
                    Expanded(child: Text(line)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class QuickNotesCard extends StatelessWidget {
  const QuickNotesCard({
    super.key,
    required this.notes,
    required this.controller,
    required this.onAdd,
    required this.onDelete,
  });

  final List<String> notes;
  final TextEditingController controller;
  final VoidCallback onAdd;
  final ValueChanged<int> onDelete;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Hızlı Notlar',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: controller,
                    decoration: const InputDecoration(
                        isDense: true, hintText: 'Yeni not ekle...'),
                    onSubmitted: (_) => onAdd(),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(onPressed: onAdd, child: const Text('Ekle')),
              ],
            ),
            const SizedBox(height: 12),
            if (notes.isEmpty)
              Text('Henüz not yok.', style: TextStyle(color: appMuted(context))),
            for (var i = 0; i < notes.length; i++)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: Icon(Icons.check_circle_outline,
                    color: appOrange(context), size: 18),
                title: Text(notes[i]),
                trailing: IconButton(
                  icon: const Icon(Icons.close, size: 18),
                  onPressed: () => onDelete(i),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class PetListPage extends StatefulWidget {
  const PetListPage({super.key, required this.query});

  final String query;

  @override
  State<PetListPage> createState() => _PetListPageState();
}

class _PetListPageState extends State<PetListPage> {
  // Excel'den aktarilan petler burada listelenir. Arama, 12'li sayfalama ve
  // detay ekrani tamamen bu state icinde yonetilir.
  static const int pageSize = 12;
  String localQuery = '';
  bool grid = false;
  int pageIndex = 0;
  PetRecord? selectedPet;
  final List<PetRecord> pets = List.of(samplePets);

  @override
  void initState() {
    super.initState();
    _loadViewMode();
  }

  Future<void> _loadViewMode() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() => grid = prefs.getString(AppConstants.petViewModeKey) == 'grid');
  }

  Future<void> _setViewMode(bool useGrid) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConstants.petViewModeKey, useGrid ? 'grid' : 'list');
    if (mounted) setState(() => grid = useGrid);
  }

  List<PetRecord> get filtered {
    final q = '${widget.query} $localQuery'.trim().toLowerCase();
    if (q.isEmpty) return pets;
    return pets.where((pet) {
      return '${pet.name} ${pet.tag} ${pet.type} ${pet.owner} ${pet.breed} ${pet.phone}'
          .toLowerCase()
          .contains(q);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final rows = filtered;
    final totalPages = rows.isEmpty ? 1 : ((rows.length - 1) ~/ pageSize) + 1;
    final safePage = pageIndex.clamp(0, totalPages - 1).toInt();
    final start = safePage * pageSize;
    final pageRows = rows.skip(start).take(pageSize).toList();
    if (pageIndex != safePage) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => pageIndex = safePage);
      });
    }
    if (selectedPet != null) {
      return PetDetailPage(
        pet: selectedPet!,
        onBack: () => setState(() => selectedPet = null),
        onEdit: editPet,
        onDelete: (pet) {
          deletePet(pet);
          setState(() => selectedPet = null);
        },
      );
    }
    return Column(
      children: [
        PageHeader(
          title: 'Pet Listesi',
          subtitle: 'Kliniğinize kayıtlı tüm petleri yönetin.',
          action: FilledButton.icon(
            onPressed: showAddPet,
            icon: const Icon(Icons.add),
            label: const Text('Yeni Pet Ekle'),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      onChanged: (value) => setState(() {
                        localQuery = value;
                        pageIndex = 0;
                      }),
                      decoration: const InputDecoration(
                        isDense: true,
                        hintText: 'Pet adı, sahip adı veya Künye No ile ara...',
                        prefixIcon: Icon(Icons.search),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  IconButton.filledTonal(
                    onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                            content: Text(
                                'Filtre alanı aktif. Arama kutusuna pet, sahip veya künye yazabilirsiniz.'))),
                    icon: const Icon(Icons.filter_alt_outlined),
                    tooltip: 'Filtrele',
                  ),
                  ViewModeButton(
                      selected: grid,
                      icon: Icons.grid_view_outlined,
                      tooltip: 'Kart görünümü',
                      onPressed: () => _setViewMode(true)),
                  ViewModeButton(
                      selected: !grid,
                      icon: Icons.view_list_outlined,
                      tooltip: 'Liste görünümü',
                      onPressed: () => _setViewMode(false)),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            child: grid
                ? PetGrid(rows: pageRows, onDetail: showPetDetail)
                : PetTable(
                    rows: pageRows,
                    onDelete: deletePet,
                    onDetail: showPetDetail,
                    onEdit: editPet,
                  ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(28, 8, 28, 20),
          child: Row(
            children: [
              Text(
                  rows.isEmpty
                      ? 'Kayıt bulunamadı'
                      : 'Toplam ${rows.length} kayıttan ${start + 1}-${start + pageRows.length} arası gösteriliyor',
                  style: TextStyle(color: appMuted(context))),
              const Spacer(),
              TextButton(
                  onPressed: safePage == 0
                      ? null
                      : () => setState(() => pageIndex = safePage - 1),
                  child: const Text('Önceki')),
              for (var i = 0; i < totalPages; i++)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 3),
                  child: i == safePage
                      ? FilledButton(onPressed: () {}, child: Text('${i + 1}'))
                      : TextButton(
                          onPressed: () => setState(() => pageIndex = i),
                          child: Text('${i + 1}'),
                        ),
                ),
              TextButton(
                  onPressed: safePage >= totalPages - 1
                      ? null
                      : () => setState(() => pageIndex = safePage + 1),
                  child: const Text('Sonraki')),
            ],
          ),
        ),
      ],
    );
  }

  void showAddPet() {
    final name = TextEditingController();
    final owner = TextEditingController();
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Yeni Pet Ekle'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'Pet adı')),
            const SizedBox(height: 10),
            TextField(
                controller: owner,
                decoration: const InputDecoration(labelText: 'Sahip adı')),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () {
              if (name.text.trim().isEmpty) return;
              setState(() {
                pets.insert(
                  0,
                  PetRecord(
                      name.text.trim(),
                      'AT${DateTime.now().millisecondsSinceEpoch.toString().substring(5, 13)}',
                      'Kedi',
                      'Belirtilmedi',
                      owner.text.trim(),
                      '-'),
                );
              });
              Navigator.pop(context);
            },
            child: const Text('Kaydet'),
          ),
        ],
      ),
    );
  }

  void deletePet(PetRecord pet) {
    setState(() => pets.remove(pet));
  }

  void showPageMessage(String text) {
    final rows = filtered;
    final totalPages = rows.isEmpty ? 1 : ((rows.length - 1) ~/ pageSize) + 1;
    if (text.contains('1.')) {
      setState(() => pageIndex = 0);
    } else if (text.contains('2.')) {
      setState(() => pageIndex = 1);
    } else if (text.contains('6.')) {
      setState(() => pageIndex = 5.clamp(0, totalPages - 1).toInt());
    } else if (text.contains('Sonraki')) {
      setState(
          () => pageIndex = (pageIndex + 1).clamp(0, totalPages - 1).toInt());
    } else {
      setState(
          () => pageIndex = (pageIndex - 1).clamp(0, totalPages - 1).toInt());
    }
  }

  void showPetDetail(PetRecord pet) {
    setState(() => selectedPet = pet);
  }

  void editPet(PetRecord pet) {
    final name = TextEditingController(text: pet.name);
    final owner = TextEditingController(text: pet.owner);
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Pet Düzenle'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'Pet adı')),
            const SizedBox(height: 10),
            TextField(
                controller: owner,
                decoration: const InputDecoration(labelText: 'Sahip adı')),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () {
              final index = pets.indexOf(pet);
              if (index >= 0) {
                setState(() {
                  final updated = PetRecord(name.text.trim(), pet.tag, pet.type,
                      pet.breed, owner.text.trim(), pet.phone);
                  pets[index] = updated;
                  if (selectedPet == pet) selectedPet = updated;
                });
              }
              Navigator.pop(context);
            },
            child: const Text('Kaydet'),
          ),
        ],
      ),
    );
  }
}

class ViewModeButton extends StatelessWidget {
  const ViewModeButton({
    super.key,
    required this.selected,
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final bool selected;
  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onPressed,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          margin: const EdgeInsets.only(left: 6),
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            gradient: selected
                ? LinearGradient(colors: [
                    appOrange(context),
                    Theme.of(context).colorScheme.secondary,
                  ])
                : null,
            color: selected ? null : appSurface(context),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: appBorder(context)),
          ),
          child: Icon(icon,
              color: selected
                  ? Colors.white
                  : Theme.of(context).colorScheme.onSurface),
        ),
      ),
    );
  }
}

class PetDetailPage extends StatelessWidget {
  const PetDetailPage({
    super.key,
    required this.pet,
    required this.onBack,
    required this.onEdit,
    required this.onDelete,
  });

  final PetRecord pet;
  final VoidCallback onBack;
  final ValueChanged<PetRecord> onEdit;
  final ValueChanged<PetRecord> onDelete;

  @override
  Widget build(BuildContext context) {
    final owner = pet.owner.trim().isEmpty ? 'Sahipsiz' : pet.owner;
    final phone = pet.phone.trim().isEmpty ? '-' : pet.phone;
    return ListView(
      children: [
        PageHeader(
          title: pet.name,
          subtitle: 'Pet kaydındaki tüm bilgiler',
          action: FilledButton.tonalIcon(
            onPressed: onBack,
            icon: const Icon(Icons.arrow_back),
            label: const Text('Geri Git'),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(22),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  PetIdentity(pet: pet),
                  const SizedBox(height: 22),
                  Wrap(
                    spacing: 14,
                    runSpacing: 14,
                    children: [
                      PetInfoTile(label: 'Pet Adı', value: pet.name),
                      PetInfoTile(label: 'Mikroçip No', value: pet.tag),
                      PetInfoTile(label: 'Tür', value: pet.type),
                      PetInfoTile(label: 'Irk', value: pet.breed),
                      PetInfoTile(label: 'Sahip', value: owner),
                      PetInfoTile(label: 'İletişim', value: phone),
                    ],
                  ),
                  const SizedBox(height: 24),
                  Row(
                    children: [
                      FilledButton.icon(
                        onPressed: () => onEdit(pet),
                        icon: const Icon(Icons.edit_outlined),
                        label: const Text('Düzenle'),
                      ),
                      const SizedBox(width: 10),
                      FilledButton.tonalIcon(
                        onPressed: () => onDelete(pet),
                        icon: const Icon(Icons.delete_outline),
                        label: const Text('Sil'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class PetInfoTile extends StatelessWidget {
  const PetInfoTile({super.key, required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 250,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: appBackground(context),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: appBorder(context)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: TextStyle(color: appMuted(context), fontSize: 12)),
            const SizedBox(height: 6),
            Text(value.isEmpty ? '-' : value,
                style: const TextStyle(fontWeight: FontWeight.w800)),
          ],
        ),
      ),
    );
  }
}

class PetTable extends StatelessWidget {
  const PetTable(
      {super.key,
      required this.rows,
      required this.onDelete,
      required this.onDetail,
      required this.onEdit});

  final List<PetRecord> rows;
  final ValueChanged<PetRecord> onDelete;
  final ValueChanged<PetRecord> onDetail;
  final ValueChanged<PetRecord> onEdit;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: SingleChildScrollView(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              headingRowColor: WidgetStateProperty.all(appBackground(context)),
              columnSpacing: 56,
              columns: const [
                DataColumn(label: Text('PET ADI')),
                DataColumn(label: Text('MİKROÇİP')),
                DataColumn(label: Text('TÜR')),
                DataColumn(label: Text('IRK')),
                DataColumn(label: Text('SAHİP')),
                DataColumn(label: Text('İLETİŞİM')),
                DataColumn(label: Text('İŞLEMLER')),
              ],
              rows: rows
                  .map(
                    (pet) => DataRow(
                      cells: [
                        DataCell(
                            PetIdentity(pet: pet, onTap: () => onDetail(pet))),
                        DataCell(Text(pet.tag,
                            style: const TextStyle(
                                color: Color(0xFFE3A35A),
                                fontWeight: FontWeight.w700))),
                        DataCell(Text(pet.type)),
                        DataCell(Text(pet.breed)),
                        DataCell(OwnerBadge(pet: pet)),
                        DataCell(Row(children: [
                          const Icon(Icons.phone_outlined,
                              size: 16, color: Color(0xFF0F6E56)),
                          const SizedBox(width: 8),
                          Text(pet.phone)
                        ])),
                        DataCell(PopupMenuButton<String>(
                          onSelected: (value) {
                            if (value == 'detail') onDetail(pet);
                            if (value == 'edit') onEdit(pet);
                            if (value == 'delete') onDelete(pet);
                          },
                          itemBuilder: (_) => const [
                            PopupMenuItem(
                                value: 'detail', child: Text('Detay')),
                            PopupMenuItem(
                                value: 'edit', child: Text('Düzenle')),
                            PopupMenuItem(value: 'delete', child: Text('Sil')),
                          ],
                        )),
                      ],
                    ),
                  )
                  .toList(),
            ),
          ),
        ),
      ),
    );
  }
}

class PetGrid extends StatelessWidget {
  const PetGrid({super.key, required this.rows, required this.onDetail});

  final List<PetRecord> rows;
  final ValueChanged<PetRecord> onDetail;

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      itemCount: rows.length,
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: MediaQuery.sizeOf(context).width > 1200 ? 4 : 2,
        mainAxisExtent: 160,
        mainAxisSpacing: 14,
        crossAxisSpacing: 14,
      ),
      itemBuilder: (_, index) {
        final pet = rows[index];
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                PetIdentity(pet: pet, onTap: () => onDetail(pet)),
                const Spacer(),
                Text('${pet.type} / ${pet.breed}',
                    style: TextStyle(color: appMuted(context))),
                const SizedBox(height: 6),
                OwnerBadge(pet: pet),
              ],
            ),
          ),
        );
      },
    );
  }
}

class PetIdentity extends StatelessWidget {
  const PetIdentity({super.key, required this.pet, this.onTap});

  final PetRecord pet;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            color: const Color(0xFFFFF6E9),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(
              pet.type == 'Kedi' ? Icons.cruelty_free_outlined : Icons.pets,
              color: const Color(0xFF0F6E56),
              size: 18),
        ),
        const SizedBox(width: 12),
        Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            InkWell(
              onTap: onTap,
              child: Text(
                pet.name,
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: onTap == null ? null : const Color(0xFF0F6E56),
                  decoration: onTap == null ? null : TextDecoration.underline,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class OwnerBadge extends StatelessWidget {
  const OwnerBadge({super.key, required this.pet});

  final PetRecord pet;

  @override
  Widget build(BuildContext context) {
    if (pet.owner.isEmpty) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
            color: const Color(0xFFFFE7EA),
            borderRadius: BorderRadius.circular(99)),
        child: const Text('SAHİPSİZ',
            style: TextStyle(
                color: Color(0xFFE22E4C),
                fontSize: 11,
                fontWeight: FontWeight.w800)),
      );
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.person_outline, size: 15, color: Color(0xFF0F6E56)),
        const SizedBox(width: 8),
        Text(pet.owner, style: const TextStyle(fontWeight: FontWeight.w800)),
      ],
    );
  }
}

class AppointmentPage extends StatefulWidget {
  const AppointmentPage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  State<AppointmentPage> createState() => _AppointmentPageState();
}

class _AppointmentPageState extends State<AppointmentPage> {
  String localQuery = '';
  late Future<Map<String, dynamic>> future =
      widget.api.request(AppConstants.appointmentsEndpoint);

  void reload() => setState(
      () => future = widget.api.request(AppConstants.appointmentsEndpoint));

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(
            title: 'Randevular', subtitle: 'Randevu durumlarını yönetin.'),
        Padding(
          padding: const EdgeInsets.fromLTRB(28, 0, 28, 14),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: TextField(
                onChanged: (value) => setState(() => localQuery = value),
                decoration: const InputDecoration(
                  isDense: true,
                  hintText: 'Randevu, pet, sahip, telefon veya durum ara...',
                  prefixIcon: Icon(Icons.search),
                ),
              ),
            ),
          ),
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return ErrorState(
                    message: snapshot.error.toString(), onRetry: reload);
              }
              if (!snapshot.hasData)
                return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = localQuery.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows
                      .where((item) => (item as Map<String, dynamic>)
                          .values
                          .join(' ')
                          .toLowerCase()
                          .contains(q))
                      .toList();
              if (rows.isEmpty)
                return const Center(child: Text('Henüz randevu yok.'));
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  return Card(
                    child: ListTile(
                      onTap: () => showAppointmentDetail(item),
                      leading: const CircleAvatar(
                          backgroundColor: Color(0xFFE1F5EE),
                          child: Icon(Icons.calendar_month_outlined,
                              color: Color(0xFF0F6E56))),
                      title: Text(
                          '${item['first_name']} ${item['last_name']} - ${item['pet_name'] ?? item['pet_type']}'),
                      subtitle: Text(
                          '${item['appt_date']} ${item['appt_time']} • ${item['status']}'),
                      trailing: PopupMenuButton<String>(
                        onSelected: (status) async {
                          await widget.api.request(
                              '${AppConstants.appointmentsUpdateEndpoint}/${item['id']}',
                              method: 'PATCH',
                              body: {'status': status});
                          reload();
                        },
                        itemBuilder: (_) => const [
                          PopupMenuItem(
                              value: 'pending', child: Text('Bekliyor')),
                          PopupMenuItem(
                              value: 'confirmed', child: Text('Onaylandı')),
                          PopupMenuItem(
                              value: 'completed', child: Text('Tamamlandı')),
                          PopupMenuItem(
                              value: 'cancelled', child: Text('İptal')),
                        ],
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }

  void showAppointmentDetail(Map<String, dynamic> item) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('${item['first_name']} ${item['last_name']}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Tarih/Saat: ${item['appt_date']} ${item['appt_time']}'),
            const SizedBox(height: 8),
            Text('Pet: ${item['pet_name'] ?? '-'} (${item['pet_type'] ?? '-'})'),
            const SizedBox(height: 8),
            Text('Talep edilen hizmet: ${item['service'] ?? 'Belirtilmedi'}'),
            const SizedBox(height: 8),
            Text('Not: ${item['notes']?.toString().trim().isEmpty == false ? item['notes'] : 'Not yok'}'),
            const SizedBox(height: 8),
            Text('Telefon: ${item['phone'] ?? '-'}'),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Kapat')),
        ],
      ),
    );
  }
}

class HospitalizedPage extends StatefulWidget {
  const HospitalizedPage({super.key, required this.query});

  final String query;

  @override
  State<HospitalizedPage> createState() => _HospitalizedPageState();
}

class _HospitalizedPageState extends State<HospitalizedPage> {
  // Yatan hasta kayitlari uygulama icinde tutulur. Hasta yatisi formu yeni
  // kayit ekler; kayda tiklaninca tedavi plani dahil tum detaylar acilir.
  final List<HospitalRecord> records = List.of(sampleHospitalized);
  HospitalRecord? selected;

  @override
  Widget build(BuildContext context) {
    final rows = records
        .where((item) =>
            '${item.pet} ${item.owner} ${item.reason} ${item.room} ${item.treatment} ${item.notes}'
                .toLowerCase()
                .contains(widget.query.toLowerCase()))
        .toList();
    if (selected != null) {
      return HospitalDetailPage(
        record: selected!,
        onBack: () => setState(() => selected = null),
      );
    }
    return Column(
      children: [
        PageHeader(
          title: 'Yatan Hastalar',
          subtitle: 'Klinikte takip edilen hastaların oda ve durum kayıtları.',
          action: FilledButton.icon(
            onPressed: showAdmissionForm,
            icon: const Icon(Icons.add),
            label: const Text('Hasta Yatışı'),
          ),
        ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            itemCount: rows.length,
            itemBuilder: (_, index) {
              final item = rows[index];
              return Card(
                child: ListTile(
                  onTap: () => setState(() => selected = item),
                  leading: const CircleAvatar(
                      backgroundColor: Color(0xFFE1F5EE),
                      child: Icon(Icons.local_hospital_outlined,
                          color: Color(0xFF0F6E56))),
                  title: Text(item.pet,
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                  subtitle: Text(
                      '${item.owner} • ${item.reason}\nTedavi: ${item.treatment}'),
                  isThreeLine: true,
                  trailing: Chip(label: Text(item.room)),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  void showAdmissionForm() {
    final pet = TextEditingController();
    final owner = TextEditingController();
    final phone = TextEditingController();
    final room = TextEditingController();
    final reason = TextEditingController();
    final treatment = TextEditingController();
    final notes = TextEditingController();

    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Hasta Yatışı'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                    controller: pet,
                    decoration:
                        const InputDecoration(labelText: 'Hasta / pet adı')),
                const SizedBox(height: 10),
                TextField(
                    controller: owner,
                    decoration: const InputDecoration(labelText: 'Sahip adı')),
                const SizedBox(height: 10),
                TextField(
                    controller: phone,
                    decoration: const InputDecoration(labelText: 'Telefon')),
                const SizedBox(height: 10),
                TextField(
                    controller: room,
                    decoration:
                        const InputDecoration(labelText: 'Oda / kafes')),
                const SizedBox(height: 10),
                TextField(
                    controller: reason,
                    decoration:
                        const InputDecoration(labelText: 'Yatış nedeni')),
                const SizedBox(height: 10),
                TextField(
                    controller: treatment,
                    minLines: 2,
                    maxLines: 4,
                    decoration:
                        const InputDecoration(labelText: 'Uygulanacak tedavi')),
                const SizedBox(height: 10),
                TextField(
                    controller: notes,
                    minLines: 2,
                    maxLines: 4,
                    decoration:
                        const InputDecoration(labelText: 'Veteriner notu')),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () {
              if (pet.text.trim().isEmpty || treatment.text.trim().isEmpty) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                      content: Text('Pet adı ve uygulanacak tedavi zorunlu.')),
                );
                return;
              }
              setState(() {
                records.insert(
                  0,
                  HospitalRecord(
                    pet.text.trim(),
                    owner.text.trim(),
                    reason.text.trim(),
                    room.text.trim().isEmpty
                        ? 'Oda belirtilmedi'
                        : room.text.trim(),
                    treatment.text.trim(),
                    phone.text.trim(),
                    notes.text.trim(),
                    DateTime.now(),
                  ),
                );
              });
              Navigator.pop(context);
            },
            child: const Text('Yatış Yap'),
          ),
        ],
      ),
    );
  }
}

class HospitalDetailPage extends StatelessWidget {
  const HospitalDetailPage({
    super.key,
    required this.record,
    required this.onBack,
  });

  final HospitalRecord record;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final admittedAt = record.admittedAt ?? DateTime(2026, 5, 25);
    return ListView(
      children: [
        PageHeader(
          title: record.pet,
          subtitle: 'Yatan hasta detayları ve uygulanacak tedavi',
          action: FilledButton.tonalIcon(
            onPressed: onBack,
            icon: const Icon(Icons.arrow_back),
            label: const Text('Geri Git'),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(22),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 14,
                    runSpacing: 14,
                    children: [
                      PetInfoTile(label: 'Hasta / Pet', value: record.pet),
                      PetInfoTile(label: 'Sahip', value: record.owner),
                      PetInfoTile(label: 'Telefon', value: record.phone),
                      PetInfoTile(label: 'Oda / Kafes', value: record.room),
                      PetInfoTile(label: 'Yatış Nedeni', value: record.reason),
                      PetInfoTile(
                          label: 'Yatış Tarihi',
                          value:
                              '${admittedAt.day.toString().padLeft(2, '0')}.${admittedAt.month.toString().padLeft(2, '0')}.${admittedAt.year}'),
                    ],
                  ),
                  const SizedBox(height: 18),
                  Text('Uygulanacak Tedavi',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: const Color(0xFF0F6E56))),
                  const SizedBox(height: 8),
                  Text(record.treatment.isEmpty ? '-' : record.treatment),
                  const SizedBox(height: 18),
                  Text('Veteriner Notu',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: const Color(0xFF0F6E56))),
                  const SizedBox(height: 8),
                  Text(record.notes.isEmpty ? '-' : record.notes),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class ProductPage extends StatelessWidget {
  const ProductPage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  Widget build(BuildContext context) => CrudListPage(
        title: 'Ürün Yönetimi',
        subtitle: 'Stok, fiyat ve ürün bilgilerini yönetin.',
        loadPath: AppConstants.productsEndpoint,
        addPath: AppConstants.productsAddEndpoint,
        updatePath: AppConstants.productsUpdateEndpoint,
        deletePath: AppConstants.productsDeleteEndpoint,
        api: api,
        query: query,
      );
}

class ServicePage extends StatelessWidget {
  const ServicePage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  Widget build(BuildContext context) => CrudListPage(
        title: 'Hizmet Yönetimi',
        subtitle: 'Muayene, aşı ve klinik hizmetlerini düzenleyin.',
        loadPath: AppConstants.servicesEndpoint,
        addPath: AppConstants.servicesAddEndpoint,
        updatePath: AppConstants.servicesUpdateEndpoint,
        deletePath: AppConstants.servicesDeleteEndpoint,
        api: api,
        query: query,
      );
}

class CrudListPage extends StatefulWidget {
  const CrudListPage({
    super.key,
    required this.title,
    required this.subtitle,
    required this.loadPath,
    required this.addPath,
    required this.updatePath,
    required this.deletePath,
    required this.api,
    required this.query,
  });

  final String title;
  final String subtitle;
  final String loadPath;
  final String addPath;
  final String updatePath;
  final String deletePath;
  final ApiClient api;
  final String query;

  @override
  State<CrudListPage> createState() => _CrudListPageState();
}

class _CrudListPageState extends State<CrudListPage> {
  late Future<Map<String, dynamic>> future;
  String localQuery = '';

  @override
  void initState() {
    super.initState();
    future = widget.api.request(widget.loadPath);
  }

  void reload() => setState(() => future = widget.api.request(widget.loadPath));

  Future<void> save({Map<String, dynamic>? item}) async {
    final name = TextEditingController(text: item?['name']?.toString() ?? '');
    final price =
        TextEditingController(text: item?['price']?.toString() ?? '0');
    final category =
        TextEditingController(text: item?['category']?.toString() ?? 'Genel');
    final stock =
        TextEditingController(text: item?['stock']?.toString() ?? '0');
    final isProduct = widget.loadPath == AppConstants.productsEndpoint;
    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(item == null ? 'Yeni kayıt' : 'Kaydı güncelle'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'Ad')),
            const SizedBox(height: 10),
            TextField(
                controller: category,
                decoration: const InputDecoration(labelText: 'Kategori')),
            const SizedBox(height: 10),
            TextField(
                controller: price,
                decoration: const InputDecoration(labelText: 'Fiyat'),
                keyboardType: TextInputType.number),
            if (isProduct) ...[
              const SizedBox(height: 10),
              TextField(
                  controller: stock,
                  decoration: const InputDecoration(labelText: 'Stok'),
                  keyboardType: TextInputType.number),
            ],
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () async {
              final body = {
                'name': name.text,
                'price': double.tryParse(price.text) ?? 0,
                'category': category.text,
                'stock': int.tryParse(stock.text) ?? 0
              };
              if (item == null) {
                await widget.api
                    .request(widget.addPath, method: 'POST', body: body);
              } else {
                await widget.api.request('${widget.updatePath}/${item['id']}',
                    method: 'PATCH', body: body);
              }
              if (mounted) Navigator.pop(context);
              reload();
            },
            child: const Text('Kaydet'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        PageHeader(
          title: widget.title,
          subtitle: widget.subtitle,
          action: FilledButton.icon(
              onPressed: () => save(),
              icon: const Icon(Icons.add),
              label: const Text('Yeni Ekle')),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(28, 0, 28, 12),
          child: TextField(
            onChanged: (value) => setState(() => localQuery = value),
            decoration: const InputDecoration(
              isDense: true,
              hintText: 'Ürün adı, kategori, fiyat veya stok ara...',
              prefixIcon: Icon(Icons.search),
            ),
          ),
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return ErrorState(
                    message: snapshot.error.toString(), onRetry: reload);
              }
              if (!snapshot.hasData)
                return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = '${widget.query} $localQuery'.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows
                      .where((item) => (item as Map<String, dynamic>)
                          .values
                          .join(' ')
                          .toLowerCase()
                          .contains(q))
                      .toList();
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  return Card(
                    child: ListTile(
                      leading: const CircleAvatar(
                          backgroundColor: Color(0xFFE1F5EE),
                          child: Icon(Icons.inventory_2_outlined,
                              color: Color(0xFF0F6E56))),
                      title: Text(item['name']?.toString() ?? '-',
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text(
                          '${item['category'] ?? 'Genel'} • ₺${item['price'] ?? 0}'),
                      trailing: Wrap(
                        children: [
                          IconButton(
                              icon: const Icon(Icons.edit_outlined),
                              onPressed: () => save(item: item)),
                          IconButton(
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () async {
                              await widget.api.request(
                                  '${widget.deletePath}/${item['id']}',
                                  method: 'DELETE');
                              reload();
                            },
                          ),
                        ],
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}

class OrdersPage extends StatefulWidget {
  const OrdersPage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  State<OrdersPage> createState() => _OrdersPageState();
}

class _OrdersPageState extends State<OrdersPage> {
  late Future<Map<String, dynamic>> future =
      widget.api.request(AppConstants.ordersEndpoint);

  void reload() =>
      setState(() => future = widget.api.request(AppConstants.ordersEndpoint));

  String statusLabel(String status) {
    return {
          'pending': 'Bekliyor',
          'confirmed': 'Onaylandı',
          'shipped': 'Kargoya verildi',
          'delivered': 'Teslim edildi',
          'cancelled': 'İptal',
        }[status] ??
        status;
  }

  Future<void> updateStatus(Map<String, dynamic> order, String status) async {
    final result = await widget.api.request(
        '${AppConstants.ordersUpdateEndpoint}/${order['id']}',
        method: 'PATCH',
        body: {'status': status});
    final mail =
        result['data'] is Map ? (result['data']['mail'] as Map?) : null;
    if (!mounted) return;
    final extra = status == 'shipped'
        ? (mail == null
            ? ' Mail ayarı yoksa gönderim atlanır.'
            : ' Mail: ${mail['message']}')
        : '';
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Sipariş durumu güncellendi.$extra')));
    reload();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(
            title: 'Gelen Siparişler',
            subtitle:
                'Site üzerinden gelen siparişleri ve kargo durumunu yönetin.'),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError)
                return ErrorState(
                    message: snapshot.error.toString(), onRetry: reload);
              if (!snapshot.hasData)
                return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows
                      .where((item) => (item as Map<String, dynamic>)
                          .values
                          .join(' ')
                          .toLowerCase()
                          .contains(q))
                      .toList();
              if (rows.isEmpty)
                return const Center(child: Text('Henüz sipariş yok.'));
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final order = rows[index] as Map<String, dynamic>;
                  final items = (order['items'] as List?) ?? [];
                  final status = order['status']?.toString() ?? 'pending';
                  return Card(
                    child: ExpansionTile(
                      leading: CircleAvatar(
                          backgroundColor: appOrange(context).withOpacity(.12),
                          child: Icon(Icons.shopping_bag_outlined,
                              color: appOrange(context))),
                      title: Text(
                          '#${order['id']} ${order['first_name'] ?? ''} ${order['last_name'] ?? ''}',
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text(
                          '${order['phone'] ?? '-'} • ₺${order['total'] ?? 0} • ${statusLabel(status)}'),
                      trailing: DropdownButton<String>(
                        value: status,
                        items: const [
                          DropdownMenuItem(
                              value: 'pending', child: Text('Bekliyor')),
                          DropdownMenuItem(
                              value: 'confirmed', child: Text('Onaylandı')),
                          DropdownMenuItem(
                              value: 'shipped', child: Text('Kargoya verildi')),
                          DropdownMenuItem(
                              value: 'delivered', child: Text('Teslim edildi')),
                          DropdownMenuItem(
                              value: 'cancelled', child: Text('İptal')),
                        ],
                        onChanged: (value) {
                          if (value != null) updateStatus(order, value);
                        },
                      ),
                      childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
                      children: [
                        Align(
                            alignment: Alignment.centerLeft,
                            child: Text('Adres: ${order['address'] ?? '-'}')),
                        const SizedBox(height: 8),
                        InfoSection(
                          title: 'Ürünler',
                          rows: items.map((item) {
                            final row = item as Map<String, dynamic>;
                            return '${row['name'] ?? 'Ürün'} • Adet: ${row['quantity']} • ₺${row['unit_price']}';
                          }).toList(),
                        ),
                      ],
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}

class ReviewReplyPage extends StatefulWidget {
  const ReviewReplyPage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  State<ReviewReplyPage> createState() => _ReviewReplyPageState();
}

class _ReviewReplyPageState extends State<ReviewReplyPage> {
  late Future<Map<String, dynamic>> future =
      widget.api.request(AppConstants.reviewsEndpoint);

  void reload() =>
      setState(() => future = widget.api.request(AppConstants.reviewsEndpoint));

  Future<void> replyTo(Map<String, dynamic> review) async {
    final reply =
        TextEditingController(text: review['reply']?.toString() ?? '');
    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('${review['author']} yorumuna yanıt'),
        content: TextField(
          controller: reply,
          minLines: 4,
          maxLines: 7,
          decoration: const InputDecoration(labelText: 'Yanıt metni'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () async {
              await widget.api.request(
                '${AppConstants.reviewsUpdateEndpoint}/${review['id']}',
                method: 'PATCH',
                body: {'reply': reply.text.trim()},
              );
              if (mounted) Navigator.pop(context);
              reload();
            },
            child: const Text('Yanıtı Kaydet'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(
          title: 'Yorumlar',
          subtitle:
              'Web sitesinde görünen müşteri yorumlarına klinik yanıtı yazın.',
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (!snapshot.hasData)
                return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows
                      .where((item) => (item as Map<String, dynamic>)
                          .values
                          .join(' ')
                          .toLowerCase()
                          .contains(q))
                      .toList();
              if (rows.isEmpty)
                return const Center(child: Text('Henüz yorum yok.'));
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  final rating = (int.tryParse('${item['rating']}') ?? 5)
                      .clamp(0, 5)
                      .toInt();
                  final stars =
                      '${List.filled(rating, '★').join()}${List.filled(5 - rating, '☆').join()}';
                  return Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const CircleAvatar(
                                  child: Icon(Icons.reviews_outlined)),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                        '${item['author']} — ${item['pet_type'] ?? 'Hasta Sahibi'}',
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w800)),
                                    Text(
                                        'Ürün: ${item['product_name'] ?? 'Genel'}',
                                        style: TextStyle(
                                            color: appMuted(context),
                                            fontSize: 12)),
                                    Text(stars,
                                        style: const TextStyle(
                                            color: Color(0xFFE9B872))),
                                  ],
                                ),
                              ),
                              Switch(
                                value: item['active'] == 1,
                                onChanged: (value) async {
                                  await widget.api.request(
                                      '${AppConstants.reviewsUpdateEndpoint}/${item['id']}',
                                      method: 'PATCH',
                                      body: {'active': value ? 1 : 0});
                                  reload();
                                },
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          Text(item['message']?.toString() ?? ''),
                          if ((item['reply']?.toString() ?? '').isNotEmpty)
                            Container(
                              margin: const EdgeInsets.only(top: 12),
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Theme.of(context)
                                    .colorScheme
                                    .primary
                                    .withOpacity(.08),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                  'Gümüş Veteriner yanıtı: ${item['reply']}'),
                            ),
                          const SizedBox(height: 10),
                          Align(
                            alignment: Alignment.centerRight,
                            child: FilledButton.icon(
                              onPressed: () => replyTo(item),
                              icon: const Icon(Icons.reply),
                              label: const Text('Yanıtla'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}

class ContactReplyPage extends StatefulWidget {
  const ContactReplyPage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  State<ContactReplyPage> createState() => _ContactReplyPageState();
}

class _ContactReplyPageState extends State<ContactReplyPage> {
  late Future<Map<String, dynamic>> future =
      widget.api.request(AppConstants.contactsEndpoint);

  void reload() => setState(
      () => future = widget.api.request(AppConstants.contactsEndpoint));

  Future<void> replyTo(Map<String, dynamic> contact) async {
    final reply =
        TextEditingController(text: contact['reply']?.toString() ?? '');
    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('${contact['full_name']} mesajına yanıt'),
        content: TextField(
          controller: reply,
          minLines: 5,
          maxLines: 9,
          decoration: const InputDecoration(
              labelText: 'Mail olarak gönderilecek yanıt'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () async {
              final result = await widget.api.request(
                '${AppConstants.contactsReplyEndpoint}/${contact['id']}',
                method: 'PATCH',
                body: {'reply': reply.text.trim()},
              );
              if (!mounted) return;
              Navigator.pop(context);
              final mail = result['data'] is Map
                  ? (result['data']['mail'] as Map?)
                  : null;
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text(
                      'Yanıt kaydedildi. Mail: ${mail?['message'] ?? 'denendi'}')));
              reload();
            },
            child: const Text('Yanıtla ve Mail Gönder'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(
            title: 'Sorular',
            subtitle:
                'İletişim formundan gelen mesajları yanıtlayın. Yanıtlar müşteriye mail olarak gönderilir.'),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError)
                return ErrorState(
                    message: snapshot.error.toString(), onRetry: reload);
              if (!snapshot.hasData)
                return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows
                      .where((item) => (item as Map<String, dynamic>)
                          .values
                          .join(' ')
                          .toLowerCase()
                          .contains(q))
                      .toList();
              if (rows.isEmpty)
                return const Center(child: Text('Henüz soru yok.'));
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  final hasReply = (item['reply']?.toString() ?? '').isNotEmpty;
                  return Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              CircleAvatar(
                                  backgroundColor:
                                      appOrange(context).withOpacity(.12),
                                  child: Icon(Icons.contact_mail_outlined,
                                      color: appOrange(context))),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(item['full_name']?.toString() ?? '-',
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w800)),
                                    Text(
                                        '${item['email'] ?? '-'} • ${item['subject'] ?? 'Genel'}',
                                        style: TextStyle(
                                            color: appMuted(context))),
                                  ],
                                ),
                              ),
                              Chip(
                                  label: Text(
                                      hasReply ? 'Yanıtlandı' : 'Bekliyor')),
                            ],
                          ),
                          const SizedBox(height: 12),
                          Text(item['message']?.toString() ?? ''),
                          if (hasReply)
                            Container(
                              margin: const EdgeInsets.only(top: 12),
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                  color: appBackground(context),
                                  borderRadius: BorderRadius.circular(12)),
                              child: Text('Yanıt: ${item['reply']}'),
                            ),
                          const SizedBox(height: 10),
                          Align(
                            alignment: Alignment.centerRight,
                            child: FilledButton.icon(
                                onPressed: () => replyTo(item),
                                icon: const Icon(Icons.reply),
                                label: const Text('Yanıt Ver')),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}

class SiteTextPage extends StatefulWidget {
  const SiteTextPage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  State<SiteTextPage> createState() => _SiteTextPageState();
}

class _SiteTextPageState extends State<SiteTextPage> {
  late Future<Map<String, dynamic>> future =
      widget.api.request(AppConstants.siteTextsEndpoint);

  void reload() => setState(
      () => future = widget.api.request(AppConstants.siteTextsEndpoint));

  Future<void> editText(Map<String, dynamic> item) async {
    final value = TextEditingController(text: item['value']?.toString() ?? '');
    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(item['label']?.toString() ?? 'Site yazısı'),
        content: TextField(
          controller: value,
          minLines: 4,
          maxLines: 9,
          decoration: const InputDecoration(labelText: 'Sitede görünecek yazı'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () async {
              await widget.api.request(
                '${AppConstants.siteTextsUpdateEndpoint}/${item['text_key']}',
                method: 'PATCH',
                body: {'value': value.text.trim()},
              );
              if (mounted) Navigator.pop(context);
              reload();
            },
            child: const Text('Kaydet'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(
          title: 'Site Yazıları',
          subtitle:
              'Web sitesindeki ana başlık ve açıklama metinlerini düzenleyin.',
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (!snapshot.hasData)
                return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows
                      .where((item) => (item as Map<String, dynamic>)
                          .values
                          .join(' ')
                          .toLowerCase()
                          .contains(q))
                      .toList();
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  return Card(
                    child: ListTile(
                      leading: const CircleAvatar(
                          child: Icon(Icons.edit_note_outlined)),
                      title: Text(item['label']?.toString() ?? '-',
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text(item['value']?.toString() ?? '',
                          maxLines: 2, overflow: TextOverflow.ellipsis),
                      trailing: IconButton(
                        icon: const Icon(Icons.edit_outlined),
                        onPressed: () => editText(item),
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}

class UserManagementPage extends StatefulWidget {
  const UserManagementPage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  State<UserManagementPage> createState() => _UserManagementPageState();
}

class _UserManagementPageState extends State<UserManagementPage> {
  late Future<Map<String, dynamic>> future =
      widget.api.request(AppConstants.usersEndpoint);

  void reload() =>
      setState(() => future = widget.api.request(AppConstants.usersEndpoint));

  Future<void> updateUser(
      Map<String, dynamic> user, Map<String, dynamic> body) async {
    await widget.api.request(
        '${AppConstants.usersUpdateEndpoint}/${user['id']}',
        method: 'PATCH',
        body: body);
    reload();
  }

  Future<void> deleteUser(Map<String, dynamic> user) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Üye silinsin mi?'),
        content: Text('${user['full_name']} kalıcı olarak silinecek.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Vazgeç')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Sil')),
        ],
      ),
    );
    if (ok != true) return;
    await widget.api.request(
        '${AppConstants.usersDeleteEndpoint}/${user['id']}',
        method: 'DELETE');
    reload();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(
          title: 'Üyeler',
          subtitle:
              'Siteye kayıt olan kullanıcıların iletişim, adres ve hayvan bilgileri.',
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return ErrorState(
                    message: snapshot.error.toString(), onRetry: reload);
              }
              if (!snapshot.hasData)
                return const Center(child: CircularProgressIndicator());
              final allUsers = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final users = q.isEmpty
                  ? allUsers
                  : allUsers
                      .where((item) => (item as Map<String, dynamic>)
                          .values
                          .join(' ')
                          .toLowerCase()
                          .contains(q))
                      .toList();
              if (users.isEmpty)
                return const Center(child: Text('Henüz üye yok.'));
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: users.length,
                itemBuilder: (_, index) {
                  final user = users[index] as Map<String, dynamic>;
                  final addresses = (user['addresses'] as List?) ?? [];
                  final pets = (user['pets'] as List?) ?? [];
                  return Card(
                    child: ExpansionTile(
                      leading: CircleAvatar(
                        backgroundColor: appOrange(context).withOpacity(.12),
                        child: Icon(Icons.person_outline,
                            color: appOrange(context)),
                      ),
                      title: Text(user['full_name']?.toString() ?? '-',
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text(
                          '${user['email'] ?? '-'} • ${user['phone'] ?? '-'} • ${user['role'] ?? 'member'}'),
                      trailing: Chip(
                        label: Text(user['is_banned'] == 1 ? 'Banlı' : 'Aktif'),
                        backgroundColor: user['is_banned'] == 1
                            ? Colors.red.withOpacity(.12)
                            : Colors.green.withOpacity(.12),
                      ),
                      childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
                      children: [
                        InfoSection(
                            title: 'Adresler',
                            rows: addresses.map((item) {
                              final row = item as Map<String, dynamic>;
                              return '${row['title'] ?? 'Adres'}: ${row['address'] ?? '-'} ${row['district'] ?? ''} ${row['city'] ?? ''}';
                            }).toList()),
                        const SizedBox(height: 12),
                        InfoSection(
                            title: 'Hayvanlar',
                            rows: pets.map((item) {
                              final row = item as Map<String, dynamic>;
                              return '${row['name'] ?? '-'} • ${row['species'] ?? '-'} • Yaş: ${row['age'] ?? '-'}';
                            }).toList()),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            FilledButton.tonalIcon(
                              onPressed: () => updateUser(user, {
                                'is_banned': user['is_banned'] == 1 ? 0 : 1
                              }),
                              icon: Icon(user['is_banned'] == 1
                                  ? Icons.lock_open_outlined
                                  : Icons.block_outlined),
                              label: Text(user['is_banned'] == 1
                                  ? 'Banı Kaldır'
                                  : 'Banla'),
                            ),
                            FilledButton.tonalIcon(
                              onPressed: () => updateUser(user, {
                                'role':
                                    user['role'] == 'admin' ? 'member' : 'admin'
                              }),
                              icon: const Icon(
                                  Icons.admin_panel_settings_outlined),
                              label: Text(user['role'] == 'admin'
                                  ? 'Üye Yap'
                                  : 'Admin Yap'),
                            ),
                            FilledButton.tonalIcon(
                              onPressed: () => deleteUser(user),
                              icon: const Icon(Icons.delete_outline),
                              label: const Text('Sil'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}

class InfoSection extends StatelessWidget {
  const InfoSection({super.key, required this.title, required this.rows});

  final String title;
  final List<String> rows;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          if (rows.isEmpty)
            Text('Kayıt yok.', style: TextStyle(color: appMuted(context)))
          else
            for (final row in rows)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(row),
              ),
        ],
      ),
    );
  }
}

class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(22),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.warning_amber_rounded,
                  color: Colors.orange, size: 42),
              const SizedBox(height: 10),
              const Text('Veri çekilemedi',
                  style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              SizedBox(
                  width: 420,
                  child: Text(message, textAlign: TextAlign.center)),
              const SizedBox(height: 14),
              FilledButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Tekrar Dene')),
            ],
          ),
        ),
      ),
    );
  }
}

class AppointmentSlotsPage extends StatefulWidget {
  const AppointmentSlotsPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<AppointmentSlotsPage> createState() => _AppointmentSlotsPageState();
}

class _AppointmentSlotsPageState extends State<AppointmentSlotsPage> {
  DateTime selectedDate = DateTime.now();
  late Future<Map<String, dynamic>> future = loadSlots();

  String get dateValue {
    final m = selectedDate.month.toString().padLeft(2, '0');
    final d = selectedDate.day.toString().padLeft(2, '0');
    return '${selectedDate.year}-$m-$d';
  }

  Future<Map<String, dynamic>> loadSlots() {
    return widget.api
        .request('${AppConstants.appointmentSlotsEndpoint}?date=$dateValue');
  }

  void reload() => setState(() => future = loadSlots());

  Future<void> pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: selectedDate,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 60)),
    );
    if (picked == null) return;
    setState(() {
      selectedDate = picked;
      future = loadSlots();
    });
  }

  Future<void> toggleSlot(Map<String, dynamic> slot, bool enabled) async {
    await widget.api.request(
      AppConstants.appointmentSlotsEndpoint,
      method: 'PATCH',
      body: {
        'date': dateValue,
        'time': slot['time'],
        'is_available': enabled,
        'note': enabled ? '' : 'Admin tarafından kapatıldı',
      },
    );
    reload();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        PageHeader(
          title: 'Randevu Saatleri',
          subtitle:
              'MHRS mantığıyla gün bazlı saatleri açıp kapatın. Dolu saatler müşteriye kapalı görünür.',
          action: FilledButton.icon(
            onPressed: pickDate,
            icon: const Icon(Icons.calendar_month_outlined),
            label: Text(dateValue),
          ),
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError)
                return ErrorState(
                    message: snapshot.error.toString(), onRetry: reload);
              if (!snapshot.hasData)
                return const Center(child: CircularProgressIndicator());
              final rows =
                  (snapshot.data!['data'] as List).cast<Map<String, dynamic>>();
              return GridView.builder(
                padding: const EdgeInsets.fromLTRB(28, 0, 28, 28),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount:
                      MediaQuery.sizeOf(context).width > 1100 ? 4 : 2,
                  mainAxisExtent: 112,
                  crossAxisSpacing: 14,
                  mainAxisSpacing: 14,
                ),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final slot = rows[index];
                  final taken = slot['taken'] == true;
                  final blocked = slot['blocked'] == true;
                  final available = slot['available'] == true;
                  final color = taken
                      ? Colors.red
                      : blocked
                          ? Colors.blueGrey
                          : Colors.green;
                  return Card(
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Row(
                        children: [
                          CircleAvatar(
                            backgroundColor: color.withOpacity(.12),
                            child: Icon(
                                taken
                                    ? Icons.lock_clock_outlined
                                    : Icons.schedule_outlined,
                                color: color),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(slot['time'].toString(),
                                    style: const TextStyle(
                                        fontSize: 20,
                                        fontWeight: FontWeight.w800)),
                                Text(
                                  taken
                                      ? 'Dolu'
                                      : (blocked ? 'Kapalı' : 'Uygun'),
                                  style: TextStyle(
                                      color: color,
                                      fontWeight: FontWeight.w700),
                                ),
                              ],
                            ),
                          ),
                          Switch(
                            value: available || taken,
                            onChanged: taken
                                ? null
                                : (value) => toggleSlot(slot, value),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}

class SendSmsPage extends StatefulWidget {
  const SendSmsPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<SendSmsPage> createState() => _SendSmsPageState();
}

class _SendSmsPageState extends State<SendSmsPage> {
  final phone = TextEditingController();
  final message = TextEditingController();
  bool sending = false;
  String? result;
  bool success = false;

  Future<void> sendSms() async {
    setState(() {
      sending = true;
      result = null;
      success = false;
    });
    try {
      final response = await widget.api.request(
        AppConstants.sendSmsEndpoint,
        method: 'POST',
        body: {
          'phone': phone.text.trim(),
          'message': message.text.trim(),
        },
      );
      setState(() {
        success = true;
        result = response['message']?.toString() ?? 'SMS gönderildi';
      });
    } catch (e) {
      setState(() {
        success = false;
        result = e.toString();
      });
    } finally {
      if (mounted) setState(() => sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final length = message.text.length;
    return ListView(
      children: [
        const PageHeader(
          title: 'SMS Gönder',
          subtitle:
              'Kayıtlı veya özel telefon numaralarına manuel SMS gönderin.',
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(22),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TextField(
                      controller: phone,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        labelText: 'Telefon numarası',
                        hintText: '05xxxxxxxxx',
                        prefixIcon: Icon(Icons.phone_outlined),
                      ),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: message,
                      minLines: 6,
                      maxLines: 10,
                      onChanged: (_) => setState(() {}),
                      decoration: const InputDecoration(
                        labelText: 'Mesaj metni',
                        hintText: 'Gönderilecek özel mesaj...',
                        alignLabelWithHint: true,
                        prefixIcon: Icon(Icons.sms_outlined),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Text('$length / 612 karakter',
                            style: TextStyle(
                                color: length > 612
                                    ? Colors.red
                                    : appMuted(context))),
                        const Spacer(),
                        Text(
                            'Ticari SMS için izinli kullanıcı ve İYS kaydı gereklidir.',
                            style: TextStyle(
                                color: appMuted(context), fontSize: 12)),
                      ],
                    ),
                    if (result != null)
                      Container(
                        margin: const EdgeInsets.only(top: 14),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: success
                              ? Colors.green.withOpacity(.12)
                              : Colors.red.withOpacity(.12),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(result!,
                            style: TextStyle(
                                color: success
                                    ? Colors.green.shade700
                                    : Colors.red.shade700)),
                      ),
                    const SizedBox(height: 18),
                    FilledButton.icon(
                      onPressed: sending ? null : sendSms,
                      icon: const Icon(Icons.send_outlined),
                      label: Text(sending ? 'Gönderiliyor...' : 'SMS Gönder'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class ClinicSettingsPage extends StatelessWidget {
  const ClinicSettingsPage({super.key, required this.storage});

  final FlutterSecureStorage storage;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: const [
        PageHeader(
            title: 'Ayarlar & Klinik',
            subtitle:
                'Klinik bilgileri, kullanıcı profili ve uygulama tercihleri.'),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: 28),
          child: InfoPanel(
            title: 'Klinik Bilgileri',
            lines: [
              'Samsun Gümüş Veteriner Muayenehanesi',
              'Toptepe, Kayaaltı Sk. No:10/1, Canik/Samsun',
              'Telefon: 0546 136 14 33',
              'Instagram: @gumusvetsamsun',
            ],
          ),
        ),
      ],
    );
  }
}

class AdminProfilePage extends StatefulWidget {
  const AdminProfilePage({super.key, required this.api, required this.storage});

  final ApiClient api;
  final FlutterSecureStorage storage;

  @override
  State<AdminProfilePage> createState() => _AdminProfilePageState();
}

class _AdminProfilePageState extends State<AdminProfilePage> {
  final email = TextEditingController();
  final password = TextEditingController();
  bool loading = true;
  String? message;

  @override
  void initState() {
    super.initState();
    loadProfile();
  }

  Future<void> loadProfile() async {
    try {
      final response = await widget.api.request(AppConstants.adminProfileEndpoint);
      email.text = response['data']?['email']?.toString() ?? '';
    } catch (_) {
      email.text = 'gumusveterinermuayenehanesi@gmail.com';
    }
    if (mounted) setState(() => loading = false);
  }

  Future<void> saveProfile() async {
    setState(() => message = null);
    try {
      final response = await widget.api.request(
        AppConstants.adminProfileEndpoint,
        method: 'PATCH',
        body: {
          'email': email.text.trim(),
          if (password.text.trim().isNotEmpty) 'password': password.text.trim(),
        },
      );
      final token = response['data']?['token']?.toString();
      if (token != null && token.isNotEmpty) {
        await widget.storage.write(key: AppConstants.tokenKey, value: token);
      }
      setState(() {
        password.clear();
        message = 'Profil güncellendi.';
      });
    } catch (e) {
      setState(() => message = e.toString().replaceFirst('Exception: ', ''));
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const PageHeader(
          title: 'Admin Profili',
          subtitle: 'Giriş e-postası ve şifrenizi uygulamadan güncelleyin.',
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(22),
              child: loading
                  ? const Center(child: CircularProgressIndicator())
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        TextField(
                          controller: email,
                          decoration: const InputDecoration(
                            labelText: 'Admin e-posta',
                            prefixIcon: Icon(Icons.mail_outline),
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: password,
                          obscureText: true,
                          decoration: const InputDecoration(
                            labelText: 'Yeni şifre (değişmeyecekse boş bırak)',
                            prefixIcon: Icon(Icons.lock_outline),
                          ),
                        ),
                        if (message != null) ...[
                          const SizedBox(height: 12),
                          Text(message!, style: TextStyle(color: appOrange(context))),
                        ],
                        const SizedBox(height: 18),
                        FilledButton.icon(
                          onPressed: saveProfile,
                          icon: const Icon(Icons.save_outlined),
                          label: const Text('Profili Kaydet'),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ],
    );
  }
}

class PetRecord {
  const PetRecord(
      this.name, this.tag, this.type, this.breed, this.owner, this.phone);

  final String name;
  final String tag;
  final String type;
  final String breed;
  final String owner;
  final String phone;
}

class HospitalRecord {
  const HospitalRecord(
    this.pet,
    this.owner,
    this.reason,
    this.room, [
    this.treatment = 'Tedavi planı belirtilmedi',
    this.phone = '-',
    this.notes = '',
    this.admittedAt,
  ]);

  final String pet;
  final String owner;
  final String reason;
  final String room;
  final String treatment;
  final String phone;
  final String notes;
  final DateTime? admittedAt;
}

const samplePets = [
  PetRecord("Lina Bal", "AT52065866", "Kedi", "Tekir", "Fazilet Öğüten",
      "5396240990"),
  PetRecord("Pufi", "AT41478084", "Köpek", "Pumi", "Sahipsiz", "-"),
  PetRecord("Tyson", "AT43294086", "Köpek", "Belçika Çoban Köpeği", "AHMET TOK",
      "5422031281"),
  PetRecord("GÜMÜŞ VET - Leydi", "AT49946798", "Kedi", "British Shorthair",
      "MÜZEYYEN KOÇAK", "5467891974"),
  PetRecord("GÜMÜŞ VET -Luna", "AT53983355", "Kedi", "Scottish Fold Shorthair",
      "DAMLA TOKUR", "5466696329"),
  PetRecord("GÜMÜŞ VET -Luna", "AT96965076", "Kedi", "Scottish Fold Shorthair",
      "DAMLA TOKUR", "5466696329"),
  PetRecord("GÜMÜŞ VET- Bostik", "AT25727459", "Kedi",
      "Scottish Fold Shorthair", "MERAL ESKİ", "5350372889"),
  PetRecord("ZEYTİN", "AT19074747", "Kedi", "British Shorthair", "ELİF GÜVEN",
      "5388388949"),
  PetRecord("GÜMÜŞ VET - BAMBAM", "AT94348920", "Köpek", "Toy Poodle",
      "BEY BEY", "5379567360"),
  PetRecord("Tanımsız", "AT33800572", "Köpek", "Cairn Terrier",
      "YAĞMUR KETENCİ", "5396550195"),
  PetRecord("GÜMÜŞ VET - Ares", "AT11001633", "Köpek", "Alman Çoban Köpeği",
      "HAMZA KULAÇ", "5531372064"),
  PetRecord("GÜMÜŞ VET - TARÇIN", "AT47330642", "Kedi", "British Shorthair",
      "ADEM ÇÖPOĞLU", "5441821979"),
  PetRecord("GÜMÜS VET - BABI", "AT64672624", "Kedi", "Scottish Fold Shorthair",
      "ELİF ŞİMSEK", "5515529757"),
  PetRecord("GÜMÜŞ VET - kedimiz", "AT58019911", "Kedi", "Brazilian Shorthair",
      "HASTA SAHIBI 19", "5302432070"),
  PetRecord("GÜMÜŞ VET - Bambi", "AT58019911", "Kedi", "British Shorthair",
      "FUNDA HANıM", "5053339418"),
  PetRecord("Sütlaç", "AT13617790", "Kedi", "Brazilian Shorthair",
      "VAHDETTIN KASAP", "5424272194"),
  PetRecord("GÜMUS VET - Tarçın", "AT84855406", "Kedi", "Tekir", "AYDıN KURT",
      "5448053999"),
  PetRecord("GÜMUS VET - Jacky", "AT84855406", "Köpek", "İrlanda Teriyeri",
      "AYDıN KURT", "5448053999"),
  PetRecord("ZEYNA", "AT53983355", "Kedi", "Scottish Fold Shorthair",
      "NURGÜL SAĞLAM", "5355936055"),
  PetRecord("GÜMÜŞ VETERİNER - CIRO", "AT66093024", "Kedi", "British Shorthair",
      "SERCAN YAYLA", "5078506570"),
  PetRecord("GÜMÜŞ VETERİNER - PATI", "AT79398450", "Kedi", "Tekir",
      "MERYEM AK", "5414400891"),
  PetRecord("GÜMÜŞ VET - Kedimiz", "AT29764016", "Kedi", "British Shorthair",
      "ELIF NUR YAŞER", "5340444021"),
  PetRecord("GÜMÜŞ VET - ÇATLI", "AT62056468", "Kedi", "British Shorthair",
      "ÖMÜRCAN BAYTUT", "5422066050"),
  PetRecord("Karamel", "AT39257529", "Köpek", "Golden Retriever",
      "HÜSEYIN ŞENER", "5427855487"),
  PetRecord("Mia", "AT66093024", "Kedi", "British Shorthair", "ELIF EYÜPOĞLU",
      "5414425255"),
  PetRecord("Vegas", "AT79398450", "Kedi", "British Shorthair",
      "NECLA TEMURLOĞA", "5445654858"),
  PetRecord("GÜMÜŞ VET - GOFRET", "AT95544676", "Kedi",
      "Scottish Fold Shorthair", "EMRE ARMAN", "5054314564"),
  PetRecord("GÜMÜŞ VETERİNER - LEO", "AT58019911", "Kedi", "Bengal",
      "SONER GÜLER", "5324463659"),
  PetRecord("Gümüş Veteriner - Köfte", "AT27147860", "Kedi", "Siamese",
      "GÜLŞAH ÖZER", "5058231185"),
  PetRecord("Gümüş Veteriner - Dino", "AT44489841", "Köpek", "Boston Terrier",
      "SEDEF ŞAHIN", "5539709356"),
  PetRecord("Gümüş Veteriner - Lokum", "AT37837129", "Kedi",
      "British Shorthair", "MUSTAFA KAYABAŞı", "5322864241"),
  PetRecord("Gümüş Veteriner - Patili", "AT59440312", "Kedi",
      "British Shorthair", "ŞIMAL HOCA", "5058610029"),
  PetRecord("GÜMÜŞ VETERİNER - Tarçın", "AT37837129", "Kedi", "Siamese",
      "NURHAN TÜLÜ", "5464209966"),
  PetRecord("GÜMÜŞ VETERİNER - Lokum", "AT58019911", "Kedi", "Tekir",
      "GÜLCAN KURU", "5423014609"),
  PetRecord("GÜMÜŞ VETERİNER - Çakıl", "AT27147860", "Kedi",
      "British Shorthair", "GIZEM ALBAYRAK", "5461985509"),
  PetRecord("GÜMÜŞ VETERİNER - Pamuk", "AT51367199", "Kedi", "Tekir",
      "MELIKE AÇıCı", "5449550561"),
  PetRecord("GÜMÜŞ VETERİNER - Şila", "AT53983355", "Köpek",
      "Cane Corso Italiano", "TAHIR SAKAOĞLU", "5439755455"),
  PetRecord("GÜMÜŞ VETERİNER - Bal ve Kaymak", "AT95544676", "Kedi",
      "British Shorthair", "SUAT SEZER", "5325684542"),
  PetRecord("GÜMÜŞ VETERİNER - Mıncır", "AT35220973", "Kedi",
      "Scottish Fold Shorthair", "SELÇUK CEBECI", "5059436004"),
  PetRecord("GÜMÜŞ VETERİNER - MAYA", "AT37837129", "Kedi", "Tekir",
      "ÖZLEM KÜÇÜK", "5466385129"),
  PetRecord("GÜMÜŞ VETERİNER - Çakıl", "AT40453285", "Kedi", "Tekir",
      "ZEYNEP SUDE AYTAN", "5436306557"),
  PetRecord("GÜMÜŞ VETERİNER - Pina", "AT51367199", "Kedi", "Tekir",
      "HASTA SAHIBI", "5436090619"),
  PetRecord("GÜMÜŞ VETERİNER - Hera", "AT49946798", "Kedi", "British Shorthair",
      "NESRIN KOCA", "5337146974"),
  PetRecord("GÜMÜŞ VETERİNER - Lucky", "AT84855406", "Kedi", "Van",
      "NURDAN SEÇKIN ŞENSOY", "5074287395"),
  PetRecord("GÜMÜŞ VETERİNER - Köpük", "AT95544676", "Kedi",
      "British Shorthair", "LEVENT COŞKUN", "5392728274"),
  PetRecord("GÜMÜŞ VETERİNER - Çilek", "AT90312363", "Kedi",
      "Scottish Fold Shorthair", "ZEYNEP TÜRKAN", "5437145494"),
  PetRecord("GÜMÜŞ VETERİNER - Duman", "AT66093024", "Kedi", "Siamese",
      "ARZU YALÇıNKAYA", "5305221282"),
  PetRecord("GÜMÜŞ VETERİNER - Leydi +", "AT70129581", "Kedi",
      "British Shorthair", "CEMANUR AYGÜN", "5055447927"),
  PetRecord("GÜMÜŞ VETERİNER - Rambo", "AT45910242", "Kedi",
      "British Shorthair", "ZEYNEP İLHAN", "5412054087"),
  PetRecord("GÜMÜŞ VETERİNER - Melül", "AT80818850", "Kedi", "Tekir",
      "RÜMEYSA -", "5519694518"),
  PetRecord("GÜMÜŞ VETERİNER - Paşa", "AT87471563", "Köpek", "Dobermann",
      "DOĞAN KOÇOĞLU", "5326681674"),
  PetRecord("GÜMÜŞ VETERİNER - Maya", "AT40453285", "Kedi", "British Shorthair",
      "HAMIDE PATKAVAK", "5053568474"),
  PetRecord("GÜMÜŞ VETERİNER - Mia", "AT45910242", "Kedi", "Siamese",
      "LEVENT KAHRAMAN", "5435598769"),
  PetRecord("GÜMÜŞ VETERİNER - GÜMÜŞ", "AT47330642", "Kedi",
      "British Shorthair", "- -", "5434998326"),
  PetRecord("GÜMÜŞ VET - Ares", "AT82239250", "Kedi", "Tekir", "NURAY KÜÇÜK",
      "5438399224"),
  PetRecord("ölü GÜMÜŞ VETERİNER - Marik Luna", "AT17654346", "Kedi", "Tekir",
      "FURKAN DINÇ", "5458114759"),
  PetRecord("GÜMÜŞ VETERİNER - Kaju", "AT33800572", "Kedi", "British Shorthair",
      "YAĞMUR YıLMAZ", "5468907113"),
  PetRecord("GÜMÜŞ VETERİNER - Tarçın", "AT37837129", "Kedi",
      "British Shorthair", "TARÇıN ANNE", "5414414998"),
  PetRecord("GÜMÜŞ VETERİNER - Minnoş", "AT31184416", "Kedi", "Tekir",
      "İBRAHIM POLAT", "5436213030"),
  PetRecord("GÜMÜŞ VETERİNER - Boncuk", "AT43294086", "Kedi",
      "British Shorthair", "MEHMET EFE", "5423667042"),
  PetRecord("GÜMÜŞ VET - deneme", "AT13617790", "Kedi", "British Shorthair",
      "BURAK GÜMÜŞ", "5513980855"),
  PetRecord("GÜMÜŞ VETERİNER - Gece", "AT37837129", "Kedi", "Tekir",
      "BERKE CAN DURGUT", "5442843303"),
  PetRecord("GÜMÜŞ VETERİNER - Mila", "AT59440312", "Kedi",
      "Scottish Fold Longhair", "TAYFUN KANAK", "5457377677"),
  PetRecord("GÜMÜŞ VETERİNER - Asil Bal", "AT83435006", "Kedi",
      "British Shorthair", "ÖZGE ÖZKURT", "5418529455"),
  PetRecord("Fitnat -ölü", "AT51367199", "Kedi", "Tekir", "MINE ZENGIN",
      "5413936933"),
];

const sampleHospitalized = [
  HospitalRecord(
      'GÜMÜŞ VET - Luna',
      'DAMLA TOKUR',
      'Serum ve gözlem',
      'Oda 1',
      'Sıvı tedavisi, ateş takibi ve 4 saatte bir genel durum kontrolü',
      '5466696329',
      'İştah ve su tüketimi takip edilecek.'),
  HospitalRecord(
      'Tyson',
      'AHMET TOK',
      'Operasyon sonrası takip',
      'Oda 2',
      'Ağrı kontrolü, pansuman ve antibiyotik protokolü',
      '5422031281',
      'Dikiş bölgesi sabah akşam kontrol edilecek.'),
  HospitalRecord(
      'ZEYTİN',
      'ELİF GÜVEN',
      'Ateş ve iştahsızlık',
      'Oda 3',
      'Ateş düşürücü destek, kan tahlili kontrolü ve beslenme takibi',
      '5388388949',
      '24 saat gözlem önerildi.'),
];
