#!/usr/bin/env python3
"""
One-time migration:
  1. Repair corrupt bytes in notes.json (premature } + 0x82 0x89 garbage)
  2. Update keys from video-path format to node.rel format
"""
import json, os, re

# ── Step 1: repair raw bytes ──────────────────────────────────────────────────
def repair_raw(data: bytes) -> bytes:
    """Remove every occurrence of the corruption pattern  \\n"↵}0x820x89↵  """
    # Pattern: escaped-newline + closing-quote + real-newline + } + 0x82 0x89 + escaped-newline
    # The corruption splits a note value across a spurious closing brace.
    # Fix: the premature closing brace + garbage bytes are removed and the two
    # halves of the string are rejoined with a blank line between them.
    CORRUPTION = bytes([0x5c, 0x6e, 0x22, 0x0a, 0x7d, 0x82, 0x89, 0x5c, 0x6e])
    REPAIR     = bytes([0x5c, 0x6e, 0x5c, 0x6e])   # just \\n\\n (blank line)
    while CORRUPTION in data:
        data = data.replace(CORRUPTION, REPAIR, 1)
        print('  repaired one corruption instance')
    return data

# ── Step 2: key migration ─────────────────────────────────────────────────────
# Chapter-number → group
def chapter_to_group(chapter_name):
    m = re.match(r'Chapter_(\d+)(?:\.(\d+))?', chapter_name)
    if not m:
        return None
    major = int(m.group(1))
    frac  = m.group(2)          # e.g. '5' for Chapter_06.5
    if major in (1, 2, 3):
        return 'cm1_Intro'
    if major in (4, 5, 6) and frac is None:
        return 'cm2_Basic'
    # Chapter_06_Bonus_… also maps to cm2_Basic (no frac, major=6)
    # Chapter_06.5 → frac='5', major=6  → cm3_Intermediate
    if major == 6 and frac:
        return 'cm3_Intermediate'
    if major in (7, 8, 9):
        return 'cm3_Intermediate'
    return None

VIDEO_EXT = re.compile(r'\.(mp4|mov|webm|m4v|mkv)$', re.IGNORECASE)

notes_path = os.path.join(os.path.dirname(__file__), 'data', 'notes.json')

# Read raw and repair
raw = open(notes_path, 'rb').read()
print(f'Read {len(raw)} bytes')
repaired = repair_raw(raw)

# Parse JSON
notes = json.loads(repaired.decode('utf-8'))

new_notes = {}
migrated = 0
kept = 0
skipped = 0

for key, value in notes.items():
    if not key.startswith('note:'):
        new_notes[key] = value
        kept += 1
        continue

    path = key[5:]  # strip 'note:'

    # Already new format (Canto_Mando_Videos/...) — just strip filename if present
    if path.startswith('Canto_Mando_Videos/'):
        if VIDEO_EXT.search(path):
            new_path = '/'.join(path.split('/')[:-1])
            print(f'  strip-filename: {key[:70]}...')
            new_notes['note:' + new_path] = value
            migrated += 1
        else:
            new_notes[key] = value
            kept += 1
        continue

    # Old format: Chapter_XX_Name/.../video.mp4
    parts = path.split('/')
    chapter_name = parts[0]
    group = chapter_to_group(chapter_name)
    if group is None:
        print(f'  SKIP (unknown chapter): {key}')
        new_notes[key] = value
        skipped += 1
        continue

    # Strip video filename if last part has an extension
    folder_parts = parts[:-1] if VIDEO_EXT.search(parts[-1]) else parts
    new_path = 'Canto_Mando_Videos/' + group + '/' + '/'.join(folder_parts)
    print(f'  migrate: {key[:60]}')
    print(f'       --> note:{new_path}')
    new_notes['note:' + new_path] = value
    migrated += 1

with open(notes_path, 'w', encoding='utf-8') as f:
    json.dump(new_notes, f, indent=2, ensure_ascii=False)

print(f'\nDone. migrated={migrated}  kept={kept}  skipped={skipped}')
print(f'Total keys: {len(notes)} → {len(new_notes)}')
