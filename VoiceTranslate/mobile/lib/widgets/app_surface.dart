import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';

class AppBackdrop extends StatelessWidget {
  const AppBackdrop({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) => DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: Theme.of(context).brightness == Brightness.dark
                ? const [Color(0xff10172c), AppTheme.ink, Color(0xff11182b)]
                : const [Color(0xfff0f2ff), Color(0xfff7f8fc), Color(0xfff1f8f7)],
          ),
        ),
        child: Stack(
          children: [
            Positioned(
              top: -125,
              right: -110,
              child: Container(
                width: 280,
                height: 280,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppTheme.indigo.withValues(alpha: 0.08),
                ),
              ),
            ),
            Positioned.fill(child: child),
          ],
        ),
      );
}

class BrandLockup extends StatelessWidget {
  const BrandLockup({this.compact = false, super.key});

  final bool compact;

  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: compact ? 40 : 48,
            height: compact ? 40 : 48,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(15),
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [AppTheme.indigo, Color(0xff555fe2)],
              ),
              boxShadow: [
                BoxShadow(
                  color: AppTheme.indigo.withValues(alpha: 0.26),
                  blurRadius: 22,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Icon(Icons.graphic_eq_rounded,
                color: Colors.white, size: compact ? 23 : 27),
          ),
          const SizedBox(width: 12),
          Text(
            'VoiceTranslate',
            style: TextStyle(
              fontSize: compact ? 17 : 19,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
        ],
      );
}

class AppBottomBar extends StatelessWidget {
  const AppBottomBar({required this.index, required this.onSelect, super.key});

  final int index;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) => NavigationBar(
        selectedIndex: index,
        onDestinationSelected: onSelect,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.grid_view_rounded), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.call_rounded), label: 'Calls'),
          NavigationDestination(icon: Icon(Icons.tune_rounded), label: 'Settings'),
        ],
      );
}

class Eyebrow extends StatelessWidget {
  const Eyebrow(this.label, {super.key});

  final String label;

  @override
  Widget build(BuildContext context) => Text(
        label.toUpperCase(),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: AppTheme.muted,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.1,
            ),
      );
}