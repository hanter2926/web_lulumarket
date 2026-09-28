import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/theme/app_theme.dart';
import '../services/call_service.dart';
import '../widgets/app_surface.dart';

const _languages = ['English', 'Spanish', 'French', 'Japanese', 'Arabic', 'Hindi'];

class CallScreen extends StatefulWidget {
  const CallScreen({required this.contactName, this.callService, super.key});

  final String contactName;
  final CallService? callService;

  @override
  State<CallScreen> createState() => _CallScreenState();
}

class _CallScreenState extends State<CallScreen> {
  String _sourceLanguage = 'English';
  String _targetLanguage = 'Spanish';
  bool _muted = false;
  bool _connecting = false;
  String _connectionMessage = 'Live calling is not available yet.';
  late final CallService _callService = widget.callService ?? const UnavailableCallService();

  @override
  void initState() {
    super.initState();
    _loadLanguages();
  }

  Future<void> _loadLanguages() async {
    final preferences = await SharedPreferences.getInstance();
    if (!mounted) return;
    final source = preferences.getString('preferred_language');
    final target = preferences.getString('translation_language');
    setState(() {
      if (_languages.contains(source)) _sourceLanguage = source!;
      if (_languages.contains(target)) _targetLanguage = target!;
    });
  }

  Future<void> _tryConnect() async {
    setState(() {
      _connecting = true;
      _connectionMessage = 'Contacting the call service...';
    });
    try {
      await _callService.connect(CallRequest(
        contactName: widget.contactName,
        sourceLanguage: _sourceLanguage,
        targetLanguage: _targetLanguage,
      ));
      if (mounted) {
        setState(() => _connectionMessage =
            'The call service returned without establishing a live audio session.');
      }
    } catch (error) {
      if (mounted) {
        setState(() => _connectionMessage = error is CallConnectionException
            ? error.message
            : 'Unable to connect. Check your connection and try again.');
      }
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          leading: IconButton(
            tooltip: 'End preview',
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close_rounded),
          ),
          title: const Text('Translation call',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
        ),
        body: AppBackdrop(
          child: SafeArea(
            top: false,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 620),
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(22, 8, 22, 26),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: 9),
                      CircleAvatar(
                        radius: 39,
                        backgroundColor: AppTheme.indigo.withValues(alpha: 0.18),
                        child: Text(_initials(widget.contactName),
                            style: const TextStyle(
                                fontSize: 22,
                                color: AppTheme.indigo,
                                fontWeight: FontWeight.w700)),
                      ),
                      const SizedBox(height: 12),
                      Text(widget.contactName,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.w700,
                              )),
                      const SizedBox(height: 5),
                      const Text('Call preview',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: AppTheme.muted)),
                      const SizedBox(height: 19),
                      _ConnectionNotice(message: _connectionMessage),
                      const SizedBox(height: 17),
                      Row(
                        children: [
                          Expanded(
                            child: _LanguageSelector(
                              label: 'You speak',
                              value: _sourceLanguage,
                              onChanged: (value) => setState(() => _sourceLanguage = value),
                            ),
                          ),
                          const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 8),
                            child: Icon(Icons.swap_horiz_rounded, color: AppTheme.muted),
                          ),
                          Expanded(
                            child: _LanguageSelector(
                              label: 'Translate to',
                              value: _targetLanguage,
                              onChanged: (value) => setState(() => _targetLanguage = value),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 18),
                      OutlinedButton.icon(
                        onPressed: _connecting ? null : _tryConnect,
                        icon: _connecting
                            ? const SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.wifi_tethering_rounded),
                        label: Text(_connecting ? 'Connecting...' : 'Try connection'),
                      ),
                      const SizedBox(height: 18),
                      _TranscriptPanel(
                        icon: Icons.graphic_eq_rounded,
                        title: 'Live subtitles',
                        text: 'Subtitles will appear here when a call is connected.',
                        accent: AppTheme.mint,
                      ),
                      const SizedBox(height: 11),
                      _TranscriptPanel(
                        icon: Icons.translate_rounded,
                        title: 'Translated transcript',
                        text: 'Your translated words will appear here.',
                        accent: AppTheme.indigo,
                      ),
                      const SizedBox(height: 21),
                      const Text(
                        'Microphone and transcript controls are visual previews only.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: AppTheme.muted, fontSize: 12),
                      ),
                      const SizedBox(height: 15),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          _CallControl(
                            icon: _muted ? Icons.mic_off_rounded : Icons.mic_rounded,
                            label: _muted ? 'Muted' : 'Mute',
                            onPressed: () => setState(() => _muted = !_muted),
                          ),
                          const SizedBox(width: 28),
                          FilledButton.icon(
                            onPressed: () => Navigator.pop(context),
                            icon: const Icon(Icons.call_end_rounded),
                            label: const Text('End'),
                            style: FilledButton.styleFrom(
                              backgroundColor: const Color(0xffd95466),
                              foregroundColor: Colors.white,
                              minimumSize: const Size(116, 52),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
}

class _ConnectionNotice extends StatelessWidget {
  const _ConnectionNotice({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xffd95466).withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xffd95466).withValues(alpha: 0.25)),
        ),
        child: Row(
          children: [
            const Icon(Icons.cloud_off_rounded, color: Color(0xffe97985), size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Not connected', style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 3),
                  Text(
                    message,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: AppTheme.muted, fontSize: 12),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
}

class _LanguageSelector extends StatelessWidget {
  const _LanguageSelector({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
          const SizedBox(height: 6),
          DropdownButtonFormField<String>(
            initialValue: value,
            isExpanded: true,
            decoration: const InputDecoration(contentPadding: EdgeInsets.symmetric(horizontal: 11)),
            items: _languages
                .map((language) => DropdownMenuItem(value: language, child: Text(language)))
                .toList(),
            onChanged: (language) {
              if (language != null) onChanged(language);
            },
          ),
        ],
      );
}

class _TranscriptPanel extends StatelessWidget {
  const _TranscriptPanel({
    required this.icon,
    required this.title,
    required this.text,
    required this.accent,
  });

  final IconData icon;
  final String title;
  final String text;
  final Color accent;

  @override
  Widget build(BuildContext context) => Container(
        constraints: const BoxConstraints(minHeight: 116),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor.withValues(alpha: 0.82),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Theme.of(context).dividerColor.withValues(alpha: 0.25)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: accent, size: 19),
                const SizedBox(width: 8),
                Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 15),
            Text(text, style: const TextStyle(color: AppTheme.muted, height: 1.4)),
          ],
        ),
      );
}

class _CallControl extends StatelessWidget {
  const _CallControl({required this.icon, required this.label, required this.onPressed});

  final IconData icon;
  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => Column(
        children: [
          IconButton.filledTonal(
            tooltip: label,
            onPressed: onPressed,
            icon: Icon(icon),
            iconSize: 23,
            style: IconButton.styleFrom(fixedSize: const Size(52, 52)),
          ),
          const SizedBox(height: 5),
          Text(label, style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
        ],
      );
}

String _initials(String name) => name
    .trim()
    .split(RegExp(r'\s+'))
    .take(2)
    .map((part) => part.isNotEmpty ? part[0] : '')
    .join()
    .toUpperCase();