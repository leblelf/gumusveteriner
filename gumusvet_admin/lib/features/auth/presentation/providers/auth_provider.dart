import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../core/constants/app_constants.dart';
import '../../../../core/network/api_service.dart';

enum AuthStatus { initial, loading, authenticated, unauthenticated, error }

class AuthState {
  const AuthState({
    this.status = AuthStatus.initial,
    this.errorMessage,
    this.token,
    this.username,
  });

  final AuthStatus status;
  final String? errorMessage;
  final String? token;
  final String? username;

  AuthState copyWith({
    AuthStatus? status,
    String? errorMessage,
    String? token,
    String? username,
  }) {
    return AuthState(
      status: status ?? this.status,
      errorMessage: errorMessage,
      token: token ?? this.token,
      username: username ?? this.username,
    );
  }
}

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier() : super(const AuthState()) {
    _checkExistingToken();
  }

  Future<void> _checkExistingToken() async {
    final prefs = await SharedPreferences.getInstance();
    final token = await ApiService.instance.token;
    final username = prefs.getString(AppConstants.savedUsernameKey);
    state = state.copyWith(
      status: token == null || token.isEmpty
          ? AuthStatus.unauthenticated
          : AuthStatus.authenticated,
      token: token,
      username: username,
    );
  }

  Future<void> login(String username, String password, bool rememberMe) async {
    state = state.copyWith(status: AuthStatus.loading, errorMessage: null);
    try {
      final response =
          await ApiService.instance.login(username.trim(), password);
      final token = response['data']?['token'] ?? response['token'];
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(AppConstants.rememberMeKey, rememberMe);
      if (rememberMe) {
        await prefs.setString(AppConstants.savedUsernameKey, username.trim());
      } else {
        await prefs.remove(AppConstants.savedUsernameKey);
      }
      state = state.copyWith(
        status: AuthStatus.authenticated,
        token: token?.toString(),
        username: username.trim(),
      );
    } catch (e) {
      state = state.copyWith(
        status: AuthStatus.error,
        errorMessage: e.toString(),
      );
    }
  }

  Future<void> logout() async {
    await ApiService.instance.logout();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(AppConstants.rememberMeKey);
    state = const AuthState(status: AuthStatus.unauthenticated);
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier();
});
