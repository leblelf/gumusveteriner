import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'core/constants/app_constants.dart';
import 'core/network/api_service.dart';

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
      themeMode = themeMode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
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
  final dark = brightness == Brightness.dark;
  final background = dark ? const Color(0xFF0F1513) : const Color(0xFFF3F7FA);
  final surface = dark ? const Color(0xFF18221F) : Colors.white;
  final border = dark ? const Color(0xFF2A3934) : const Color(0xFFDDE7ED);
  final fill = dark ? const Color(0xFF202B27) : const Color(0xFFF7FAFC);
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    scaffoldBackgroundColor: background,
    colorScheme: ColorScheme.fromSeed(
      seedColor: const Color(0xFFFF8A1E),
      brightness: brightness,
      primary: const Color(0xFFFF8A1E),
      secondary: const Color(0xFF0EB88A),
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
        borderSide: const BorderSide(color: Color(0xFF0F6E56)),
      ),
    ),
    dividerTheme: DividerThemeData(color: border),
  );
}

Color appSurface(BuildContext context) => Theme.of(context).cardTheme.color ?? Theme.of(context).colorScheme.surface;
Color appBackground(BuildContext context) => Theme.of(context).scaffoldBackgroundColor;
Color appBorder(BuildContext context) => Theme.of(context).dividerTheme.color ?? const Color(0xFFDDE7ED);
Color appMuted(BuildContext context) => Theme.of(context).colorScheme.onSurface.withOpacity(.62);
Color appOrange(BuildContext context) => Theme.of(context).colorScheme.primary;

class ApiClient {
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
  const AuthGate({super.key, required this.themeMode, required this.onToggleTheme});

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
    storage.read(key: AppConstants.tokenKey).then((value) {
      setState(() {
        token = value;
        loading = false;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return token == null
        ? LoginPage(storage: storage, themeMode: widget.themeMode, onToggleTheme: widget.onToggleTheme)
        : AdminShell(storage: storage, themeMode: widget.themeMode, onToggleTheme: widget.onToggleTheme);
  }
}

class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.storage, required this.themeMode, required this.onToggleTheme});

  final FlutterSecureStorage storage;
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final username = TextEditingController(text: 'admin');
  final password = TextEditingController();
  bool loading = false;
  String? error;

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
                  if (error != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text(error!, style: const TextStyle(color: Color(0xFFD93025))),
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
  const AdminShell({super.key, required this.storage, required this.themeMode, required this.onToggleTheme});

  final FlutterSecureStorage storage;
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
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
      SiteTextPage(api: api, query: query),
      UserManagementPage(api: api, query: query),
      SendSmsPage(api: api),
      AppointmentSlotsPage(api: api),
      ClinicSettingsPage(storage: widget.storage),
    ];
    final mobile = MediaQuery.sizeOf(context).width < 820;
    final content = Column(
      children: [
        TopBar(
          query: query,
          onQueryChanged: (value) => setState(() => query = value),
          onLogout: logout,
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
          for (var i = 0; i < items.length; i++)
            SidebarTile(
              icon: items[i].icon,
              label: items[i].label,
              active: selected == i,
              onTap: () => onSelected(i),
            ),
          const Spacer(),
          const Divider(height: 1),
          SidebarTile(
            icon: Icons.settings_outlined,
            label: 'Ayarlar & Klinik',
            active: selected == 11,
            onTap: () => onSelected(11),
          ),
          SidebarTile(icon: Icons.logout, label: 'Çıkış Yap', active: false, onTap: onLogout),
          const SizedBox(height: 18),
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
    final activeBg = Theme.of(context).brightness == Brightness.dark ? const Color(0xFF32261C) : const Color(0xFFFFF3E8);
    final activeBorder = Theme.of(context).brightness == Brightness.dark ? const Color(0xFF5A3B22) : const Color(0xFFFFD9B7);
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
        const Icon(Icons.pets, color: Color(0xFFF2A02D), size: 34),
        const SizedBox(width: 8),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Gümüş Veteriner',
              style: TextStyle(
                color: appOrange(context),
                fontWeight: FontWeight.w800,
                fontSize: compact ? 20 : 24,
                height: 1,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'PET YÖNETİMİ',
              style: TextStyle(
                color: const Color(0xFF61737B),
                fontSize: compact ? 10 : 12,
                letterSpacing: 1.8,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class TopBar extends StatelessWidget {
  const TopBar({
    super.key,
    required this.query,
    required this.onQueryChanged,
    required this.onLogout,
    required this.isDark,
    required this.onToggleTheme,
  });

  final String query;
  final ValueChanged<String> onQueryChanged;
  final VoidCallback onLogout;
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
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 430),
            child: TextField(
              onChanged: onQueryChanged,
              decoration: const InputDecoration(
                isDense: true,
                hintText: 'Pet, sahip veya randevu ara...',
                prefixIcon: Icon(Icons.search),
              ),
            ),
          ),
          const Spacer(),
          IconButton(
            onPressed: onToggleTheme,
            icon: Icon(isDark ? Icons.light_mode_outlined : Icons.dark_mode_outlined),
            tooltip: isDark ? 'Açık moda geç' : 'Karanlık moda geç',
          ),
          CircleAvatar(
            backgroundColor: const Color(0xFFFFF0D9),
            child: Text('Profil'.substring(0, 1), style: const TextStyle(color: Color(0xFFE2871B))),
          ),
          const SizedBox(width: 10),
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Dr. Gümüş', style: TextStyle(fontWeight: FontWeight.w800)),
              Text('Klinik yöneticisi', style: TextStyle(fontSize: 12, color: appMuted(context))),
            ],
          ),
          PopupMenuButton<String>(
            onSelected: (value) {
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
                Text(title, style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: Theme.of(context).colorScheme.onSurface)),
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

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key, required this.api});

  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: Future.wait([
        api.request(AppConstants.productsEndpoint),
        api.request(AppConstants.servicesEndpoint),
        api.request(AppConstants.appointmentsEndpoint),
      ]),
      builder: (context, snapshot) {
        final loading = snapshot.connectionState != ConnectionState.done;
        final data = snapshot.data as List<Map<String, dynamic>>?;
        final products = data == null ? 0 : (data[0]['data'] as List).length;
        final services = data == null ? 0 : (data[1]['data'] as List).length;
        final appointments = data == null ? 0 : (data[2]['data'] as List).length;
        return ListView(
          padding: EdgeInsets.zero,
          children: [
            const PageHeader(title: 'Dashboard', subtitle: 'Kliniğinizin genel durumunu takip edin.'),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  MetricCard(title: 'Toplam Pet', value: '${samplePets.length}', icon: Icons.pets_outlined, loading: false),
                  MetricCard(title: 'Randevular', value: '$appointments', icon: Icons.calendar_month_outlined, loading: loading),
                  MetricCard(title: 'Ürünler', value: '$products', icon: Icons.inventory_2_outlined, loading: loading),
                  MetricCard(title: 'Hizmetler', value: '$services', icon: Icons.medical_services_outlined, loading: loading),
                ],
              ),
            ),
            const SizedBox(height: 18),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Expanded(child: InfoPanel(title: 'Bugünün Akışı', lines: ['09:30 Genel muayene', '11:00 Aşı kontrolü', '14:00 Yatan hasta pansumanı'])),
                  SizedBox(width: 16),
                  Expanded(child: InfoPanel(title: 'Hızlı Notlar', lines: ['Düşük stok ürünleri kontrol et', 'Aşı hatırlatmalarını gönder', 'Yatan hasta raporlarını güncelle'])),
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
                backgroundColor: const Color(0xFFFFF1DF),
                child: Icon(icon, color: const Color(0xFFF29A2A)),
              ),
              const SizedBox(width: 14),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: TextStyle(color: appMuted(context))),
                  Text(loading ? '...' : value, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
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
            Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 12),
            for (final line in lines)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 7),
                child: Row(
                  children: [
                    Icon(Icons.check_circle_outline, size: 18, color: appOrange(context)),
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

class PetListPage extends StatefulWidget {
  const PetListPage({super.key, required this.query});

  final String query;

  @override
  State<PetListPage> createState() => _PetListPageState();
}

class _PetListPageState extends State<PetListPage> {
  String localQuery = '';
  bool grid = false;
  final List<PetRecord> pets = List.of(samplePets);

  List<PetRecord> get filtered {
    final q = '${widget.query} $localQuery'.trim().toLowerCase();
    if (q.isEmpty) return pets;
    return pets.where((pet) {
      return '${pet.name} ${pet.tag} ${pet.owner} ${pet.breed} ${pet.phone}'.toLowerCase().contains(q);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final rows = filtered;
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
                      onChanged: (value) => setState(() => localQuery = value),
                      decoration: const InputDecoration(
                        isDense: true,
                        hintText: 'Pet adı, sahip adı veya Künye No ile ara...',
                        prefixIcon: Icon(Icons.search),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  IconButton.filledTonal(
                    onPressed: () => ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Filtre alanı aktif. Arama kutusuna pet, sahip veya künye yazabilirsiniz.'))),
                    icon: const Icon(Icons.filter_alt_outlined),
                    tooltip: 'Filtrele',
                  ),
                  IconButton.filledTonal(onPressed: () => setState(() => grid = true), icon: const Icon(Icons.grid_view_outlined), tooltip: 'Kart görünümü'),
                  IconButton.filled(onPressed: () => setState(() => grid = false), icon: const Icon(Icons.view_list_outlined), tooltip: 'Liste görünümü'),
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
                ? PetGrid(rows: rows)
                : PetTable(
                    rows: rows,
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
              Text('Toplam 64 kayıttan 1-${rows.length.clamp(0, 12)} arası gösteriliyor', style: TextStyle(color: appMuted(context))),
              const Spacer(),
              TextButton(onPressed: () => showPageMessage('Önceki sayfa'), child: const Text('Önceki')),
              FilledButton(onPressed: () => showPageMessage('1. sayfa'), child: const Text('1')),
              TextButton(onPressed: () => showPageMessage('2. sayfa'), child: const Text('2')),
              TextButton(onPressed: () => showPageMessage('6. sayfa'), child: const Text('6')),
              TextButton(onPressed: () => showPageMessage('Sonraki sayfa'), child: const Text('Sonraki')),
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
            TextField(controller: name, decoration: const InputDecoration(labelText: 'Pet adı')),
            const SizedBox(height: 10),
            TextField(controller: owner, decoration: const InputDecoration(labelText: 'Sahip adı')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () {
              if (name.text.trim().isEmpty) return;
              setState(() {
                pets.insert(
                  0,
                  PetRecord(name.text.trim(), 'AT${DateTime.now().millisecondsSinceEpoch.toString().substring(5, 13)}', 'Kedi', 'Belirtilmedi', owner.text.trim(), '-'),
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
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  void showPetDetail(PetRecord pet) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(pet.name),
        content: Text('Künye: ${pet.tag}\nTür: ${pet.type}\nIrk: ${pet.breed}\nSahip: ${pet.owner.isEmpty ? 'Sahipsiz' : pet.owner}\nTelefon: ${pet.phone}'),
        actions: [FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Tamam'))],
      ),
    );
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
            TextField(controller: name, decoration: const InputDecoration(labelText: 'Pet adı')),
            const SizedBox(height: 10),
            TextField(controller: owner, decoration: const InputDecoration(labelText: 'Sahip adı')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () {
              final index = pets.indexOf(pet);
              if (index >= 0) {
                setState(() {
                  pets[index] = PetRecord(name.text.trim(), pet.tag, pet.type, pet.breed, owner.text.trim(), pet.phone);
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

class PetTable extends StatelessWidget {
  const PetTable({super.key, required this.rows, required this.onDelete, required this.onDetail, required this.onEdit});

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
                DataColumn(label: Text('PET BİLGİSİ')),
                DataColumn(label: Text('TÜR / IRK')),
                DataColumn(label: Text('SAHİP')),
                DataColumn(label: Text('İLETİŞİM')),
                DataColumn(label: Text('İŞLEMLER')),
              ],
              rows: rows
                  .map(
                    (pet) => DataRow(
                      cells: [
                        DataCell(PetIdentity(pet: pet)),
                        DataCell(Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(pet.type, style: const TextStyle(fontWeight: FontWeight.w800)),
                            Text(pet.breed, style: const TextStyle(fontSize: 12, color: Color(0xFF75868E))),
                          ],
                        )),
                        DataCell(OwnerBadge(pet: pet)),
                        DataCell(Row(children: [const Icon(Icons.phone_outlined, size: 16, color: Color(0xFFF29A2A)), const SizedBox(width: 8), Text(pet.phone)])),
                        DataCell(PopupMenuButton<String>(
                          onSelected: (value) {
                            if (value == 'detail') onDetail(pet);
                            if (value == 'edit') onEdit(pet);
                            if (value == 'delete') onDelete(pet);
                          },
                          itemBuilder: (_) => const [
                            PopupMenuItem(value: 'detail', child: Text('Detay')),
                            PopupMenuItem(value: 'edit', child: Text('Düzenle')),
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
  const PetGrid({super.key, required this.rows});

  final List<PetRecord> rows;

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
                PetIdentity(pet: pet),
                const Spacer(),
                Text('${pet.type} / ${pet.breed}', style: TextStyle(color: appMuted(context))),
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
  const PetIdentity({super.key, required this.pet});

  final PetRecord pet;

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
          child: Icon(pet.type == 'Kedi' ? Icons.cruelty_free_outlined : Icons.pets, color: const Color(0xFFF29A2A), size: 18),
        ),
        const SizedBox(width: 12),
        Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(pet.name, style: const TextStyle(fontWeight: FontWeight.w800)),
            Text(pet.tag, style: const TextStyle(fontSize: 11, color: Color(0xFFE3A35A), fontWeight: FontWeight.w700)),
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
        decoration: BoxDecoration(color: const Color(0xFFFFE7EA), borderRadius: BorderRadius.circular(99)),
        child: const Text('SAHİPSİZ', style: TextStyle(color: Color(0xFFE22E4C), fontSize: 11, fontWeight: FontWeight.w800)),
      );
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.person_outline, size: 15, color: Color(0xFFF29A2A)),
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
  late Future<Map<String, dynamic>> future = widget.api.request(AppConstants.appointmentsEndpoint);

  void reload() => setState(() => future = widget.api.request(AppConstants.appointmentsEndpoint));

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(title: 'Randevular', subtitle: 'Randevu durumlarını yönetin.'),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return ErrorState(message: snapshot.error.toString(), onRetry: reload);
              }
              if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows.where((item) => (item as Map<String, dynamic>).values.join(' ').toLowerCase().contains(q)).toList();
              if (rows.isEmpty) return const Center(child: Text('Henüz randevu yok.'));
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  return Card(
                    child: ListTile(
                      leading: const CircleAvatar(backgroundColor: Color(0xFFFFF1DF), child: Icon(Icons.calendar_month_outlined, color: Color(0xFFF29A2A))),
                      title: Text('${item['first_name']} ${item['last_name']} - ${item['pet_name'] ?? item['pet_type']}'),
                      subtitle: Text('${item['appt_date']} ${item['appt_time']} • ${item['status']}'),
                      trailing: PopupMenuButton<String>(
                        onSelected: (status) async {
                          await widget.api.request('${AppConstants.appointmentsUpdateEndpoint}/${item['id']}', method: 'PATCH', body: {'status': status});
                          reload();
                        },
                        itemBuilder: (_) => const [
                          PopupMenuItem(value: 'pending', child: Text('Bekliyor')),
                          PopupMenuItem(value: 'confirmed', child: Text('Onaylandı')),
                          PopupMenuItem(value: 'completed', child: Text('Tamamlandı')),
                          PopupMenuItem(value: 'cancelled', child: Text('İptal')),
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

class HospitalizedPage extends StatelessWidget {
  const HospitalizedPage({super.key, required this.query});

  final String query;

  @override
  Widget build(BuildContext context) {
    final rows = sampleHospitalized.where((item) => '${item.pet} ${item.owner} ${item.reason}'.toLowerCase().contains(query.toLowerCase())).toList();
    return Column(
      children: [
        PageHeader(
          title: 'Yatan Hastalar',
          subtitle: 'Klinikte takip edilen hastaların oda ve durum kayıtları.',
          action: FilledButton.icon(
            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Hasta yatışı ekleme ekranı hazır. Kalıcı kayıt için yatan hasta API endpointi bağlanabilir.'))),
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
                  leading: const CircleAvatar(backgroundColor: Color(0xFFFFF1DF), child: Icon(Icons.local_hospital_outlined, color: Color(0xFFF29A2A))),
                  title: Text(item.pet, style: const TextStyle(fontWeight: FontWeight.w800)),
                  subtitle: Text('${item.owner} • ${item.reason}'),
                  trailing: Chip(label: Text(item.room)),
                ),
              );
            },
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
    final price = TextEditingController(text: item?['price']?.toString() ?? '0');
    final category = TextEditingController(text: item?['category']?.toString() ?? 'Genel');
    final stock = TextEditingController(text: item?['stock']?.toString() ?? '0');
    final isProduct = widget.loadPath == AppConstants.productsEndpoint;
    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(item == null ? 'Yeni kayıt' : 'Kaydı güncelle'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: name, decoration: const InputDecoration(labelText: 'Ad')),
            const SizedBox(height: 10),
            TextField(controller: category, decoration: const InputDecoration(labelText: 'Kategori')),
            const SizedBox(height: 10),
            TextField(controller: price, decoration: const InputDecoration(labelText: 'Fiyat'), keyboardType: TextInputType.number),
            if (isProduct) ...[
              const SizedBox(height: 10),
              TextField(controller: stock, decoration: const InputDecoration(labelText: 'Stok'), keyboardType: TextInputType.number),
            ],
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () async {
              final body = {'name': name.text, 'price': double.tryParse(price.text) ?? 0, 'category': category.text, 'stock': int.tryParse(stock.text) ?? 0};
              if (item == null) {
                await widget.api.request(widget.addPath, method: 'POST', body: body);
              } else {
                await widget.api.request('${widget.updatePath}/${item['id']}', method: 'PATCH', body: body);
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
          action: FilledButton.icon(onPressed: () => save(), icon: const Icon(Icons.add), label: const Text('Yeni Ekle')),
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
                return ErrorState(message: snapshot.error.toString(), onRetry: reload);
              }
              if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = '${widget.query} $localQuery'.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows.where((item) => (item as Map<String, dynamic>).values.join(' ').toLowerCase().contains(q)).toList();
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  return Card(
                    child: ListTile(
                      leading: const CircleAvatar(backgroundColor: Color(0xFFFFF1DF), child: Icon(Icons.inventory_2_outlined, color: Color(0xFFF29A2A))),
                      title: Text(item['name']?.toString() ?? '-', style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text('${item['category'] ?? 'Genel'} • ₺${item['price'] ?? 0}'),
                      trailing: Wrap(
                        children: [
                          IconButton(icon: const Icon(Icons.edit_outlined), onPressed: () => save(item: item)),
                          IconButton(
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () async {
                              await widget.api.request('${widget.deletePath}/${item['id']}', method: 'DELETE');
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
  late Future<Map<String, dynamic>> future = widget.api.request(AppConstants.ordersEndpoint);

  void reload() => setState(() => future = widget.api.request(AppConstants.ordersEndpoint));

  String statusLabel(String status) {
    return {
      'pending': 'Bekliyor',
      'confirmed': 'Onaylandı',
      'shipped': 'Kargoya verildi',
      'delivered': 'Teslim edildi',
      'cancelled': 'İptal',
    }[status] ?? status;
  }

  Future<void> updateStatus(Map<String, dynamic> order, String status) async {
    final result = await widget.api.request('${AppConstants.ordersUpdateEndpoint}/${order['id']}', method: 'PATCH', body: {'status': status});
    final mail = result['data'] is Map ? (result['data']['mail'] as Map?) : null;
    if (!mounted) return;
    final extra = status == 'shipped'
        ? (mail == null ? ' Mail ayarı yoksa gönderim atlanır.' : ' Mail: ${mail['message']}')
        : '';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Sipariş durumu güncellendi.$extra')));
    reload();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(title: 'Gelen Siparişler', subtitle: 'Site üzerinden gelen siparişleri ve kargo durumunu yönetin.'),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError) return ErrorState(message: snapshot.error.toString(), onRetry: reload);
              if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final rows = q.isEmpty ? allRows : allRows.where((item) => (item as Map<String, dynamic>).values.join(' ').toLowerCase().contains(q)).toList();
              if (rows.isEmpty) return const Center(child: Text('Henüz sipariş yok.'));
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final order = rows[index] as Map<String, dynamic>;
                  final items = (order['items'] as List?) ?? [];
                  final status = order['status']?.toString() ?? 'pending';
                  return Card(
                    child: ExpansionTile(
                      leading: CircleAvatar(backgroundColor: appOrange(context).withOpacity(.12), child: Icon(Icons.shopping_bag_outlined, color: appOrange(context))),
                      title: Text('#${order['id']} ${order['first_name'] ?? ''} ${order['last_name'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text('${order['phone'] ?? '-'} • ₺${order['total'] ?? 0} • ${statusLabel(status)}'),
                      trailing: DropdownButton<String>(
                        value: status,
                        items: const [
                          DropdownMenuItem(value: 'pending', child: Text('Bekliyor')),
                          DropdownMenuItem(value: 'confirmed', child: Text('Onaylandı')),
                          DropdownMenuItem(value: 'shipped', child: Text('Kargoya verildi')),
                          DropdownMenuItem(value: 'delivered', child: Text('Teslim edildi')),
                          DropdownMenuItem(value: 'cancelled', child: Text('İptal')),
                        ],
                        onChanged: (value) {
                          if (value != null) updateStatus(order, value);
                        },
                      ),
                      childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
                      children: [
                        Align(alignment: Alignment.centerLeft, child: Text('Adres: ${order['address'] ?? '-'}')),
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
  late Future<Map<String, dynamic>> future = widget.api.request(AppConstants.reviewsEndpoint);

  void reload() => setState(() => future = widget.api.request(AppConstants.reviewsEndpoint));

  Future<void> replyTo(Map<String, dynamic> review) async {
    final reply = TextEditingController(text: review['reply']?.toString() ?? '');
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
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Vazgeç')),
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
          subtitle: 'Web sitesinde görünen müşteri yorumlarına klinik yanıtı yazın.',
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows.where((item) => (item as Map<String, dynamic>).values.join(' ').toLowerCase().contains(q)).toList();
              if (rows.isEmpty) return const Center(child: Text('Henüz yorum yok.'));
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  final rating = (int.tryParse('${item['rating']}') ?? 5).clamp(0, 5).toInt();
                  final stars = '${List.filled(rating, '★').join()}${List.filled(5 - rating, '☆').join()}';
                  return Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const CircleAvatar(child: Icon(Icons.reviews_outlined)),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text('${item['author']} — ${item['pet_type'] ?? 'Hasta Sahibi'}', style: const TextStyle(fontWeight: FontWeight.w800)),
                                    Text(stars, style: const TextStyle(color: Color(0xFFE9B872))),
                                  ],
                                ),
                              ),
                              Switch(
                                value: item['active'] == 1,
                                onChanged: (value) async {
                                  await widget.api.request('${AppConstants.reviewsUpdateEndpoint}/${item['id']}', method: 'PATCH', body: {'active': value ? 1 : 0});
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
                                color: Theme.of(context).colorScheme.primary.withOpacity(.08),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text('Gümüş Veteriner yanıtı: ${item['reply']}'),
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

class SiteTextPage extends StatefulWidget {
  const SiteTextPage({super.key, required this.api, required this.query});

  final ApiClient api;
  final String query;

  @override
  State<SiteTextPage> createState() => _SiteTextPageState();
}

class _SiteTextPageState extends State<SiteTextPage> {
  late Future<Map<String, dynamic>> future = widget.api.request(AppConstants.siteTextsEndpoint);

  void reload() => setState(() => future = widget.api.request(AppConstants.siteTextsEndpoint));

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
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Vazgeç')),
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
          subtitle: 'Web sitesindeki ana başlık ve açıklama metinlerini düzenleyin.',
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
              final allRows = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final rows = q.isEmpty
                  ? allRows
                  : allRows.where((item) => (item as Map<String, dynamic>).values.join(' ').toLowerCase().contains(q)).toList();
              return ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                itemCount: rows.length,
                itemBuilder: (_, index) {
                  final item = rows[index] as Map<String, dynamic>;
                  return Card(
                    child: ListTile(
                      leading: const CircleAvatar(child: Icon(Icons.edit_note_outlined)),
                      title: Text(item['label']?.toString() ?? '-', style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text(item['value']?.toString() ?? '', maxLines: 2, overflow: TextOverflow.ellipsis),
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
  late Future<Map<String, dynamic>> future = widget.api.request(AppConstants.usersEndpoint);

  void reload() => setState(() => future = widget.api.request(AppConstants.usersEndpoint));

  Future<void> updateUser(Map<String, dynamic> user, Map<String, dynamic> body) async {
    await widget.api.request('${AppConstants.usersUpdateEndpoint}/${user['id']}', method: 'PATCH', body: body);
    reload();
  }

  Future<void> deleteUser(Map<String, dynamic> user) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Üye silinsin mi?'),
        content: Text('${user['full_name']} kalıcı olarak silinecek.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Vazgeç')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Sil')),
        ],
      ),
    );
    if (ok != true) return;
    await widget.api.request('${AppConstants.usersDeleteEndpoint}/${user['id']}', method: 'DELETE');
    reload();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const PageHeader(
          title: 'Üyeler',
          subtitle: 'Siteye kayıt olan kullanıcıların iletişim, adres ve hayvan bilgileri.',
        ),
        Expanded(
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return ErrorState(message: snapshot.error.toString(), onRetry: reload);
              }
              if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
              final allUsers = snapshot.data!['data'] as List;
              final q = widget.query.trim().toLowerCase();
              final users = q.isEmpty
                  ? allUsers
                  : allUsers.where((item) => (item as Map<String, dynamic>).values.join(' ').toLowerCase().contains(q)).toList();
              if (users.isEmpty) return const Center(child: Text('Henüz üye yok.'));
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
                        child: Icon(Icons.person_outline, color: appOrange(context)),
                      ),
                      title: Text(user['full_name']?.toString() ?? '-', style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text('${user['email'] ?? '-'} • ${user['phone'] ?? '-'} • ${user['role'] ?? 'member'}'),
                      trailing: Chip(
                        label: Text(user['is_banned'] == 1 ? 'Banlı' : 'Aktif'),
                        backgroundColor: user['is_banned'] == 1 ? Colors.red.withOpacity(.12) : Colors.green.withOpacity(.12),
                      ),
                      childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
                      children: [
                        InfoSection(title: 'Adresler', rows: addresses.map((item) {
                          final row = item as Map<String, dynamic>;
                          return '${row['title'] ?? 'Adres'}: ${row['address'] ?? '-'} ${row['district'] ?? ''} ${row['city'] ?? ''}';
                        }).toList()),
                        const SizedBox(height: 12),
                        InfoSection(title: 'Hayvanlar', rows: pets.map((item) {
                          final row = item as Map<String, dynamic>;
                          return '${row['name'] ?? '-'} • ${row['species'] ?? '-'} • Yaş: ${row['age'] ?? '-'}';
                        }).toList()),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            FilledButton.tonalIcon(
                              onPressed: () => updateUser(user, {'is_banned': user['is_banned'] == 1 ? 0 : 1}),
                              icon: Icon(user['is_banned'] == 1 ? Icons.lock_open_outlined : Icons.block_outlined),
                              label: Text(user['is_banned'] == 1 ? 'Banı Kaldır' : 'Banla'),
                            ),
                            FilledButton.tonalIcon(
                              onPressed: () => updateUser(user, {'role': user['role'] == 'admin' ? 'member' : 'admin'}),
                              icon: const Icon(Icons.admin_panel_settings_outlined),
                              label: Text(user['role'] == 'admin' ? 'Üye Yap' : 'Admin Yap'),
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
              const Icon(Icons.warning_amber_rounded, color: Colors.orange, size: 42),
              const SizedBox(height: 10),
              const Text('Veri çekilemedi', style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              SizedBox(width: 420, child: Text(message, textAlign: TextAlign.center)),
              const SizedBox(height: 14),
              FilledButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Tekrar Dene')),
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
    return widget.api.request('${AppConstants.appointmentSlotsEndpoint}?date=$dateValue');
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
          subtitle: 'MHRS mantığıyla gün bazlı saatleri açıp kapatın. Dolu saatler müşteriye kapalı görünür.',
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
              if (snapshot.hasError) return ErrorState(message: snapshot.error.toString(), onRetry: reload);
              if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
              final rows = (snapshot.data!['data'] as List).cast<Map<String, dynamic>>();
              return GridView.builder(
                padding: const EdgeInsets.fromLTRB(28, 0, 28, 28),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: MediaQuery.sizeOf(context).width > 1100 ? 4 : 2,
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
                            child: Icon(taken ? Icons.lock_clock_outlined : Icons.schedule_outlined, color: color),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(slot['time'].toString(), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                                Text(
                                  taken ? 'Dolu' : (blocked ? 'Kapalı' : 'Uygun'),
                                  style: TextStyle(color: color, fontWeight: FontWeight.w700),
                                ),
                              ],
                            ),
                          ),
                          Switch(
                            value: available || taken,
                            onChanged: taken ? null : (value) => toggleSlot(slot, value),
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
          subtitle: 'Kayıtlı veya özel telefon numaralarına manuel SMS gönderin.',
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
                        Text('$length / 612 karakter', style: TextStyle(color: length > 612 ? Colors.red : appMuted(context))),
                        const Spacer(),
                        Text('Ticari SMS için izinli kullanıcı ve İYS kaydı gereklidir.', style: TextStyle(color: appMuted(context), fontSize: 12)),
                      ],
                    ),
                    if (result != null)
                      Container(
                        margin: const EdgeInsets.only(top: 14),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: success ? Colors.green.withOpacity(.12) : Colors.red.withOpacity(.12),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(result!, style: TextStyle(color: success ? Colors.green.shade700 : Colors.red.shade700)),
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
        PageHeader(title: 'Ayarlar & Klinik', subtitle: 'Klinik bilgileri, kullanıcı profili ve uygulama tercihleri.'),
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

class PetRecord {
  const PetRecord(this.name, this.tag, this.type, this.breed, this.owner, this.phone);

  final String name;
  final String tag;
  final String type;
  final String breed;
  final String owner;
  final String phone;
}

class HospitalRecord {
  const HospitalRecord(this.pet, this.owner, this.reason, this.room);

  final String pet;
  final String owner;
  final String reason;
  final String room;
}

const samplePets = [
  PetRecord('Pufi', 'AT41178684', 'Köpek', 'Pumi', '', '-'),
  PetRecord('Tyson', 'AT43294086', 'Köpek', 'Belçika Çoban Köpeği', 'AHMET TOK', '5422031281'),
  PetRecord('GÜMÜŞ VET - Leydi', 'AT40846798', 'Kedi', 'British Shorthair', 'MÜZEYYEN KOÇAK', '5467891974'),
  PetRecord('GÜMÜŞ VET - Luna', 'AT53983355', 'Kedi', 'Scottish Fold Shorthair', 'DAMLA TOKUR', '5466696329'),
  PetRecord('GÜMÜŞ VET - Luna', 'AT90865076', 'Kedi', 'Scottish Fold Shorthair', 'DAMLA TOKUR', '5466696329'),
  PetRecord('GÜMÜŞ VET - Bostik', 'AT25727459', 'Kedi', 'Scottish Fold Shorthair', 'MERAL ESKİ', '5350372889'),
  PetRecord('ZEYTİN', 'AT19074747', 'Kedi', 'British Shorthair', 'ELİF GÜVEN', '5388388949'),
  PetRecord('GÜMÜŞ VET - BAMBAM', 'AT04342820', 'Köpek', 'Toy Poodle', 'BEY BEY', '5379567360'),
  PetRecord('Tanımsız', 'AT33800572', 'Köpek', 'Cairn Terrier', 'YAĞMUR KETENCİ', '5396550195'),
  PetRecord('GÜMÜŞ VET - Ares', 'AT10001833', 'Köpek', 'Alman Çoban Köpeği', 'HAMZA KULAÇ', '5531372064'),
  PetRecord('GÜMÜŞ VET - TARÇIN', 'AT47330642', 'Kedi', 'British Shorthair', 'ADEM ÇOPOĞLU', '5441821979'),
  PetRecord('GÜMÜŞ VET - BABI', 'AT64672624', 'Kedi', 'Scottish Fold Shorthair', 'ELİF ŞİMŞEK', '5515529757'),
];

const sampleHospitalized = [
  HospitalRecord('GÜMÜŞ VET - Luna', 'DAMLA TOKUR', 'Serum ve gözlem', 'Oda 1'),
  HospitalRecord('Tyson', 'AHMET TOK', 'Operasyon sonrası takip', 'Oda 2'),
  HospitalRecord('ZEYTİN', 'ELİF GÜVEN', 'Ateş ve iştahsızlık', 'Oda 3'),
];
