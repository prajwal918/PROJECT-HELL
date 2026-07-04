"""Find all L3 tick fields used by Z gates."""
import re
import glob

fields = set()
for f in glob.glob("engine_logic/gates/gate_Z*.py"):
    with open(f) as fh:
        for line in fh:
            m = re.search(r'tick\.get\(["\']([^"\']+)["\']', line)
            if m:
                fields.add(m.group(1))

for f in sorted(fields):
    print(f)
