#!/usr/bin/env python3
"""Author tool: write ONE donate link into monetize.py and .github/FUNDING.yml.
Called by 'Set donate link.bat'. ASCII only. Usage: set_links.py "<donate_url>"."""
import os
import re
import sys

url = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
here = os.path.dirname(os.path.abspath(__file__))

# 1) monetize.py -> DONATE_URL
mp = os.path.join(here, "monetize.py")
with open(mp, "r", encoding="utf-8") as f:
    src = f.read()
safe = url.replace('"', "").replace("\\", "/")
src = re.sub(r'(?m)^DONATE_URL\s*=.*$', 'DONATE_URL = "%s"' % safe, src, count=1)
with open(mp, "w", encoding="utf-8", newline="\n") as f:
    f.write(src)

# 2) .github/FUNDING.yml -> GitHub "Sponsor" button
fund = os.path.join(here, ".github", "FUNDING.yml")
os.makedirs(os.path.dirname(fund), exist_ok=True)
u = url.lower()
if "ko-fi.com" in u:
    line = "ko_fi: " + url.rstrip("/").split("/")[-1]
elif "buymeacoffee.com" in u or "buymea.coffee" in u:
    line = "buy_me_a_coffee: " + url.rstrip("/").split("/")[-1]
elif "patreon.com" in u:
    line = "patreon: " + url.rstrip("/").split("/")[-1]
elif "github.com/sponsors/" in u:
    line = "github: [%s]" % url.rstrip("/").split("/")[-1]
elif url:
    line = 'custom: ["%s"]' % url
else:
    line = "# no link set"
with open(fund, "w", encoding="utf-8", newline="\n") as f:
    f.write(line + "\n")

print("Donate URL:", url or "(empty)")
print("OK")
