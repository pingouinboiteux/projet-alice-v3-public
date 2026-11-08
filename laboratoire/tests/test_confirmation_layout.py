import sys
from pathlib import Path
import threading
import tkinter as tk
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from alice_desktop import confirm_details


@pytest.mark.parametrize('description',['Note courte','Texte long\n'*200])
def test_confirmation_buttons_visible_inside_dialog(description):
    root=tk.Tk();root.geometry('1x1+10000+10000');root.update();measurements=[]
    def inspect():
        dialog=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
        dialog.update_idletasks()
        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child,tk.Button):
                    bottom=child.winfo_rooty()+child.winfo_height()-dialog.winfo_rooty()
                    measurements.append((child.winfo_ismapped(),bottom<=dialog.winfo_height()))
                visit(child)
        visit(dialog)
        # Send through the window manager callback even when the test is unfocused.
        root.tk.call(dialog.protocol('WM_DELETE_WINDOW'))
    root.after(100,inspect)
    try:
        assert confirm_details(root,description,threading.Event()) is False
        assert measurements==[(1,True),(1,True)]
    finally:root.destroy()
