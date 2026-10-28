<p align="center"><img src="assets/ascii-art-text.png" alt="MyArxiv-Agent" width="500"></p>
<p align="center"><strong>中文</strong> · <a href="README.en.md">English</a></p>

# MyArxiv-Agent

由 [@neflibata-feng](https://github.com/neflibata-feng) 开发的开源 arXiv 论文个人知识空间：按关注领域抓取论文，在收件箱筛选，将论文归档并建立阅读笔记，也可以通过网页管理仓库内容。

本仓库提供代码和空白起点，不维护个人论文库。欢迎提交 Issue、Pull Request 和文档改进，或提出新的功能建议。

## 开始使用

### 1. 从模板创建仓库

1. 打开本仓库首页，点击 **Use this template → Create a new repository**。
2. 选择你的账号、填写仓库名称，然后选择 **Public**（公开）或 **Private**（私有）并创建。默认使用 `main` 分支；以下步骤均在你新建的仓库中完成。
3. 将新仓库克隆到本地，并在终端进入仓库目录：

   ```bash
   git clone https://github.com/你的用户名/你的仓库名.git
   cd 你的仓库名
   ```

有隐私需求时可以选择私有仓库。GitHub Free 的公开仓库支持 GitHub Pages；私有仓库使用 Pages 需要 GitHub Pro、Team 或 Enterprise 等支持相应功能的套餐，具体以 [GitHub Pages 文档](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)为准。私有仓库也可以部署网页：网页通过你的个人访问令牌连接仓库，论文和笔记仍由 GitHub 仓库权限控制。请妥善保管令牌，并在可信设备上使用。

### 2. 安装依赖

安装 Python 3.9 或更新版本，在仓库根目录创建虚拟环境并安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r scripts/requirements.txt
```

### 3. 配置关注领域

编辑仓库根目录的 `config.yaml`。配置包含多层结构，修改时保留 YAML 的缩进、引号与列表格式。下面是常用配置的位置和示例值；请在原文件对应位置修改，不必删除其他配置：

```yaml
meta:
  owner: "你的GitHub用户名"
fetch:
  arxiv_api:
    max_results: 150
  query:
    categories: ["cs.AI", "cs.CL"]
    keywords: ["agent", "language model"]
    keyword_field: "all"
    combine_mode: "(cat_or) AND (kw_or)"
inbox:
  render:
    max_items: 200
    max_bytes: 900000
```

- `meta.owner`：填写你的 GitHub 用户名，作为仓库配置中的所有者信息。
- `fetch.query.categories`：要关注的 arXiv 分类；`keywords`：关键词。示例的 `combine_mode` 表示分类条件与关键词条件同时满足，同组内默认用 OR 组合；可根据文件中的说明调整。
- `keyword_field`：搜索字段，`all` 表示全部字段，也可按配置注释使用 `ti`（标题）、`abs`（摘要）等。`id_list` 可用于指定 arXiv ID；同时设置查询条件时会按 arXiv API 语义过滤。
- `fetch.arxiv_api.max_results`：每次抓取数量；`inbox.render.max_items` 和 `max_bytes`：收件箱显示条数和大小的上限。SQLite 保存完整状态，Inbox 只显示有限数量的待处理条目。
- `fetch.formatting.summary_max_chars` 控制摘要截断长度；`features.arxiv_version_update_behavior` 控制版本更新提示；`archive.notes.template.sections` 可调整笔记模板。路径、网络重试和更多参数见文件内注释。

网页连接仓库后，可在 **设置**中可视化修改部分常用配置；未提供可视化控件的选项仍可直接编辑 YAML。请勿把 PAT 或其他凭据写入配置文件或提交记录。

### 4. 初始化并提交

在仓库根目录运行：

```bash
python scripts/migrate_to_sqlite.py
```

此命令会导入已有 Inbox 和 Papers 内容；从模板新建的仓库为空。如果从已有仓库迁移，请先备份数据。初始化后提交配置、`data/arxiv.db` 和 `Inbox.md`：

```bash
git add config.yaml data/arxiv.db Inbox.md
git commit -m "chore:初始化论文知识空间"
git push origin main
```

`data/arxiv.db` 是论文及处理状态的完整数据源；请与 `Inbox.md`、`Papers/`、`Notes/` 和 `Contents.md` 一起保存。只清空 Inbox 不会清空数据库。

### 5. 开启 GitHub 自动化

模板仓库的自动化文件位于 `.github/workflow-templates/`，默认不会运行。在自己的仓库中，将需要的文件复制到 `.github/workflows/` 并提交到 `main`，然后在 **Actions** 页面启用工作流：

| 模板 | 用途 | 触发方式 |
| --- | --- | --- |
| `daily_scheduler.yml` | 抓取论文并更新数据库和 Inbox | 默认每天 UTC 01:25（北京时间 09:25），也可手动运行 |
| `auto_archive.yml` | 处理 Inbox 中的勾选和删除，生成归档、笔记与目录 | Inbox 提交变化或手动运行 |
| `deploy-web.yml` | 构建网页并发布到 `gh-pages` 分支 | `main` 的 `web/` 变化或手动运行 |

例如，在本地复制并提交：

```bash
mkdir -p .github/workflows
cp .github/workflow-templates/daily_scheduler.yml .github/workflows/
cp .github/workflow-templates/auto_archive.yml .github/workflows/
cp .github/workflow-templates/deploy-web.yml .github/workflows/
git add .github/workflows/
git commit -m "ci:启用论文管理工作流"
git push origin main
```

Windows 用户也可以在文件管理器中复制文件后再提交。模板默认检出并推送 `main`；若默认分支名称不同，需要同步修改工作流中的分支引用。在 **Settings → Actions → General → Workflow permissions** 中确认工作流可读写仓库内容；如果仓库要求更严格的令牌策略，也要允许对应权限。

个人仓库一般无需开启规则集；如需启用，请仔细配置，否则可能导致工作流失败。随后打开 **Actions → Daily Arxiv Fetcher → Run workflow** 手动运行一次，检查日志和生成的 Inbox；定时运行可能因 GitHub 调度而延迟。

在 `Inbox.md` 或网页中勾选想保留的论文、删除不感兴趣的条目，再同步到仓库。`Auto Archive & Organize` 会将勾选的论文归档到 `Papers/`、创建 `Notes/` 笔记并更新 `Contents.md`；如果需要，也可以从 Actions 页面手动运行它。GitHub 不会让使用仓库 `GITHUB_TOKEN` 的推送自动触发普通 `push` 工作流，因此**抓取工作流自己的提交不会自动启动归档工作流**；使用你的网页 PAT 或普通 Git 提交筛选结果会触发它。详情见 [GitHub 文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)。

## 网页使用

### 1. 发布到 GitHub Pages

1. 确保已经按上文复制并提交 `deploy-web.yml`。
2. 打开 **Actions → Deploy Web App → Run workflow**，选择 `main` 并运行。成功后，工作流会构建 `web/`，并将结果推送到仓库的 `gh-pages` 分支。若失败，打开该次运行查看日志，并检查写入权限。
3. 打开 **Settings → Pages**，在 **Build and deployment → Source** 选择 **Deploy from a branch**；分支选择 `gh-pages`、目录选择 `/ (root)`，保存并等待发布完成。
4. 打开 Pages 显示的网址，通常是 `https://你的用户名.github.io/你的仓库名/`。后续 `main` 中 `web/` 变化会触发该工作流，也可在 Actions 页面手动重新运行。

品牌展示页的工作流只服务于原项目，不会替你发布个人网页；请使用上述 `deploy-web.yml` 模板。私有仓库的 Pages 可用性取决于账户套餐，网页本身的可见性也应单独确认。

### 2. 创建令牌并连接仓库

1. 在 GitHub 个人设置中打开 **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**。
2. 为令牌设置名称和合理的有效期；在 **Repository access** 中选择 **Only select repositories**，只选你的论文仓库。
3. 在仓库权限中授予 **Contents: Read and write**。生成后妥善保存，令牌通常只会完整显示一次。
4. 打开你部署的网页，在登录页填写 `你的用户名/仓库名` 和令牌，然后连接。网页默认访问 `main`；读取或保存失败时，请检查仓库名、令牌权限和有效期。

网页会把令牌保存在浏览器本地，请只在可信设备上使用；不要把令牌写入文件或提交。

## 项目结构

- `scripts/`：抓取、收件箱处理和 SQLite 初始化脚本。
- `config.yaml`：查询、路径、格式和存储配置。
- `Inbox.md`、`Contents.md`：收件箱与归档索引的空白起点。
- `Papers/`、`Notes/`：论文元数据与阅读笔记；`data/arxiv.db` 在初始化时创建。
- `web/`：网页客户端；`.github/workflows/`：本项目品牌展示页的部署工作流；`.github/workflow-templates/`：默认关闭的可选自动化模板。
- `agent/skills/`：可复用的研究和写作技能，目前没有与抓取流程自动集成。

## 参与贡献

欢迎报告问题、改进文档或代码、提出功能建议。较大的改动建议先创建 Issue 讨论目标和方案。

1. 在本项目 GitHub 页面点击 **Fork**，将仓库复制到自己的账号。贡献使用 Fork；个人论文空间则推荐按上文使用模板创建。
2. 克隆你的 Fork，基于最新 `main` 创建功能分支，完成修改后检查差异并提交。
3. 运行与改动相关的验证：网页修改在 `web/` 执行 `npm ci` 和 `npm run build`；抓取或归档相关验证使用临时数据。不要提交个人论文数据、数据库、构建产物或凭据。
4. 推送分支到你的 Fork，向本仓库 `main` 发起 Pull Request，说明改动目的、实现内容和验证结果，并根据反馈继续完善。

使用 AI 工具协助贡献时，请先阅读仓库中的 [AGENTS.md](AGENTS.md)，遵守开发约定，并自行检查生成的改动和验证结果。

## 许可与致谢

本项目采用 [Apache-2.0](LICENSE) 许可证。论文及其元数据的权利和使用条件由原作者、出版方及数据来源分别规定，不因本项目许可证改变；使用时请遵守相应许可与学术规范。感谢 arXiv 提供开放的论文元数据。
