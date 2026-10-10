# 拾序 0.2.1 · 文件整理助手

选择文件夹，先预览，再将文件按类型整理到英文目录，支持撤销和保存草稿。

本次修复任务已经结束但结果请求暂时失败时界面不再更新的问题。结果读取失败会继续自动重试，恢复连接后清除错误提示，结果同步完成后才允许新的操作。

新增前端恢复测试、Windows 自动构建检查、MIT 许可证和第三方依赖说明。统一依赖版本与构建中的版本号检查。

## 下载与使用

1. 下载 `ShiXu-0.2.1-windows-x64.exe`，双击运行。
2. 需要 Windows 10/11 x64 和 Microsoft Edge WebView2 Runtime，无需 Python 或 Node。
3. 先选择测试文件夹体验扫描、整理和撤销，再整理自己的文件。

可使用附件 `SHA256SUMS.txt` 核对文件校验值。`ShiXu-0.2.1-source.zip` 是用于开发和构建的源码。

## 数据与升级

桌面版历史和草稿保存在 `%LOCALAPPDATA%\ShiXu\tasks.sqlite3`，日志在同一目录。关闭旧程序后运行新版即可，程序升级保留同一数据目录中的历史和草稿。源码开发版使用 `backend/data/tasks.sqlite3`，迁移方法见 README。

自动生成的压缩包目录为 `Packages`，其他类型使用 Word、PDF、Excel、Images、Videos、Fonts、Other 等英文目录。旧整理记录中的实际路径不会自动改写。

本版本尚未签名，需要 WebView2。单机验证记录见 `VALIDATION.md`；未完成独立 Windows 电脑的兼容性验证。
