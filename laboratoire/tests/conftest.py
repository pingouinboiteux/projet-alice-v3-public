"""Shared test-only Tcl interpreter for isolated desktop-loop windows."""
import tkinter as tk
import pytest


@pytest.fixture(scope='session')
def validation_desktop_root():
    # Production uses one interpreter too; each test owns a fresh Toplevel.
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()
