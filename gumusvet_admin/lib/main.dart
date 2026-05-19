import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

const String apiBaseUrl = 'https://wwwgumusvet.com';

void main() {
  runApp(const GumusVetAdminApp());
}

class GumusVetAdminApp extends StatelessWidget {
  const GumusVetAdminApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Gumus Vet Admin',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0F6E56),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      home: const AuthGate(),
    );
  }
}

class ApiClient {
  ApiClient(this.storage);

  final FlutterSecureStorage storage;

  Future<String?> get token => storage.read(key: 'admin_token');

  Future<Map<String, dynamic>> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? body,
  }) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    final savedToken = await token;
    if (savedToken != null) {
      headers['Authorization'] = 'Bearer $savedToken';
    }
    final uri = Uri.parse('$apiBaseUrl$path');
    late http.Response response;
    if (method == 'POST') {
      response = await http.post(uri, headers: headers, body: jsonEncode(body ?? {}));
    } else if (method == 'PATCH') {
      response = await http.patch(uri, headers: headers, body: jsonEncode(body ?? {}));
    } else if (method == 'DELETE') {
      response = await http.delete(uri, headers: headers);
    } else {
      response = await http.get(uri, headers: headers);
    }
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    if (decoded['success'] != true) {
      throw Exception(decoded['message'] ?? 'İşlem başarısız.');
    }
    return decoded;
  }
}

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

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
    storage.read(key: 'admin_token').then((value) {
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
    return token == null ? LoginPage(storage: storage) : AdminShell(storage: storage);
  }
}

class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.storage});
  final FlutterSecureStorage storage;

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
        '/api/admin/login',
        method: 'POST',
        body: {'username': username.text.trim(), 'password': password.text},
      );
      final token = response['data']['token'] as String;
      await widget.storage.write(key: 'admin_token', value: token);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => AdminShell(storage: widget.storage)),
      );
    } catch (_) {
      setState(() => error = 'Giriş başarısız. Kullanıcı adı veya şifre hatalı.');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Card(
            margin: const EdgeInsets.all(20),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.pets, size: 48, color: Color(0xFF0F6E56)),
                  const SizedBox(height: 12),
                  const Text('Gümüş Vet Admin', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 20),
                  TextField(controller: username, decoration: const InputDecoration(labelText: 'Kullanıcı adı')),
                  TextField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: 'Şifre')),
                  if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: Colors.red))),
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
  const AdminShell({super.key, required this.storage});
  final FlutterSecureStorage storage;

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
  int index = 0;

  @override
  Widget build(BuildContext context) {
    final api = ApiClient(widget.storage);
    final pages = [
      DashboardPage(api: api),
      ProductPage(api: api),
      ServicePage(api: api),
      AppointmentPage(api: api),
    ];
    return Scaffold(
      appBar: AppBar(
        title: const Text('Gümüş Veteriner Yönetim'),
        actions: [
          IconButton(
            onPressed: () async {
              await widget.storage.delete(key: 'admin_token');
              if (!mounted) return;
              Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => LoginPage(storage: widget.storage)));
            },
            icon: const Icon(Icons.logout),
            tooltip: 'Çıkış',
          )
        ],
      ),
      body: Row(
        children: [
          NavigationRail(
            selectedIndex: index,
            onDestinationSelected: (value) => setState(() => index = value),
            labelType: NavigationRailLabelType.all,
            destinations: const [
              NavigationRailDestination(icon: Icon(Icons.dashboard), label: Text('Panel')),
              NavigationRailDestination(icon: Icon(Icons.inventory_2), label: Text('Ürün')),
              NavigationRailDestination(icon: Icon(Icons.medical_services), label: Text('Hizmet')),
              NavigationRailDestination(icon: Icon(Icons.event), label: Text('Randevu')),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(child: pages[index]),
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
        api.request('/api/admin/products'),
        api.request('/api/admin/services'),
        api.request('/api/admin/appointments'),
      ]),
      builder: (context, snapshot) {
        if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
        final data = snapshot.data as List<Map<String, dynamic>>;
        return GridView.count(
          padding: const EdgeInsets.all(20),
          crossAxisCount: MediaQuery.sizeOf(context).width > 720 ? 3 : 1,
          childAspectRatio: 2.6,
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          children: [
            StatCard(title: 'Ürünler', value: '${(data[0]['data'] as List).length}', icon: Icons.inventory_2),
            StatCard(title: 'Hizmetler', value: '${(data[1]['data'] as List).length}', icon: Icons.medical_services),
            StatCard(title: 'Randevular', value: '${(data[2]['data'] as List).length}', icon: Icons.event),
          ],
        );
      },
    );
  }
}

class StatCard extends StatelessWidget {
  const StatCard({super.key, required this.title, required this.value, required this.icon});
  final String title;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(leading: Icon(icon, color: const Color(0xFF0F6E56)), title: Text(title), subtitle: Text(value, style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold))),
    );
  }
}

class ProductPage extends StatelessWidget {
  const ProductPage({super.key, required this.api});
  final ApiClient api;
  @override
  Widget build(BuildContext context) => CrudListPage(
    title: 'Ürün Yönetimi',
    loadPath: '/api/admin/products',
    addPath: '/api/admin/products/add',
    updatePath: '/api/admin/products/update',
    deletePath: '/api/admin/products/delete',
    api: api,
  );
}

class ServicePage extends StatelessWidget {
  const ServicePage({super.key, required this.api});
  final ApiClient api;
  @override
  Widget build(BuildContext context) => CrudListPage(
    title: 'Hizmet Yönetimi',
    loadPath: '/api/admin/services',
    addPath: '/api/admin/services/add',
    updatePath: '/api/admin/services/update',
    deletePath: '/api/admin/services/delete',
    api: api,
  );
}

class CrudListPage extends StatefulWidget {
  const CrudListPage({super.key, required this.title, required this.loadPath, required this.addPath, required this.updatePath, required this.deletePath, required this.api});
  final String title;
  final String loadPath;
  final String addPath;
  final String updatePath;
  final String deletePath;
  final ApiClient api;

  @override
  State<CrudListPage> createState() => _CrudListPageState();
}

class _CrudListPageState extends State<CrudListPage> {
  late Future<Map<String, dynamic>> future;

  @override
  void initState() {
    super.initState();
    future = widget.api.request(widget.loadPath);
  }

  void reload() => setState(() => future = widget.api.request(widget.loadPath));

  Future<void> save({Map<String, dynamic>? item}) async {
    final name = TextEditingController(text: item?['name']?.toString() ?? '');
    final price = TextEditingController(text: item?['price']?.toString() ?? '0');
    await showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(item == null ? 'Yeni kayıt' : 'Kaydı güncelle'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: name, decoration: const InputDecoration(labelText: 'Ad')),
            TextField(controller: price, decoration: const InputDecoration(labelText: 'Fiyat'), keyboardType: TextInputType.number),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Vazgeç')),
          FilledButton(
            onPressed: () async {
              final body = {'name': name.text, 'price': double.tryParse(price.text) ?? 0, 'category': 'Genel', 'stock': 0};
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
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      builder: (context, snapshot) {
        if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
        final rows = snapshot.data!['data'] as List;
        return Scaffold(
          body: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: rows.length,
            itemBuilder: (_, index) {
              final item = rows[index] as Map<String, dynamic>;
              return Card(
                child: ListTile(
                  title: Text(item['name']?.toString() ?? '-'),
                  subtitle: Text('₺${item['price'] ?? 0}'),
                  trailing: Wrap(children: [
                    IconButton(icon: const Icon(Icons.edit), onPressed: () => save(item: item)),
                    IconButton(icon: const Icon(Icons.delete), onPressed: () async { await widget.api.request('${widget.deletePath}/${item['id']}', method: 'DELETE'); reload(); }),
                  ]),
                ),
              );
            },
          ),
          floatingActionButton: FloatingActionButton.extended(onPressed: () => save(), icon: const Icon(Icons.add), label: Text(widget.title)),
        );
      },
    );
  }
}

class AppointmentPage extends StatefulWidget {
  const AppointmentPage({super.key, required this.api});
  final ApiClient api;
  @override
  State<AppointmentPage> createState() => _AppointmentPageState();
}

class _AppointmentPageState extends State<AppointmentPage> {
  late Future<Map<String, dynamic>> future = widget.api.request('/api/admin/appointments');
  void reload() => setState(() => future = widget.api.request('/api/admin/appointments'));

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      builder: (context, snapshot) {
        if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
        final rows = snapshot.data!['data'] as List;
        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: rows.length,
          itemBuilder: (_, index) {
            final item = rows[index] as Map<String, dynamic>;
            return Card(
              child: ListTile(
                title: Text('${item['first_name']} ${item['last_name']} - ${item['pet_name'] ?? item['pet_type']}'),
                subtitle: Text('${item['appt_date']} ${item['appt_time']} • ${item['status']}'),
                trailing: PopupMenuButton<String>(
                  onSelected: (status) async {
                    await widget.api.request('/api/admin/appointments/update/${item['id']}', method: 'PATCH', body: {'status': status});
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
    );
  }
}
