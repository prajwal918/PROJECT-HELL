with open('ml/signal_logger.py', 'r', encoding='utf-8') as f:
    source = f.read()
lines = source.split('\n')

# Check if there's a mix of tabs and spaces
for i in range(83, 142):
    line = lines[i]
    if '\t' in line:
        print(f"TAB at line {i+1}: {repr(line[:30])}")

# Check indentation units
print("\nIndentation analysis:")
for i in range(83, 142):
    line = lines[i]
    spaces = len(line) - len(line.lstrip())
    print(f"{i+1}: spaces={spaces} content={line.strip()[:50]}")
