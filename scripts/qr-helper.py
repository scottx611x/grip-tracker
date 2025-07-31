out = []
with open("qr.txt") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        row = "".join("1" if ch == "#" else "0" for ch in line)
        out.append(row)

print("qrcode = [")
for r in out:
    print(f'    "{r}",')
print("]")