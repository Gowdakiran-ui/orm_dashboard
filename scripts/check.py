import pathlib
with open(pathlib.Path(__file__).parent / 'start_platform.ps1', 'rb') as f:
    text = f.read().decode('utf-8')

for i, line in enumerate(text.splitlines()):
    c = line.count('"')
    if c % 2 != 0:
        print(f"Line {i+1} has odd quotes: {c} -> {line}")

print("Total quotes:", text.count('"'))
