"""Windows entry point. Bundles Vue, starts a loopback API, and opens WebView2."""
import ctypes
import logging
import multiprocessing
import os
import socket
import threading
import time
import traceback
from pathlib import Path


def run_desktop(data_dir):
    from backend.runtime import VERSION
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data_dir / 'desktop.log', encoding='utf-8',
                        level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    # Prebind the loopback socket: avoid the race in choosing an unused port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    os.environ['FILE_ORGANIZER_ORIGIN'] = origin
    # This private marker is for local packaging smoke tests, never bundled.
    marker = os.environ.get('FILE_ORGANIZER_SMOKE_MARKER')
    if marker:
        Path(marker).write_text(origin, encoding='utf-8')
    import uvicorn
    import webview
    from backend.main import app, organizer
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                          log_config=None, access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]),
                              name='organizer-api', daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError('本机服务启动失败，请查看 desktop.log。')
        time.sleep(.05)
    window = None
    close_started = False
    allow_close = False

    class DesktopApi:
        def choose_directory(self, initial='', title='选择文件夹'):
            directory = initial if initial and Path(initial).is_dir() else ''
            result = window.create_file_dialog(webview.FileDialog.FOLDER, directory=directory)
            return result[0] if result else None

    def closing():
        nonlocal close_started, allow_close
        if allow_close:
            return True
        active = organizer.active()
        if not active:
            return True
        if not close_started:
            close_started = True
            def finish_and_close():
                nonlocal allow_close
                try:
                    organizer.stop(active['id'])
                except ValueError:
                    pass
                organizer.wait()
                allow_close = True
                window.destroy()
            threading.Thread(target=finish_and_close, name='safe-close', daemon=True).start()
        return False

    window = webview.create_window(f'拾序 · 文件整理助手 {VERSION}', origin,
                                  js_api=DesktopApi(), width=1250, height=850,
                                  min_size=(800, 600), text_select=True)
    window.events.closing += closing
    try:
        webview.start(gui='edgechromium', private_mode=True)
    finally:
        active = organizer.active()
        if active:
            try:
                organizer.stop(active['id'])
            except ValueError:
                pass
        organizer.wait()
        server.should_exit = True
        thread.join(5)
        sock.close()


def main():
    os.environ['FILE_ORGANIZER_DESKTOP'] = '1'
    from backend.runtime import data_directory
    from backend.desktop_lock import DesktopLock
    data_dir = data_directory()
    # Lock before importing backend.main: importing it performs DB recovery.
    with DesktopLock(data_dir) as lock:
        if not lock.handle:
            ctypes.windll.user32.MessageBoxW(None, '拾序已经在运行。请使用现有窗口，或关闭它后再启动。', '拾序', 0x40)
            return
        run_desktop(data_dir)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        logging.exception('Desktop startup failed')
        message = '拾序启动失败。请确认已安装 Microsoft Edge WebView2 Runtime。\n详细原因见用户数据目录 ShiXu 下的 desktop.log。'
        if os.environ.get('FILE_ORGANIZER_SMOKE_MARKER'):
            Path(os.environ['FILE_ORGANIZER_SMOKE_MARKER'] + '.error').write_text(traceback.format_exc(), encoding='utf-8')
        ctypes.windll.user32.MessageBoxW(None, message, '拾序', 0x10)
