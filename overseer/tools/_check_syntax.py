with open('ml/signal_logger.py', 'r', encoding='utf-8') as f:
    source = f.read()
lines = source.split('\n')
for i in range(116, 142):
    raw = lines[i].encode('utf-8')
    print(f'{i+1}: {raw!r}')
