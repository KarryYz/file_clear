"""Native Windows folder dialog for the local browser edition."""
import threading
from pathlib import Path

_picker_lock = threading.Lock()


def choose_directory(initial='', title='选择文件夹'):
    if not _picker_lock.acquire(blocking=False):
        raise ValueError('目录选择窗口已经打开。')
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        options = {'title': title, 'parent': root, 'mustexist': True}
        if initial and Path(initial).is_absolute() and Path(initial).is_dir():
            options['initialdir'] = initial
        return filedialog.askdirectory(**options) or None
    except ImportError as exc:
        raise ValueError('当前 Python 缺少 Tk 目录选择组件，请手动输入路径或使用桌面版。') from exc
    finally:
        if root is not None:
            root.destroy()
        _picker_lock.release()
