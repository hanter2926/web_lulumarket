import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';
import '../models/preview_contact.dart';
import '../models/user.dart';
import '../routing/app_router.dart';
import '../services/auth_service.dart';
import '../widgets/app_surface.dart';
import 'settings/settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({this.initialIndex = 0, this.user, super.key});

  final int initialIndex;
  final User? user;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late int _selectedIndex = widget.initialIndex;
  late Future<User> _user = widget.user == null
      ? AuthService().currentUser()
      : Future<User>.value(widget.user);

  void _reloadUser() => setState(() => _user = AuthService().currentUser());

  @override
  Widget build(BuildContext context) => FutureBuilder<User>(
        future: _user,
        builder: (context, snapshot) => Scaffold(
          body: AppBackdrop(
            child: SafeArea(
              child: snapshot.connectionState == ConnectionState.waiting
                  ? const Center(child: CircularProgressIndicator())
                  : snapshot.hasError || !snapshot.hasData
                      ? _SessionError(onRetry: _reloadUser)
                      : IndexedStack(
                          index: _selectedIndex,
                          children: [
                            _HomeDashboard(
                              user: snapshot.data!,
                              onStartCall: () => Navigator.pushNamed(context, AppRouter.contacts),
                              onOpenSettings: () => setState(() => _selectedIndex = 2),
                            ),
                            const _CallsOverview(),
                            SettingsScreen(
                              user: snapshot.data!,
                              onLogout: _logout,
                            ),
                          ],
                        ),
            ),
          ),
          bottomNavigationBar: AppBottomBar(
            index: _selectedIndex,
            onSelect: (index) => setState(() => _selectedIndex = index),
          ),
        ),
      );

  Future<void> _logout() async {
    String? message;
    try {
      await AuthService().logout();
    } catch (_) {
      message = 'Server sign-out failed. Your local session was cleared.';
    }
    if (mounted) {
      if (message != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
      }
      Navigator.pushNamedAndRemoveUntil(context, AppRouter.login, (_) => false);
    }
  }
}

class _HomeDashboard extends StatefulWidget {
  const _HomeDashboard({
    required this.user,
    required this.onStartCall,
    required this.onOpenSettings,
  });

  final User user;
  final VoidCallback onStartCall;
  final VoidCallback onOpenSettings;

  @override
  State<_HomeDashboard> createState() => _HomeDashboardState();
}

class _HomeDashboardState extends State<_HomeDashboard> {
  final _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final filteredContacts = previewContacts
        .where((contact) => contact.name.toLowerCase().contains(_query.toLowerCase()))
        .take(3)
        .toList();
    final firstName = widget.user.displayName.trim().split(' ').first;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(22, 16, 22, 28),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 660),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Expanded(child: BrandLockup(compact: true)),
                  IconButton(
                    tooltip: 'Settings',
                    onPressed: widget.onOpenSettings,
                    icon: const Icon(Icons.settings_outlined),
                  ),
                  CircleAvatar(
                    radius: 20,
                    backgroundColor: AppTheme.indigo.withValues(alpha: 0.22),
                    child: Text(_initials(widget.user.displayName),
                        style: const TextStyle(color: AppTheme.indigo, fontWeight: FontWeight.w700)),
                  ),
                ],
              ),
              const SizedBox(height: 31),
              const Eyebrow('Your translation space'),
              const SizedBox(height: 7),
              Text('Good to see you, $firstName',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                      )),
              const SizedBox(height: 21),
              _TranslationHero(onStartCall: widget.onStartCall),
              const SizedBox(height: 26),
              TextField(
                controller: _search,
                onChanged: (value) => setState(() => _query = value),
                decoration: const InputDecoration(
                  hintText: 'Search contacts',
                  prefixIcon: Icon(Icons.search_rounded),
                ),
              ),
              const SizedBox(height: 25),
              Row(
                children: [
                  Expanded(
                    child: Text('Contacts',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w700,
                            )),
                  ),
                  _PreviewLabel(),
                  TextButton(
                    onPressed: widget.onStartCall,
                    child: const Text('See all'),
                  ),
                ],
              ),
              const SizedBox(height: 5),
              if (filteredContacts.isEmpty)
                const _InlineEmpty(message: 'No contacts match your search.')
              else
                ...filteredContacts.map((contact) => _ContactRow(
                      contact: contact,
                      onTap: () => Navigator.pushNamed(
                        context,
                        AppRouter.call,
                        arguments: contact.name,
                      ),
                    )),
              const SizedBox(height: 23),
              Text('Recent calls',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                      )),
              const SizedBox(height: 10),
              const _InlineEmpty(message: 'Your recent calls will appear here.'),
            ],
          ),
        ),
      ),
    );
  }
}

class _TranslationHero extends StatelessWidget {
  const _TranslationHero({required this.onStartCall});

  final VoidCallback onStartCall;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(20, 21, 20, 18),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xff293663), Color(0xff202b4b), Color(0xff174047)],
          ),
          border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(14),
              ),
              child: const Icon(Icons.graphic_eq_rounded, color: AppTheme.mint),
            ),
            const SizedBox(height: 18),
            Text('Make every word\nfeel closer.',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      color: Colors.white,
                      height: 1.12,
                      fontWeight: FontWeight.w800,
                    )),
            const SizedBox(height: 9),
            Text('Start a voice translation conversation.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Colors.white70,
                    )),
            const SizedBox(height: 19),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: onStartCall,
                icon: const Icon(Icons.call_rounded, size: 19),
                label: const Text('Start translation call'),
                style: FilledButton.styleFrom(
                  backgroundColor: AppTheme.mint,
                  foregroundColor: AppTheme.ink,
                ),
              ),
            ),
          ],
        ),
      );
}

class _ContactRow extends StatelessWidget {
  const _ContactRow({required this.contact, required this.onTap});

  final PreviewContact contact;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
        onTap: onTap,
        leading: _ContactAvatar(contact: contact, size: 45),
        title: Text(contact.name, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(contact.detail,
            maxLines: 1, overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
        trailing: Icon(Icons.chevron_right_rounded,
            color: Theme.of(context).colorScheme.onSurfaceVariant),
      );
}

class _ContactAvatar extends StatelessWidget {
  const _ContactAvatar({required this.contact, required this.size});

  final PreviewContact contact;
  final double size;

  @override
  Widget build(BuildContext context) => Stack(
        children: [
          CircleAvatar(
            radius: size / 2,
            backgroundColor: contact.color.withValues(alpha: 0.2),
            child: Text(contact.initials,
                style: TextStyle(color: contact.color, fontWeight: FontWeight.w700)),
          ),
          if (contact.isOnline)
            Positioned(
              bottom: 0,
              right: 0,
              child: Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: AppTheme.mint,
                  shape: BoxShape.circle,
                  border: Border.all(color: Theme.of(context).scaffoldBackgroundColor, width: 2),
                ),
              ),
            ),
        ],
      );
}

class _PreviewLabel extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: AppTheme.indigo.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(8),
        ),
        child: const Text('Preview',
            style: TextStyle(color: AppTheme.indigo, fontSize: 10, fontWeight: FontWeight.w700)),
      );
}

class _InlineEmpty extends StatelessWidget {
  const _InlineEmpty({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor.withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Theme.of(context).dividerColor.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            const Icon(Icons.info_outline_rounded, color: AppTheme.muted, size: 19),
            const SizedBox(width: 10),
            Expanded(child: Text(message, style: const TextStyle(color: AppTheme.muted))),
          ],
        ),
      );
}

class _CallsOverview extends StatelessWidget {
  const _CallsOverview();

  @override
  Widget build(BuildContext context) => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(26),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 74,
                  height: 74,
                  decoration: BoxDecoration(
                    color: AppTheme.indigo.withValues(alpha: 0.13),
                    borderRadius: BorderRadius.circular(24),
                  ),
                  child: const Icon(Icons.call_outlined, color: AppTheme.indigo, size: 32),
                ),
                const SizedBox(height: 21),
                Text('No calls yet',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                        )),
                const SizedBox(height: 8),
                const Text('Your call history will show up here once calling is connected.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppTheme.muted, height: 1.45)),
              ],
            ),
          ),
        ),
      );
}

class _SessionError extends StatelessWidget {
  const _SessionError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_rounded, color: AppTheme.muted, size: 38),
              const SizedBox(height: 14),
              const Text('Could not load your profile',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 7),
              const Text('Check your connection, then try again.',
                  textAlign: TextAlign.center, style: TextStyle(color: AppTheme.muted)),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Try again'),
              ),
            ],
          ),
        ),
      );
}

String _initials(String name) {
  final parts = name.trim().split(RegExp(r'\s+'));
  return parts.take(2).map((part) => part.isNotEmpty ? part[0] : '').join().toUpperCase();
}