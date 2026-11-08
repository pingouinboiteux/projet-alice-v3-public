"""Real Tk layout regression, no Alice services or keyboard/mouse input."""
import ctypes
from types import SimpleNamespace
import tkinter as tk

from interface.laboratoire.desktop_style import append


def test_initial_layout_follows_messages_but_preserves_manual_scroll():
    window = tk.Tk()
    window.withdraw()
    window.attributes('-alpha', 0.0)
    window.geometry('400x180+0+0')
    history = tk.Text(window, wrap='word', height=5)
    history.pack(fill='both', expand=True)
    app = SimpleNamespace(history=history)
    try:
        append(app, 'Alice', 'validation_accueil ' * 150)
        window.update_idletasks()
        api = ctypes.WinDLL('user32')
        api.GetParent.argtypes = [ctypes.c_void_p]
        api.GetParent.restype = ctypes.c_void_p
        api.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        api.ShowWindow(api.GetParent(window.winfo_id()), 4)
        window.update()
        # A burst of queued text events must follow the latest response.
        for index in range(4):
            append(app, 'Alice', ('validation_reponse_%d ' % index) * 60)
        window.update()
        assert history.yview()[1] >= .98
        history.yview_moveto(0)
        window.update()
        append(app, 'Alice', 'validation_lecture_ancienne')
        window.update()
        assert history.yview()[0] == 0
    finally:
        window.destroy()
