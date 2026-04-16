import json
import re

input_file = r'favourites_12_04_2026.html'
TARGET_FOLDER = 'Speed Dial'

with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

folder_pattern = rf'<DT><H3[^>]*>{re.escape(TARGET_FOLDER)}</H3>\s*<DL><p>(.*?)</DL><p>'
folder_match = re.search(folder_pattern, content, re.DOTALL)

if not folder_match:
    print(f'Folder "{TARGET_FOLDER}" not found')
    exit(1)

folder_content = folder_match.group(1)

link_pattern = r'<DT><A HREF="([^"]+)"[^>]*>([^<]+)</A>'
matches = re.findall(link_pattern, folder_content)

shortcuts = []
for i, (url, name) in enumerate(matches, 1):
    shortcuts.append({
        'id': str(i),
        'name': name,
        'url': url
    })

defaults = {
    'shortcuts': shortcuts,
    'todos': []
}

with open('src/defaults.json', 'w', encoding='utf-8') as f:
    json.dump(defaults, f, indent=2, ensure_ascii=False)

print(f'Updated {len(shortcuts)} shortcuts to defaults.json')
