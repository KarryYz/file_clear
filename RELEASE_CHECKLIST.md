# 0.2.2 发布准备

仓库：[KarryYz/file_clear](https://github.com/KarryYz/file_clear)，维护者 KarryYz，许可证 MIT。

先执行 `.\build.ps1` 和 `.\release.ps1`。在 GitHub 创建 `v0.2.2` 标签，选择已提交并验证的源码作为目标，Release 标题建议「拾序 0.2.2」，复制 `RELEASE_NOTES.md` 作为说明。

上传 `dist` 中的以下文件：

- `ShiXu-0.2.2-windows-x64.exe`
- `ShiXu-0.2.2-source.zip`
- `SHA256SUMS.txt`
- `LICENSE`
- `THIRD_PARTY_NOTICES.txt`
- `RELEASE_NOTES.md`

上传后确认文件的 SHA-256 与清单一致。README 的 `/releases/latest` 会指向最新正式版本。现有 `exe` 标签的 0.2.0 Release 可作为历史版本保留，新版本使用 `v主版本.次版本.修订号` 标签。

- [x] 文件安全行为、草稿和接口自动化测试。
- [x] 前端类型检查与构建。
- [x] Windows x64 单文件 EXE 构建。
- [x] EXE 运行及本机 API/界面资源检查。
- [x] 原生目录选择、路径回填和扫描。
- [x] 实际 EXE 失败项重试、安全停止/继续、撤销内容校验。
- [x] EXE 重启后历史与草稿持久化、正常关闭退出服务。
- [x] 准备不含用户数据的源码 ZIP 和 SHA-256 校验文件。
- [ ] 独立 Windows 10/11 电脑验证（不安装 Python/Node）。
- [x] 确认 GitHub 仓库名、许可证、版本说明和维护者信息。
- [ ] 核对第三方许可证说明并上传 GitHub Release。
- [ ] 如需可信发布者显示，配置代码签名证书。

不要上传 `backend/data/`、用户数据库、日志、`.venv/`、`node_modules/` 或测试工作目录。发布 EXE 需要 WebView2 Runtime；不要把开发机器上的运行成功当成所有 Windows 环境的验证结果。

构建脚本和 CI 不自动发布公开 Release。推送版本一致的 `v*` 标签时，发布工作流会构建附件并创建 Release 草稿；在 GitHub 核对附件和说明后点击发布即可。上传新版后，源码、标签和 EXE 的版本应保持对应。
