import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../constants/app_constants.dart';

class ApiService {
  ApiService._internal() {
    _dio = Dio(
      BaseOptions(
        baseUrl: AppConstants.baseUrl,
        connectTimeout:
            const Duration(milliseconds: AppConstants.connectTimeout),
        receiveTimeout:
            const Duration(milliseconds: AppConstants.receiveTimeout),
        headers: const {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _storage.read(key: AppConstants.tokenKey);
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) async {
          if (error.response?.statusCode == 401) {
            await _storage.delete(key: AppConstants.tokenKey);
          }
          handler.next(error);
        },
      ),
    );
  }

  static final ApiService instance = ApiService._internal();

  late final Dio _dio;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  static const String _localFallbackBaseUrl = 'http://127.0.0.1:5000';

  Future<String?> get token => _storage.read(key: AppConstants.tokenKey);

  Future<Map<String, dynamic>> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? body,
    Map<String, dynamic>? params,
  }) async {
    try {
      final response =
          await _send(path, method: method, body: body, params: params);
      final data = _asMap(response.data);
      if (data['success'] != true) {
        throw ApiException(
            message: (data['message'] ?? 'Islem basarisiz.').toString());
      }
      return data;
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  Future<Response<dynamic>> _send(
    String path, {
    required String method,
    Map<String, dynamic>? body,
    Map<String, dynamic>? params,
  }) async {
    try {
      return await _sendWith(_dio, path,
          method: method, body: body, params: params);
    } on DioException {
      if (AppConstants.baseUrl != _localFallbackBaseUrl) {
        final token = await _storage.read(key: AppConstants.tokenKey);
        final fallback = Dio(
          BaseOptions(
            baseUrl: _localFallbackBaseUrl,
            connectTimeout:
                const Duration(milliseconds: AppConstants.connectTimeout),
            receiveTimeout:
                const Duration(milliseconds: AppConstants.receiveTimeout),
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json',
              if (token != null && token.isNotEmpty)
                'Authorization': 'Bearer $token',
            },
          ),
        );
        return _sendWith(fallback, path,
            method: method, body: body, params: params);
      }
      rethrow;
    }
  }

  Future<Response<dynamic>> _sendWith(
    Dio client,
    String path, {
    required String method,
    Map<String, dynamic>? body,
    Map<String, dynamic>? params,
  }) {
    switch (method.toUpperCase()) {
      case 'POST':
        return client.post(path, data: body ?? {}, queryParameters: params);
      case 'PUT':
        return client.put(path, data: body ?? {}, queryParameters: params);
      case 'PATCH':
        return client.patch(path, data: body ?? {}, queryParameters: params);
      case 'DELETE':
        return client.delete(path, data: body, queryParameters: params);
      default:
        return client.get(path, queryParameters: params);
    }
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    throw ApiException(message: 'Sunucudan beklenmeyen cevap geldi.');
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final response = await request(
      AppConstants.loginEndpoint,
      method: 'POST',
      body: {'username': username, 'password': password},
    );
    final token = response['data']?['token'] ?? response['token'];
    if (token is! String || token.isEmpty) {
      throw ApiException(message: 'Token alinamadi.');
    }
    await _storage.write(key: AppConstants.tokenKey, value: token);
    return response;
  }

  Future<void> logout() async {
    await request(AppConstants.logoutEndpoint, method: 'POST')
        .catchError((_) => <String, dynamic>{});
    await _storage.delete(key: AppConstants.tokenKey);
  }

  Future<Map<String, dynamic>> getProducts() =>
      request(AppConstants.productsEndpoint);
  Future<Map<String, dynamic>> createProduct(Map<String, dynamic> data) =>
      request(AppConstants.productsAddEndpoint, method: 'POST', body: data);
  Future<Map<String, dynamic>> updateProduct(
          int id, Map<String, dynamic> data) =>
      request('${AppConstants.productsUpdateEndpoint}/$id',
          method: 'PATCH', body: data);
  Future<Map<String, dynamic>> deleteProduct(int id) =>
      request('${AppConstants.productsDeleteEndpoint}/$id', method: 'DELETE');

  Future<Map<String, dynamic>> getServices() =>
      request(AppConstants.servicesEndpoint);
  Future<Map<String, dynamic>> createService(Map<String, dynamic> data) =>
      request(AppConstants.servicesAddEndpoint, method: 'POST', body: data);
  Future<Map<String, dynamic>> updateService(
          int id, Map<String, dynamic> data) =>
      request('${AppConstants.servicesUpdateEndpoint}/$id',
          method: 'PATCH', body: data);
  Future<Map<String, dynamic>> deleteService(int id) =>
      request('${AppConstants.servicesDeleteEndpoint}/$id', method: 'DELETE');

  Future<Map<String, dynamic>> getAppointments() =>
      request(AppConstants.appointmentsEndpoint);
  Future<Map<String, dynamic>> updateAppointmentStatus(int id, String status) =>
      request('${AppConstants.appointmentsUpdateEndpoint}/$id',
          method: 'PATCH', body: {'status': status});
  Future<Map<String, dynamic>> deleteAppointment(int id) =>
      request('${AppConstants.appointmentsDeleteEndpoint}/$id',
          method: 'DELETE');
}

class ApiException implements Exception {
  const ApiException({required this.message, this.statusCode});

  final String message;
  final int? statusCode;

  factory ApiException.fromDioError(DioException e) {
    final data = e.response?.data;
    String? serverMessage;
    if (data is Map) {
      serverMessage =
          (data['message'] ?? data['error'] ?? data['detail'])?.toString();
    }

    if (serverMessage != null && serverMessage.isNotEmpty) {
      return ApiException(
          message: serverMessage, statusCode: e.response?.statusCode);
    }

    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return ApiException(
            message: 'Baglanti zaman asimina ugradi.', statusCode: 408);
      case DioExceptionType.badResponse:
        return ApiException(
            message: 'Sunucu istegi kabul etmedi.',
            statusCode: e.response?.statusCode);
      case DioExceptionType.cancel:
        return const ApiException(
            message: 'Istek iptal edildi.', statusCode: 0);
      default:
        return const ApiException(
            message: 'Sunucuya ulasilamiyor.', statusCode: 0);
    }
  }

  @override
  String toString() => message;
}
