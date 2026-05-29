class AppConstants {
  AppConstants._();

  static const String appName = 'Gümüş Veteriner Admin';
  static const String appVersion = '1.0.0';

  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://wwwgumusvet.com',
  );

  static const String loginEndpoint = '/api/admin/login';
  static const String logoutEndpoint = '/api/admin/logout';
  static const String productsEndpoint = '/api/admin/products';
  static const String productsAddEndpoint = '/api/admin/products/add';
  static const String productsUpdateEndpoint = '/api/admin/products/update';
  static const String productsDeleteEndpoint = '/api/admin/products/delete';
  static const String servicesEndpoint = '/api/admin/services';
  static const String servicesAddEndpoint = '/api/admin/services/add';
  static const String servicesUpdateEndpoint = '/api/admin/services/update';
  static const String servicesDeleteEndpoint = '/api/admin/services/delete';
  static const String appointmentsEndpoint = '/api/admin/appointments';
  static const String appointmentsUpdateEndpoint = '/api/admin/appointments/update';
  static const String appointmentsDeleteEndpoint = '/api/admin/appointments/delete';
  static const String appointmentSlotsEndpoint = '/api/admin/appointment-slots';
  static const String reviewsEndpoint = '/api/admin/reviews';
  static const String reviewsUpdateEndpoint = '/api/admin/reviews/update';
  static const String contactsEndpoint = '/api/admin/contacts';
  static const String contactsReplyEndpoint = '/api/admin/contacts/reply';
  static const String siteTextsEndpoint = '/api/admin/site-texts';
  static const String siteTextsUpdateEndpoint = '/api/admin/site-texts/update';
  static const String usersEndpoint = '/api/admin/users';
  static const String usersUpdateEndpoint = '/api/admin/users/update';
  static const String usersDeleteEndpoint = '/api/admin/users/delete';
  static const String ordersEndpoint = '/api/admin/orders';
  static const String ordersUpdateEndpoint = '/api/admin/orders/update';
  static const String sendSmsEndpoint = '/api/admin/send-sms';
  static const String adminProfileEndpoint = '/api/admin/profile';
  static const String forgotPasswordEndpoint = '/api/forgot-password';

  static const String tokenKey = 'admin_token';
  static const String rememberMeKey = 'remember_me';
  static const String savedUsernameKey = 'saved_username';
  static const String themeKey = 'app_theme';
  static const String petViewModeKey = 'pet_view_mode';
  static const String quickNotesKey = 'quick_notes';
  static const String adminProfileNameKey = 'admin_profile_name';
  static const String adminProfilePhotoKey = 'admin_profile_photo';

  static const double sidebarWidth = 240.0;
  static const double sidebarCollapsedWidth = 72.0;
  static const double defaultPadding = 20.0;
  static const double cardRadius = 16.0;
  static const double buttonRadius = 12.0;

  static const int connectTimeout = 30000;
  static const int receiveTimeout = 30000;
}
