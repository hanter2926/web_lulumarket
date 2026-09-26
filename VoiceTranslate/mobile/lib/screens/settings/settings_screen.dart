import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/theme/app_theme.dart';
import '../../models/user.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({required this.user, required this.onLogout, super.key});

  final User user;
  final Future<void> Function() onLogout;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  static const _languages = ['English', 'Spanish', 'French', 'Japanese', 'Arabic', 'Hindi'];
  static const _voices = ['Balanced', 'Warm', 'Clear'];
  String _preferredLanguage = 'English';
  String _translationLanguage = 'Spanish';
  String _voice = 'Balanced';
  bool _darkMode = AppTheme.themeMode.value == ThemeMode.dark;
  bool _loggingOut = false;

  @override
  void initState() {
    super.initState();
    _loadPreferences();
  }

  Future<void> _loadPreferences() async {
    final preferences = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _preferredLanguage = preferences.getString('preferred_language') ?? 'English';
      _translationLanguage = preferences.getString('translation_language') ?? 'Spanish';
      _voice = preferences.getString('voice_style') ?? 'Balanced';
    });
  }

  Future<void> _saveValue(String key, String value) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(key, value);
  }

  Future<void> _logout() async {
    setState(() => _loggingOut = true);
    try {
      await widget.onLogout();
    } finally {
      if (mounted) setState(() => _loggingOut = false);
    }
  }

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(22, 20, 22, 30),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 620),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Settings',
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                        )),
                const SizedBox(height: 5),
                const Text('Make VoiceTranslate yours.',
                    style: TextStyle(color: AppTheme.muted)),
                const SizedBox(height: 22),
                _ProfilePanel(user: widget.user),
                const SizedBox(height: 25),
                const _SettingsHeading(title: 'Translation'),
                const SizedBox(height: 10),
                _SettingsPanel(
                  children: [
                    _PreferenceDropdown(
                      icon: Icons.record_voice_over_outlined,
                      label: 'I speak',
                      value: _preferredLanguage,
                      options: _languages,
                      onChanged: (value) {
                        setState(() => _preferredLanguage = value);
                        _saveValue('preferred_language', value);
                      },
                    ),
                    const Divider(height: 1),
                    _PreferenceDropdown(
                      icon: Icons.translate_rounded,
                      label: 'Translate to',
                      value: _translationLanguage,
                      options: _languages,
                      onChanged: (value) {
                        setState(() => _translationLanguage = value);
                        _saveValue('translation_language', value);
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 22),
                const _SettingsHeading(title: 'Voice & appearance'),
                const SizedBox(height: 10),
                _SettingsPanel(
                  children: [
                    _PreferenceDropdown(
                      icon: Icons.graphic_eq_rounded,
                      label: 'Voice style',
                      value: _voice,
                      options: _voices,
                      onChanged: (value) {
                        setState(() => _voice = value);
                        _saveValue('voice_style', value);
                      },
                    ),
                    const Divider(height: 1),
                    SwitchListTile.adaptive(
                      contentPadding: const EdgeInsets.symmetric(horizontal: 15),
                      secondary: const Icon(Icons.dark_mode_outlined),
                      title: const Text('Dark appearance'),
                      value: _darkMode,
                      onChanged: (value) async {
                        setState(() => _darkMode = value);
                        await AppTheme.setDarkMode(value);
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                const Text('Voice style takes effect when voice output is connected.',
                    style: TextStyle(color: AppTheme.muted, fontSize: 12)),
                const SizedBox(height: 24),
                OutlinedButton.icon(
                  onPressed: _loggingOut ? null : _logout,
                  icon: _loggingOut
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.logout_rounded),
                  label: Text(_loggingOut ? 'Signing out...' : 'Sign out'),
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size.fromHeight(52),
                    foregroundColor: const Color(0xffe97985),
                    side: const BorderSide(color: Color(0xffd95466)),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
}

class _ProfilePanel extends StatelessWidget {
  const _ProfilePanel({required this.user});

  final User user;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(17),
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor,
          borderRadius: BorderRadius.circular(19),
        ),
        child: Row(
          children: [
            CircleAvatar(
              radius: 26,
              backgroundColor: AppTheme.indigo.withValues(alpha: 0.2),
              child: Text(user.displayName.trim().isEmpty
                  ? '?'
                  : user.displayName.trim()[0].toUpperCase(),
                  style: const TextStyle(color: AppTheme.indigo, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(user.displayName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(user.email,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
                ],
              ),
            ),
            const Icon(Icons.verified_user_outlined, color: AppTheme.mint, size: 20),
          ],
        ),
      );
}

class _SettingsHeading extends StatelessWidget {
  const _SettingsHeading({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) => Text(title,
      style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700));
}

class _SettingsPanel extends StatelessWidget {
  const _SettingsPanel({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor,
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(children: children),
      );
}

class _PreferenceDropdown extends StatelessWidget {
  const _PreferenceDropdown({
    required this.icon,
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
  });

  final IconData icon;
  final String label;
  final String value;
  final List<String> options;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(15, 5, 13, 5),
        child: Row(
          children: [
            Icon(icon, color: AppTheme.indigo, size: 21),
            const SizedBox(width: 12),
            Expanded(child: Text(label)),
            DropdownButton<String>(
              value: value,
              underline: const SizedBox.shrink(),
              items: options.map((option) => DropdownMenuItem(
                    value: option,
                    child: Text(option, overflow: TextOverflow.ellipsis),
                  )).toList(),
              onChanged: (selection) {
                if (selection != null) onChanged(selection);
              },
            ),
          ],
        ),
      );
}