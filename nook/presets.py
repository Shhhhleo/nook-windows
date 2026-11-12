"""Portable, data-only appearance templates. Never execute imported content."""
import json
from pathlib import Path

PRESETS = {
    'Everyday': dict(width=760, music_height=174, compact_width=420, compact_height=58,
                     height=390, radius=24, opacity=100, desktop_theme='Glass'),
    'Focus': dict(width=700, music_height=168, compact_width=360, compact_height=52,
                  height=360, radius=22, opacity=100, desktop_theme='Paper'),
    'Studio': dict(width=840, music_height=184, compact_width=440, compact_height=62,
                   height=430, radius=28, opacity=100, desktop_theme='Midnight'),
}
DESCRIPTIONS = {
    'Everyday': 'A balanced music player and readable resting strip.',
    'Focus': 'Small and quiet, with space left for your work.',
    'Studio': 'More room for track names and desktop essentials.',
}
LIMITS = {'width': (460, 1100), 'music_height': (160, 240), 'compact_width': (320, 600),
          'compact_height': (48, 90), 'height': (300, 850), 'radius': (8, 48), 'opacity': (65, 100)}
THEMES = ('Glass', 'Paper', 'Midnight')


def validate_template(value):
    if not isinstance(value, dict) or value.get('format') != 'nook-appearance-v1':
        raise ValueError('Choose a Nook appearance template (.json).')
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
