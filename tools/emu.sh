#!/bin/bash
# emu.sh ui | tap "<text>" | shot <name> | back | home | switcher | off | on | app
#   ui     lists the screen's elements with text, description, id and bounds (uiautomator).
#   tap    taps the first element whose text or description contains <text>.
#   shot   saves a screenshot to $OUT_DIR/<name>.png.
#   back / home / app    the back key, the home key, (re)launch the Companion app (also: front).
#   switcher             the app switcher (recents).
#   off / on             screen off (power key) / screen on with the keyguard dismissed.
#   In fullscreen only `switcher` and `off` hide the page; `home` does not (lib.sh leave_app).
#
# CAUTION: uiautomator reports the text of password fields too. `ui` hides fields marked as
# password, but do not rely on that: never dump the UI while a password field holds a password;
# use `shot` there.
. "$(dirname "$0")/../lib.sh"
dump() { "$ADB" shell uiautomator dump /sdcard/ui.xml </dev/null >/dev/null && "$ADB" shell cat /sdcard/ui.xml </dev/null; }
case "$1" in
ui)
  dump | python3 -c '
import re, sys
for m in re.finditer(r"<node [^>]*>", sys.stdin.read()):
    n = m.group(0).replace(" ", " ")
    g = lambda k: (re.search(k + r"=\"([^\"]*)\"", n) or [None, ""])[1]
    if "password=\"true\"" in n:
        print(g(" class").split(".")[-1], "(password field: text hidden)", g("bounds")); continue
    t, d = g(" text"), g("content-desc")
    if t or d or "Edit" in g(" class"):
        print(g(" class").split(".")[-1], repr(t), repr(d), g("resource-id").split("/")[-1], g("bounds"), "click" if g("clickable") == "true" else "")'
  ;;
tap)
  xy=$(dump | python3 -c '
import re, sys
want = sys.argv[1]
for m in re.finditer(r"<node [^>]*>", sys.stdin.read()):
    n = m.group(0).replace(" ", " ")
    if re.search(r"(text|content-desc)=\"[^\"]*" + re.escape(want), n):
        a = list(map(int, re.findall(r"\d+", re.search(r"bounds=\"([^\"]*)\"", n).group(1))))
        print((a[0] + a[2]) // 2, (a[1] + a[3]) // 2)
        break' "$2")
  if [ -n "$xy" ]; then
    # shellcheck disable=SC2086
    "$ADB" shell input tap $xy </dev/null && echo "tapped $2 at $xy"
  else
    echo "not found: $2"
  fi
  ;;
shot) "$ADB" exec-out screencap -p > "$OUT_DIR/$2.png" && echo "$OUT_DIR/$2.png" ;;
back) "$ADB" shell input keyevent 4 </dev/null ;;
home) leave_app home ;;
switcher) leave_app switcher ;;
off) leave_app off ;;
on) return_app off ;;
app | front) launch_app ;;
*) sed -n '2,11p' "$0" ;;
esac
