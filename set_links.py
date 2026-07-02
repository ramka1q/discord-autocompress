#!/usr/bin/env python3
"""Author tool: write support/donate links into monetize.py and .github/FUNDING.yml.
Called by 'Set support links.bat'. ASCII only. Usage: set_links.py "<support>" "<pro>"."""
import os
import re
import sys

sup = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
pro = (sys.argv[2] if len(sys.argv) > 2 else "").strip()
here = os.path.dirname(os.path.abspath(__file__))


def set_const(text, name, val):
    val = val.replace('"', "").replace("\\", "/")
    return re.sub(r'(?m)^%s\s*=.*$' % name, '%s = "%s"' % (name, val), text, count=1)


# 1) monetize.py constants
mp = os.path.join(here, "monetize.py")
with open(mp, "r", encoding="utf-8") as f:
    src = f.read()
src = set_const(src, "SUPPORT_URL", sup)
src = set_const(src, "PRO_URL", pro)
with open(mp, "w", encoding="utf-8", newline="\n") as f:
    f.write(src)

# 2) .github/FUNDING.yml -> GitHub "Sponsor" button
fund = os.path.join(here, ".github", "FUNDING.yml")
os.makedirs(os.path.dirname(fund), exist_ok=True)
out, customs = [], []
u = sup.lower()
if "ko-fi.com" in u:
    out.append("ko_fi: " + sup.rstrip("/").split("/")[-1])
elif "buymeacoffee.com" in u or "buymea.coffee" in u:
    out.append("buy_me_a_coffee: " + sup.rstrip("/").split("/")[-1])
elif "patreon.com" in u:
    out.append("patreon: " + sup.rstrip("/").split("/")[-1])
elif "github.com/sponsors/" in u:
    out.append("github: [%s]" % sup.rstrip("/").split("/")[-1])
elif sup:
    customs.append(sup)
if pro:
    customs.append(pro)
if customs:
    out.append("custom: [%s]" % ", ".join('"%s"' % c for c in customs))
if not out:
    out.append("# no links set")
with open(fund, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(out) + "\n")

print("Support URL:", sup or "(empty)")
print("Pro URL:    ", pro or "(empty)")
print("OK")
