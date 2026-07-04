import ast
with open('ml/signal_logger.py', 'r', encoding='utf-8') as f:
    source = f.read()
# Simplify the function dramatically to find the issue
start = source.index("def log_signal(")
end = source.index("\ndef update_mid_price(")
lines = source[start:end].split('\n')

# Remove lines between try and except, replace with simple pass
new_lines = []
skip_until_except = False
found_try = False
for line in lines:
    stripped = line.strip()
    if stripped == 'try:':
        found_try = True
        new_lines.append(line)
        new_lines.append('    pass')
        skip_until_except = True
        continue
    if skip_until_except:
        if stripped.startswith('except'):
            skip_until_except = False
            new_lines.append(line)
        continue
    new_lines.append(line)

if found_try:
    test = '\n'.join(new_lines)
    try:
        ast.parse(test)
        print("Simplified OK - issue is in the try block body")
    except SyntaxError as e:
        print(f"Simplified ERROR at line {e.lineno}: {e.msg}")
        print(f"Context: {new_lines[max(0,e.lineno-3):e.lineno+3]}")
else:
    print("No try block found")
