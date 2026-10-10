"""Resource and user-data locations for source and frozen desktop editions."""
import os
import sys
from pathlib import Path

VERSION = '0.2.1'
RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def data_directory():
    override = os.environ.get('FILE_ORGANIZER_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, 'frozen', False) or os.environ.get('FILE_ORGANIZER_DESKTOP') == '1':
        return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ShiXu'
    return RESOURCE_ROOT / 'backend' / 'data'
