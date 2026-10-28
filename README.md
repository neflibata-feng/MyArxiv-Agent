<p align="center"><img src="assets/ascii-art-text.png" alt="MyArxiv-Agent" width="500"></p>
<p align="center"><strong>中文</strong> · <a href="README.en.md">English</a></p>

# MyArxiv-Agent

一个开源的 arXiv 论文管理模板：按关注领域抓取论文，在收件箱筛选，将论文归档并建立阅读笔记，也可以通过网页管理仓库内容。

本仓库提供代码和空白起点，不维护个人论文库。欢迎提交 Issue、改进代码和文档，或提出新的功能建议。

## 开始使用

1. Fork 本仓库，或在 GitHub 启用模板功能后使用 **Use this template** 创建自己的仓库。之后在自己的仓库操作。
2. 安装 Python 3.9 或更新版本，在仓库根目录创建虚拟环境并安装依赖：

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r scripts/requirements.txt
   ```

3. 编辑 `config.yaml`：设置 `meta.owner`，并按需要调整 `fetch.query` 的分类、关键词、`fetch.arxiv_api.max_results` 和 `inbox.render` 的容量。环境变量也可覆盖配置，例如 `ARXIV_AGENT__fetch__arxiv_api__max_results=100`；层级以双下划线分隔。
4. 初始化空数据库并生成收件箱：

   ```bash
   python scripts/migrate_to_sqlite.py
   ```

   此命令会导入已有 Inbox 和 Papers 内容；全新模板为空。如果从已有仓库迁移，请先备份数据，避免意外覆盖。
5. 抓取并筛选论文：

   ```bash
   python scripts/fetch_arxiv.py
   ```

   在 `Inbox.md` 中勾选要归档的条目，删除不感兴趣的条目，然后执行：

   ```bash
   python scripts/process_inbox.py
   ```

   归档结果写入 `Papers/`、`Notes/` 和 `Contents.md`。数据库 `data/arxiv.db` 保存完整状态，Inbox 只是有限容量的可编辑视图。请将数据库与上述文件一起保存或提交；只清空 Inbox 不会清空数据库。

模板不包含定时抓取或自动归档工作流。需要自动化时，请在自己的仓库自行配置调度、提交权限和分支保护；要求通过 PR 的分支不能直接推送。运行抓取、归档或网页编辑前，先同步最新版本，避免覆盖他人的更改。

## 网页使用

本地预览：

```bash
cd web
npm ci
npm run dev
```

登录时输入自己的 `用户名/仓库名` 和 GitHub fine-grained PAT。给令牌限定目标仓库并授予 `Contents: Read and write`；PAT 保存在浏览器本地，请使用可信设备，不要提交令牌。网页直接修改仓库文件，因此需要对应分支的写入权限；受保护分支可能拒绝直接保存。网页默认访问 `main` 分支。

本仓库不附带 GitHub Actions 工作流。网页可通过本地开发服务器使用，也可以在自己的仓库中运行 `npm run build`，将 `web/dist/` 发布到支持静态文件的托管服务。

## 项目结构

- `scripts/`：抓取、收件箱处理和 SQLite 初始化脚本。
- `config.yaml`：查询、路径、格式和存储配置。
- `Inbox.md`、`Contents.md`：收件箱与归档索引的空白起点。
- `Papers/`、`Notes/`：论文元数据与阅读笔记；`data/arxiv.db` 在初始化时创建。
- `web/`：网页客户端。
- `agent/skills/`：可复用的研究和写作技能，目前没有与抓取流程自动集成。

## 参与贡献

欢迎通过 Issue 讨论问题或建议，也欢迎提交 Pull Request。请先说明改动目的；较大的改动建议先开 Issue 讨论。提交前请检查差异，并运行与改动相关的验证：网页修改可在 `web/` 执行 `npm ci` 和 `npm run build`；涉及抓取或归档的验证请使用临时数据，避免提交个人论文数据、数据库、构建产物或凭据。

## 许可与致谢

代码和自动化框架采用 [Apache-2.0](LICENSE-APACHE)，文档、截图等内容采用 [CC BY-NC-SA 4.0](LICENSE)。论文版权属于原作者及出版方；使用论文数据时请遵守相关许可与学术规范。感谢 arXiv 提供开放的论文元数据。
