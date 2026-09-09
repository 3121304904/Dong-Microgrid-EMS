# Dong 微电网项目 Git 使用与答辩记录

本项目从 2026-09-09 开始采用 Git 管理版本。课程设计为单人独立完成，因此提交记录对应本人在需求、代码、测试、文档和答辩材料上的实际修改。

## 当前本地仓库

- 分支：`main`
- 首次真实提交：`fc2137a` — `chore: initialize Dong microgrid project v1.3`
- 仓库目录：`Code/Dong_v1.3`

## 日常提交步骤

在项目根目录打开 PowerShell，完成一个可运行、可说明的小功能后执行：

```powershell
git status
git add <修改过的文件或文件夹>
git commit -m "feat: 简短描述本次实际完成的功能"
git log --oneline --decorate -10
```

提交信息建议使用：

- `feat:` 新功能，例如 `feat: add risk-aware PV dispatch comparison`
- `fix:` 修复，例如 `fix: remove tab switching ghost image`
- `docs:` 文档或 PPT 更新，例如 `docs: add defense presentation draft`
- `test:` 测试，例如 `test: cover Monte Carlo reproducibility`
- `chore:` 工程维护，例如 `chore: update release packaging notes`

## 首次推送到 GitHub

1. 登录 GitHub 后创建一个**空仓库**，建议名称为 `Dong-Microgrid-EMS`。创建时不要勾选 README、`.gitignore` 或 License 初始化选项。
2. 在本项目目录运行下列命令，并把账号名和仓库名换成实际值：

```powershell
git remote add origin https://github.com/<你的GitHub账号>/<仓库名>.git
git push -u origin main
```

3. 按 Git Credential Manager 或浏览器提示完成 GitHub 登录授权。
4. 打开 GitHub 仓库的 **Commits** 页面，截图保存；该截图可放入结项答辩 PPT 的 Git 使用记录页。

## 答辩注意事项

- 只展示真实发生的提交，不补造或倒填开发历史。
- 每次提交前先运行测试或至少启动一次程序，保证提交对应可说明的状态。
- PPT 中可展示提交哈希、日期、提交说明和 GitHub Commits 网页截图。
- 单人项目无需虚构多人分工；可按“界面、调度模型、数据实验、测试打包、文档答辩”说明本人承担的任务。
