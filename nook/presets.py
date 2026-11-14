"""Portable, data-only appearance templates. Never execute imported content."""
import json
from pathlib import Path

PRESETS = {
    'Everyday': dict(width=840, music_height=132, compact_width=700, compact_height=42,
                     height=300, radius=20, opacity=100, desktop_theme='Glass'),
    'Focus': dict(width=760, music_height=132, compact_width=620, compact_height=40,
                  height=300, radius=18, opacity=100, desktop_theme='Paper'),
    'Studio': dict(width=960, music_height=140, compact_width=800, compact_height=44,
                   height=340, radius=22, opacity=100, desktop_theme='Midnight'),
}
DESCRIPTIONS = {
    'Everyday': 'A balanced music player and readable resting strip.',
    'Focus': 'Small and quiet, with space left for your work.',
    'Studio': 'More room for track names and desktop essentials.',
}
LIMITS = {'width': (460, 1100), 'music_height': (128, 240), 'compact_width': (320, 1100),
          'compact_height': (36, 90), 'height': (300, 850), 'radius': (8, 48), 'opacity': (65, 100)}
THEMES = ('Glass', 'Paper', 'Midnight', 'Graphite')


def validate_template(value):
    if not isinstance(value, dict) or value.get('format') != 'nook-appearance-v1':
        raise ValueError('Choose a Notch appearance template (.json).')
    settings = value.get('settings')
    if not isinstance(settings, dict):
        raise ValueError('This template has no appearance settings.')
    cleaned = {}
    for key, (low, high) in LIMITS.items():
        if key in settings:
            number = settings[key]
            if type(number) is not int or not low <= number <= high:
                raise ValueError('Template size is outside the supported range: ' + key)
            cleaned[key] = number
    if 'desktop_theme' in settings:
        if settings['desktop_theme'] not in THEMES:
            raise ValueError('Unknown desktop style.')
        cleaned['desktop_theme'] = settings['desktop_theme']
    if not cleaned:
        raise ValueError('The template contains no supported appearance settings.')
    return cleaned


def read_template(path):
    if Path(path).stat().st_size > 32_768:
        raise ValueError('Appearance templates must be smaller than 32 KB.')
    return validate_template(json.loads(Path(path).read_text('utf-8')))


def write_template(path, settings):
    allowed = {key: settings[key] for key in (*LIMITS, 'desktop_theme') if key in settings}
    payload = {'format': 'nook-appearance-v1', 'settings': allowed}
    validate_template(payload)
    Path(path).write_text(json.dumps(payload, indent=2), 'utf-8')
