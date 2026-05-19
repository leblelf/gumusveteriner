class MockData {
  MockData._();

  static final Map<String, dynamic> dashboardStats = {
    'total_appointments': 0,
    'today_appointments': 0,
    'total_products': 0,
    'active_services': 0,
    'pending_appointments': 0,
    'monthly_revenue': 0.0,
  };

  static final List<Map<String, dynamic>> appointments = [];
  static final List<Map<String, dynamic>> products = [];
  static final List<Map<String, dynamic>> services = [];
}
