"""Packs skin/AIUsageBar into dist/AIUsageBar_<version>.rmskin.

An .rmskin is a zip containing RMSKIN.ini + Skins/<name>/..., followed by a
16-byte footer (zip size, flags, "RMSKIN\\0") that Rainmeter's installer checks.
Leaves out runtime data (data/, logs) so nobody's usage numbers get shipped.
"""
import io
import os
import struct
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin", "AIUsageBar")
SEP = sys.argv[2] if len(sys.argv) > 2 else "/"   # path separator inside the zip


def main(version):
    exe = os.path.join(SKIN, "@Resources", "bin", "aiusage", "aiusage.exe")
    if not os.path.exists(exe):
        sys.exit("build the exe first (build.ps1)")
    ini = (f"[rmskin]\r\nName=AI Usage Bar\r\nAuthor=Alorist\r\nVersion={version}\r\n"
           "MinimumRainmeter=4.5.0\r\nMinimumWindows=10.0\r\nLoadType=Skin\r\nLoad=AIUsageBar\\Taskbar.ini\r\n")
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("RMSKIN.ini", ini)
        for dirpath, dirs, files in os.walk(SKIN):
            rel_dir = os.path.relpath(dirpath, SKIN)
            dirs[:] = [d for d in dirs if not (rel_dir == "@Resources" and d == "data")]
            for f in files:
                if f.endswith((".log", ".tmp", ".old")):
                    continue
                rel = os.path.normpath(os.path.join(rel_dir, f)).split(os.sep)
                z.write(os.path.join(dirpath, f), SEP.join(["Skins", "AIUsageBar", *rel]))
                count += 1
    data = buf.getvalue()
    footer = struct.pack("<qB", len(data), 0) + b"RMSKIN\x00"
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", f"AIUsageBar_{version}.rmskin")
    with open(out, "wb") as f:
        f.write(data + footer)
    print(f"wrote {out} ({count} files, {len(data) // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "1.0.0")
