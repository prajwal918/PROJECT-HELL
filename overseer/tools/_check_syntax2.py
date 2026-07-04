import ast
with open('ml/signal_logger.py', 'r', encoding='utf-8') as f:
    source = f.read()
# Replace the entire function to test
try:
    ast.parse(source)
    print("FULL FILE: OK")
except SyntaxError as e:
    print(f"FULL FILE ERROR at line {e.lineno}: {e.msg}")

# Try parsing just the function
try:
    start = source.index("def log_signal(")
    end = source.index("\ndef update_mid_price(")
    func_source = source[start:end]
    ast.parse(func_source)
    print("FUNCTION ONLY: OK")
except SyntaxError as e:
    print(f"FUNCTION ERROR at line {e.lineno}: {e.msg}")

# Try removing the triple-quote SQL and see if that fixes it
try:
    test_source = source.replace("""cursor = conn.execute(
        \"\"\"
        INSERT INTO signal_log""", """cursor = conn.execute("INSERT INTO signal_log""")
    ast.parse(test_source)
    print("AFTER SQL REPLACE: OK")
except SyntaxError as e:
    print(f"AFTER SQL REPLACE ERROR at line {e.lineno}: {e.msg}")
