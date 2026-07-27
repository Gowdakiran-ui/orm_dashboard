import os
import re

def search_files(directory, extensions, patterns):
    matches = {p_name: [] for p_name in patterns.keys()}
    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    for p_name, pattern in patterns.items():
                        for match in re.finditer(pattern, content):
                            matches[p_name].append({
                                'file': filepath,
                                'line': content.count('\n', 0, match.start()) + 1,
                                'match': match.group(0)
                            })
    return matches

frontend_dir = r"c:\codebase\viewer\orm_dashboard\src"
patterns = {
    'invalid_svg': r'stroke="#[A-Fa-f0-9]{6}/\d{2}"',
    'window_open': r'window\.open\([^)]+\)'
}

print("--- Frontend Search ---")
results = search_files(frontend_dir, ['.tsx', '.ts'], patterns)
for p_name, matches in results.items():
    print(f"\nPattern: {p_name} ({len(matches)} matches)")
    for m in matches:
        print(f"  {m['file']}:{m['line']} -> {m['match']}")

print("\n--- Backend sources.py ---")
with open(r"c:\codebase\viewer\orm_collection\app\api\endpoints\sources.py", 'r', encoding='utf-8') as f:
    print(f.read())
