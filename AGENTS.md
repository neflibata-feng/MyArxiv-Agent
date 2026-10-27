# 开发约定

- 使用当前隔离环境中的现有 checkout；未经用户要求不要创建 worktree。
- 网页位于 `web/`，使用 `npm ci` 安装，`npm run build` 验证 TypeScript 与生产构建。
- Python 使用虚拟环境，依赖为 `scripts/requirements.txt`。数据库与 Inbox 是用户数据，验证迁移、抓取和归档时使用临时副本，禁止直接改写真实数据。
- 修改 Markdown 渲染时同时验证公式、代码高亮、相对资源与恶意 HTML 清洗。
- 每个优化独立分支与 PR；提交前检查 diff，并说明实际测试与限制。未经明确授权不要合并。
- 本批优化允许修改应用代码；文档改动仅限 README 与本文件，不新增其他文档，不提交测试脚本、测试输出、构建产物或凭据。测试放在 checkout 外或忽略目录。
- 构建会生成 `web/vite.config.js`、`web/vite.config.d.ts`，只清理本次运行新生成的文件。当前仓库缺少 ESLint 配置，不能把 lint 未运行报告为通过。

- 提交信息统一使用 `类型:中文描述` 格式，例如 `feat:增加论文筛选`。
