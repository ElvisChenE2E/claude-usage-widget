# -*- coding: utf-8 -*-
"""Standalone notification tester — run this to see the toasts.

    python test_notify.py

Shows 3 fake alerts stacked at the bottom-right. These are self-drawn
(Tkinter) so they DON'T depend on Windows notification settings or Focus
Assist — if these don't appear, nothing is blocking us.
"""
import tkinter as tk
import claude_usage as m

root = tk.Tk()
root.withdraw()

tests = [
    ("Claude usage 82%", "Session (5hr) reached 80% · resets in 2h 14m"),
    ("Claude usage 96%", "Weekly (7 day) reached 95% · resets in 1d 6h"),
    ("Claude session reset", "Your 5-hour session limit just reset."),
]

for title, msg in tests:
    m.Toast(root, title, msg, timeout=8000)

# quit once all toasts have closed
def check():
    if not m.Toast._active:
        root.destroy()
    else:
        root.after(500, check)

root.after(500, check)
root.mainloop()
print("done")
