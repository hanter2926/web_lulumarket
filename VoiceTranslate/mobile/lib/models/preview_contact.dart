import 'package:flutter/material.dart';

class PreviewContact {
  const PreviewContact({
    required this.name,
    required this.detail,
    required this.initials,
    required this.color,
    required this.isOnline,
  });

  final String name;
  final String detail;
  final String initials;
  final Color color;
  final bool isOnline;
}

const previewContacts = [
  PreviewContact(
    name: 'Sofia Martinez',
    detail: 'Spanish · Mexico City',
    initials: 'SM',
    color: Color(0xfff0a176),
    isOnline: true,
  ),
  PreviewContact(
    name: 'Kenji Watanabe',
    detail: 'Japanese · Tokyo',
    initials: 'KW',
    color: Color(0xff7fa9d7),
    isOnline: true,
  ),
  PreviewContact(
    name: 'Amara Okafor',
    detail: 'English · Lagos',
    initials: 'AO',
    color: Color(0xffc38cd2),
    isOnline: false,
  ),
  PreviewContact(
    name: 'Lucas Moreau',
    detail: 'French · Montreal',
    initials: 'LM',
    color: Color(0xff78c1a8),
    isOnline: false,
  ),
];