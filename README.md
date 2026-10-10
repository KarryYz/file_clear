# 拾序 · 文件整理助手

本机运行的 Vue 3 + TypeScript + FastAPI 工具。选择目录 → 扫描预览 → 勾选文件 → 按类型归档 → 必要时撤销。

## Windows 桌面版（0.2.0）

运行 `ShiXu-0.2.0-windows-x64.exe` 即可打开桌面窗口，无需安装 Python 或 Node。支持 Windows 10/11 64 位，需要 Microsoft Edge WebView2 Runtime（通常随 Edge/Windows 11 提供）。首次启动会解压内置运行文件，可能需要几秒。

桌面版历史和草稿保存在 `%LOCALAPPDATA%\ShiXu\tasks.sqlite3`，日志保存在同目录的 `desktop.log`。关闭窗口时，如有任务正在运行，会请求安全停止，完成当前文件后退出。桌面版与源码开发版默认使用不同的数据目录；如需迁移历史，请关闭两边的程序、先备份数据库，再将开发版 `backend/data/tasks.sqlite3` 复制到桌面版数据目录。请勿覆盖已有记录而不备份。

本版本尚未做代码签名，建议发布前在一台独立的 Windows 电脑上再验证一次。

## 快速启动（Windows / PowerShell）

在解压后的项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm install
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 。请保持终端运行。只绑定本机地址，使用单个服务进程，不要加 `--workers`，不要发布到公网。

依赖已安装、界面已构建后，可在普通 PowerShell 中执行 `.\start.ps1` 启动。通常不需要管理员权限。若从受限的代理执行环境启动，服务可能只能写入项目目录，访问 D 盘会报 `WinError 5`；请在自己的普通终端启动，或为服务提供所需目录的执行环境权限。

## 开发模式

后端在根目录运行：

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

另一个终端：

```powershell
cd frontend
npm run dev
```

访问 http://127.0.0.1:5173 。Vite 将 `/api` 代理到本机后端。前端更新后，用 `npm run build` 更新正式界面。

## 已实现

- Word、PDF、Excel、PowerPoint 分类，支持常见旧版扩展名。
- 默认选择「全部文件」，覆盖当前层级的所有普通文件，子文件夹仅在勾选递归后扫描。
- 压缩包按格式收进 `Packages/ZIP`、`Packages/RAR`、`Packages/7Z`、`Packages/TAR` 等目录（不解压、不删除）。
- 图片 → `Images`、视频 → `Videos`、音频 → `Audio`、字体 → `Fonts`、文本 → `Text`。
- 未识别的扩展名、无扩展名文件及普通点文件 → `Other`；Office 临时锁文件及链接仍跳过并显示提示。
- EXE、MSI、MSIX、ISO 安装包候选，全部默认不勾选，需要用户判断。
- 一键全选所有候选文件（含 EXE，跨类别筛选），也可只选办公文件或取消全选。
- 自动生成英文目录，以 `Archive` 为默认根目录；保留原文件名和中文界面。
- 可选递归扫描；跳过归档目录、系统目录、常见软件目录、项目依赖目录和目录联接。
- 预览原路径 / 目标路径，按类别筛选和逐文件勾选。
- Windows 原生目录选择按钮，浏览器版使用 Tk，桌面版使用系统文件夹选择窗口；也支持手动输入路径。
- 同名自动加序号；执行期间新出现的冲突文件不会被覆盖。
- 跨磁盘复制，SHA-256 校验后移除源文件；单个文件失败不影响其他文件。
- 后台执行并实时显示处理数量、当前文件、复制/校验阶段。浏览器刷新后重新连接正在运行的任务。
- 安全停止：完成当前文件后停止，未处理文件标为「待继续」；可以继续，也可以撤销已完成的文件。
- 失败项一键重试：只处理失败文件，重新检查路径和原文件状态，目标重名时自动编号，不重复处理成功项。原文件内容已修改时仍拒绝移动，需要重新扫描。
- 整理前检查目标目录创建和临时文件写入/清理权限，失败则保持预览、保留所有源文件，并给出处理建议。
- SQLite 任务历史、逐文件操作记录和撤销；撤销不覆盖原位置的新文件，修改过的归档文件不自动恢复。
- 扫描结果仅在服务内存中临时缓存（最多 30 次预览），不自动写入数据库或历史；刷新界面后不自动恢复，服务重启后过期。
- 主动「保存草稿」可保留勾选文件、分类筛选、源/目标目录、规则和递归设置。刷新或重启后自动恢复最近保存的草稿；修改选择后需点击「更新草稿」。草稿不会自动执行。
- 草稿与整理记录分开显示。「查看」从服务读取最新记录并滚动、聚焦到详情区域；执行草稿后转为整理记录。
- 中断后恢复记录；无法确定完整状态时保留文件并提示人工核对。
- 后端验证本机 Host / Origin，写操作要求 JSON；界面无需上传文件。

## 使用边界

建议先用一个测试文件夹体验。选择磁盘根目录时先不开启递归，避免误整理软件、游戏或项目中的资料。扩展名只能识别候选文件类型，不能可靠判断一个 EXE 是否为安装器；软件目录排除也无法识别所有自定义安装位置。

移动文档可能改变相对链接、外部数据引用和快捷方式。默认只整理当前层级，勾选递归前需确认目录用途。

本版本不删除重复文件，不扫描文件正文，不更改注册表；不支持符号链接/目录联接。单次扫描上限为 10000 个文件，超限要求缩小目录范围。复制方式需要目标磁盘有足够空间，较大文件比同盘直接重命名耗时。硬链接关系、ACL、NTFS 附加数据流不保证保留，适用于普通文档和安装包文件。

英文目录规则只用于新扫描产生的计划。旧预览及历史中的路径不自动更改，确保撤销仍按实际原路径执行。更新后请重新扫描，不要执行旧预览。原文件名或用户输入的源/目标目录仍可能包含中文，不会擅自改名。

执行期间应保持服务运行，不同时编辑相关文件。历史存在 `backend/data/tasks.sqlite3`，不要删除该数据库，否则无法利用记录撤销。中断时可能同时保留源文件与复制文件；请按记录核对，工具不会擅自删除不确定的副本。撤销不删除整理时创建的空目录。

历史记录和主动保存的草稿均保存在这一个本机 SQLite 文件中，正常重启服务后仍保留。列表展示最近 30 条整理记录，数据库内的旧记录不会因列表限制被删除。旧版本自动保存的扫描记录会从历史列表隐藏，实际整理记录及其撤销路径保持原样。`Packages` 规则只作用于新扫描，不自动重命名现有归档目录。

## 验证

```powershell
python -m unittest backend.test_organizer -v
python -m pip install -r backend\requirements-dev.txt
python -m unittest backend.test_api -v
cd frontend
npm run build
```

文件操作测试使用临时目录，不处理真实 D 盘文件。

## 项目结构与后续扩展

```text
backend/
  organizer.py       # 扫描、计划、文件移动、撤销、持久化
  main.py            # FastAPI 接口与本机访问约束
  test_organizer.py  # 文件安全行为测试
frontend/
  src/App.vue        # 整理界面
  src/style.css      # 界面样式
```

当前采用单项目、前后端分离结构，文件操作逻辑不依赖 FastAPI。桌面壳启动同一个本机后端并加载 Vue 界面，已支持目录选择和后台任务进度。后续可按需要增加自定义分类规则、重复文件分析，或拆分数据库仓储与规则引擎。暂时无需引入 Django、Redis 或多服务部署。

## 构建 EXE

推荐使用 Python 3.11 的干净虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-desktop.txt -r backend\requirements-dev.txt
cd frontend
npm ci
cd ..
.\build.ps1
```

产物在 `dist/ShiXu-0.2.0-windows-x64.exe`。`ShiXu.spec` 仅包含程序代码、依赖和构建后的 Vue 界面，不包含数据库、测试文件、日志或本地缓存。发布前应核对 SHA-256，并在干净 Windows 环境验证目录选择、整理、停止、重试和撤销。

开发时可用 `.\.venv\Scripts\python.exe desktop.py` 启动桌面壳。`FILE_ORGANIZER_DATA_DIR` 可用于隔离测试数据目录；普通用户无需配置环境变量。

同一数据目录的桌面版同时只允许一个实例，避免重复启动后互相干扰整理记录。执行 `.\release.ps1` 可生成源码 ZIP 和 `dist/SHA256SUMS.txt`；脚本只在本机准备文件，不上传。源码包使用明确的文件清单，排除用户数据、依赖目录和测试工作目录。
