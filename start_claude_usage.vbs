' Launch Claude Usage widget silently (no console window)
Set sh = CreateObject("WScript.Shell")
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
' pythonw.exe avoids opening a console window
sh.Run "pythonw.exe """ & scriptDir & "claude_usage.py""", 0, False
