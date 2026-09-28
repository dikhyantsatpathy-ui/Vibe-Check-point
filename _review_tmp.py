import re, collections
lines = open('app/main.py', encoding='utf-8').read().splitlines()
print("TOTAL LINES:", len(lines))

# duplicate function defs
names = collections.Counter()
locs = collections.defaultdict(list)
for i, l in enumerate(lines, 1):
    m = re.match(r'\s*(?:async )?def (\w+)', l)
    if m:
        names[m.group(1)] += 1
        locs[m.group(1)].append(i)
print("\nDUPLICATE FUNCTION DEFS:")
for n, c in names.items():
    if c > 1:
        print(" ", n, locs[n])

# duplicate routes
routes = collections.defaultdict(list)
pending = []
for i, l in enumerate(lines, 1):
    m = re.match(r'@app\.(get|post|put|delete|patch)\("([^"]+)"\)', l)
    if m:
        pending.append((i, m.group(2)))
    elif re.match(r'\s*(?:async )?def ', l) and pending:
        for ln, p in pending:
            routes[p].append((ln, i))
        pending = []
print("\nDUPLICATE ROUTES (same path+method):")
seen = collections.defaultdict(list)
for i, l in enumerate(lines, 1):
    m = re.match(r'@app\.(get|post|put|delete|patch)\("([^"]+)"\)', l)
    if m:
        seen[(m.group(1), m.group(2))].append(i)
for k, v in seen.items():
    if len(v) > 1:
        print(" ", k, v)
print("\nknown markers:")
for i, l in enumerate(lines, 1):
    if re.search(r'neon\.tech|demo_login|_DEFAULT_NEON_URL|VERISOURCE|FALLBACK', l, re.I):
        print(" ", i, l.strip()[:120])
