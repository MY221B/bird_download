#!/usr/bin/env python3
import sys, re, urllib.request

def main():
    if len(sys.argv) < 2:
        print("", end=""); return
    aid = sys.argv[1].strip()
    url = f"https://macaulaylibrary.org/asset/{aid}"
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode('utf-8','ignore')
    m = re.search(r'ebird\.org/species/([a-z0-9]+)', html)
    if m:
        print(m.group(1)); return
    m = re.search(r'"taxonCode"\s*:\s*"([a-z0-9]+)"', html)
    print(m.group(1) if m else "", end="")

if __name__ == '__main__':
    main()


