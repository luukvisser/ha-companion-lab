#!/usr/bin/env python3
"""A generic check for data that must not be published: secrets and household details.

Usage: tools/check-house-data.py [root]   (exit 1 on findings)

Flags private-network addresses other than the lab's own (the emulator's 10.0.2.2, the Docker
bridge 172.17.0.1, the isolated stack's 172.31.240.0/24, documentation ranges), private keys,
tokens (JWT-shaped strings, Home Assistant long-lived tokens, GitHub tokens), long hex strings that
are not labelled checksums, e-mail addresses, home-directory paths and real Companion-app device
model names. Add your own household's names, host names and IDs to a local, untracked list
(HOUSE_DATA_EXTRA, one regular expression per line) instead of to this file.
"""
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
SKIP_FILES = {"NOTES-for-Luuk.md", "lab.env"}
ALLOWED_IPS = re.compile(r"^(10\.0\.2\.\d+|172\.17\.0\.1|172\.31\.240\.\d+|127\.\d+\.\d+\.\d+|0\.0\.0\.0|10\.0\.0\.5)$")
PRIVATE_IP = re.compile(r"\b(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)\b")
CHECKS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "JWT/HA token": re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "e-mail": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}\b"),
    "home path": re.compile(r"/home/[a-z][a-z0-9_-]*/|/Users/[A-Za-z][A-Za-z0-9_-]*/"),
}
LONG_HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{32,}(?![0-9a-fA-F])")
CHECKSUM_CONTEXT = re.compile(r"sha(1|256)|digest|@sha|checksum|SHA|uses:", re.I)
EMAIL_OK = re.compile(r"noreply@anthropic\.com|users\.noreply\.github\.com|@example\.(com|org)|\.invalid$|\.example$")

extra = []
if os.environ.get("HOUSE_DATA_EXTRA") and os.path.exists(os.environ["HOUSE_DATA_EXTRA"]):
    extra = [re.compile(l.strip(), re.I) for l in open(os.environ["HOUSE_DATA_EXTRA"]) if l.strip()]

findings = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for name in filenames:
        if name in SKIP_FILES:
            continue
        path = os.path.join(dirpath, name)
        rel = os.path.relpath(path, ROOT)
        try:
            text = open(path, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            data = open(path, "rb").read()
            for rx in extra:
                if rx.search(data.decode("latin-1")):
                    findings.append(f"{rel}: household pattern in binary")
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for ip in PRIVATE_IP.findall(line):
                if not ALLOWED_IPS.match(ip[0]):
                    findings.append(f"{rel}:{n}: private address {ip[0]}")
            for label, rx in CHECKS.items():
                m = rx.search(line)
                if m and not (label == "e-mail" and EMAIL_OK.search(m.group(0))):
                    findings.append(f"{rel}:{n}: {label}")
            if LONG_HEX.search(line) and not CHECKSUM_CONTEXT.search(line):
                findings.append(f"{rel}:{n}: long hex string without a checksum label")
            for rx in extra:
                if rx.search(line):
                    findings.append(f"{rel}:{n}: household pattern")

for f in findings:
    print(f)
print(f"house-data check: {len(findings)} finding(s)")
sys.exit(1 if findings else 0)
