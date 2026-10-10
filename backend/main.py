import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.organizer import Organizer
from backend.directory_picker import choose_directory
from backend.runtime import RESOURCE_ROOT, VERSION, data_directory

ROOT = RESOURCE_ROOT
organizer = Organizer(data_directory() / 'tasks.sqlite3')
app = FastAPI(title='文件整理助手', version=VERSION)
ALLOWED_ORIGINS = {'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000'}
if os.environ.get('FILE_ORGANIZER_ORIGIN'):
    ALLOWED_ORIGINS.add(os.environ['FILE_ORGANIZER_ORIGIN'])
app.add_middleware(CORSMiddleware, allow_origins=list(ALLOWED_ORIGINS),
                   allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '').split(':')[0]
    origin = request.headers.get('origin')
    if host not in {'localhost', '127.0.0.1'} or (origin and origin not in ALLOWED_ORIGINS):
        return JSONResponse({'detail': '仅允许本机界面访问。'}, status_code=403)
    if request.method == 'POST' and not request.headers.get('content-type', '').startswith('application/json'):
        return JSONResponse({'detail': '需要 JSON 请求。'}, status_code=415)
    return await call_next(request)


class ScanRequest(BaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    mode: str = 'documents'
    recursive: bool = False


class ExecuteRequest(BaseModel):
    selected_ids: list[str]


class DraftRequest(BaseModel):
    selected_ids: list[str]
    category_filter: str = '全部'


class DirectoryRequest(BaseModel):
    initial: str = ''
    title: str = '选择文件夹'


def invoke(action, *args):
    try:
        return action(*args)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': VERSION}


@app.post('/api/scan')
def scan(body: ScanRequest):
    return invoke(organizer.scan, body.source, body.target, body.mode, body.recursive)


@app.post('/api/tasks/{task_id}/execute')
def execute(task_id: str, body: ExecuteRequest):
    return invoke(organizer.start_execute, task_id, body.selected_ids)


@app.post('/api/tasks/{task_id}/undo')
def undo(task_id: str):
    return invoke(organizer.start_undo, task_id)


@app.post('/api/directories/choose')
def pick_directory(body: DirectoryRequest):
    return {'path': invoke(choose_directory, body.initial, body.title)}


@app.get('/api/active')
def active():
    return organizer.active()


@app.get('/api/tasks/{task_id}/progress')
def progress(task_id: str):
    return invoke(organizer.progress, task_id)


@app.post('/api/tasks/{task_id}/stop')
def stop(task_id: str):
    return invoke(organizer.stop, task_id)


@app.post('/api/tasks/{task_id}/retry')
def retry(task_id: str):
    return invoke(organizer.start_retry, task_id)


@app.post('/api/tasks/{task_id}/resume')
def resume(task_id: str):
    return invoke(organizer.start_resume, task_id)


@app.get('/api/tasks')
def history():
    return organizer.history()


@app.get('/api/drafts')
def drafts():
    return organizer.drafts()


@app.get('/api/tasks/{task_id}')
def get_task(task_id: str):
    return invoke(organizer.get, task_id)


@app.post('/api/tasks/{task_id}/draft')
def save_draft(task_id: str, body: DraftRequest):
    return invoke(organizer.save_draft, task_id, body.selected_ids, body.category_filter)


if (ROOT / 'frontend' / 'dist').is_dir():
    app.mount('/', StaticFiles(directory=ROOT / 'frontend' / 'dist', html=True), name='frontend')
