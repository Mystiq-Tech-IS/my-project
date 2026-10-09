"""Диагностика: что записано в реестре про Мир танков / танки."""
import winreg

bases = [
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]

FOUND = []

for hive, base in bases:
    try:
        with winreg.OpenKey(hive, base) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    i += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(k, sub) as sk:
                        def g(n, d=""):
                            try:
                                v, _ = winreg.QueryValueEx(sk, n)
                                return v
                            except Exception:
                                return d

                        name = g("DisplayName", "")
                        ln = name.lower()
                        if ("tank" in ln or "танк" in ln
                                or "warface" in ln or "lesta" in ln
                                or "wargaming" in ln or "мир" in ln):
                            FOUND.append((name, {
                                "DisplayName":     name,
                                "Publisher":       g("Publisher", "<empty>"),
                                "EstimatedSize":   g("EstimatedSize", "<none>"),
                                "InstallLocation": g("InstallLocation", "<empty>"),
                                "DisplayIcon":     g("DisplayIcon", "<empty>"),
                                "SystemComponent": g("SystemComponent", "<none>"),
                                "NoDisplay":       g("NoDisplay", "<none>"),
                                "ParentKeyName":   g("ParentKeyName", "<none>"),
                                "ReleaseType":     g("ReleaseType", "<none>"),
                                "Registry key":    sub,
                            }))
                except Exception:
                    pass
    except Exception:
        pass

for name, info in FOUND:
    print(f"=== {name} ===")
    for k, v in info.items():
        if k == "DisplayName":
            continue
        print(f"  {k:18} {v}")
    print()