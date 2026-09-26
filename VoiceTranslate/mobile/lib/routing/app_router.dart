import 'package:flutter/material.dart';

import '../screens/call_screen.dart';
import '../screens/contact_selection_screen.dart';
import '../screens/auth/login_screen.dart';
import '../screens/auth/register_screen.dart';
import '../screens/home_screen.dart';
import '../screens/splash_screen.dart';
import '../models/user.dart';

class AppRouter {
  static const splash = '/';
  static const login = '/login';
  static const register = '/register';
  static const home = '/home';
  static const calls = '/calls';
  static const settings = '/settings';
  static const contacts = '/contacts';
  static const call = '/call';

  static Route<dynamic> onGenerateRoute(RouteSettings settings) {
    switch (settings.name) {
      case register:
        return MaterialPageRoute(builder: (_) => const RegisterScreen());
      case splash:
        return MaterialPageRoute(builder: (_) => const SplashScreen());
      case home:
        final user = settings.arguments as User?;
        return MaterialPageRoute(builder: (_) => HomeScreen(user: user));
      case calls:
        return MaterialPageRoute(builder: (_) => const HomeScreen(initialIndex: 1));
      case AppRouter.settings:
        return MaterialPageRoute(builder: (_) => const HomeScreen(initialIndex: 2));
      case contacts:
        return MaterialPageRoute(builder: (_) => const ContactSelectionScreen());
      case call:
        final contactName = settings.arguments as String? ?? 'Selected contact';
        return MaterialPageRoute(builder: (_) => CallScreen(contactName: contactName));
      case login:
      default:
        return MaterialPageRoute(builder: (_) => const LoginScreen());
    }
  }
}
