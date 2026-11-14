"""Bounded local file tools. Writes require a reviewed proposal; no shell execution."""
import csv
import io
from pathlib import Path

TEXT_TYPES = {'.txt', '.md', '.csv', '.json', '.log', '.rst'}


def resolve(root, path, *, exists=True):
    base = Path(root).resolve()
    target = (base / path.strip().strip('"')).resolve()
    if not target.is_relative_to(base):
        raise ValueError('Choose a file inside your selected cowork folder.')
    if exists and not target.exists():
        raise ValueError('That path does not exist in your cowork folder.')
    return target


def listing(root, path='.'):
    folder = resolve(root, path)
    if not folder.is_dir():
        raise ValueError('Choose a folder to list.')
    rows = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:100]
    rows = [p for p in rows if p.resolve().is_relative_to(Path(root).resolve())]
    return {'text': str(folder) + '\n' + '\n'.join(('Folder: ' if p.is_dir() else '') + p.name for p in rows),
            'files': [str(p) for p in rows if p.is_file()][:20]}


def read(root, path):
    target = resolve(root, path)
    if target.suffix.lower() not in TEXT_TYPES or not target.is_file():
        raise ValueError('I can read TXT, Markdown, CSV, JSON and log files. Choose one inside your cowork folder.')
    if target.stat().st_size > 256_000:
        raise ValueError('That file is too large for a quick read (250 KB limit).')
    text = target.read_text('utf-8-sig', errors='replace')
    if '\x00' in text:
        raise ValueError('This appears to be a binary file.')
    return {'text': text[:16000] + ('\n[Preview truncated]' if len(text) > 16000 else ''), 'files': [str(target)]}


def inventory(root, folder='.'):
    target = resolve(root, folder)
    if not target.is_dir():
        raise ValueError('Choose a folder.')
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Type', 'Bytes'])
    for p in sorted(target.iterdir(), key=lambda p: p.name.lower())[:500]:
        if p.resolve().is_relative_to(Path(root).resolve()):
            # Prefix spreadsheet formulas so opening the CSV cannot execute them.
            name = "'" + p.name if p.name.startswith(('=', '+', '-', '@')) else p.name
            writer.writerow([name, 'folder' if p.is_dir() else p.suffix, p.stat().st_size if p.is_file() else ''])
    return proposal(root, 'file-inventory.csv', output.getvalue())


def proposal(root, path, content):
    target = resolve(root, path, exists=False)
    if target.suffix.lower() not in {'.txt', '.md', '.csv'}:
        raise ValueError('New documents must be TXT, Markdown or CSV.')
    if target.exists():
        raise ValueError('That file already exists. Choose a new filename; existing files are never overwritten.')
    if not target.parent.is_dir() or len(content) > 64000:
        raise ValueError('Choose an existing folder and a document smaller than 64,000 characters.')
    return {'text': 'Ready to create ' + str(target) + '\n\n' + content,
            'proposal': {'path': str(target), 'content': content, 'root': str(Path(root).resolve())}}


def apply(proposed, root):
    if proposed['root'] != str(Path(root).resolve()):
        raise ValueError('Your cowork folder changed. Please prepare the document again.')
    target = resolve(root, proposed['path'], exists=False)
    # Exclusive create closes the race between preview and approval.
    with target.open('x', encoding='utf-8') as output:
        output.write(proposed['content'])
    return {'text': 'Created ' + str(target), 'files': [str(target)]}
