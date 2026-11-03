<p align="center"><img src="assets/ascii-art-text.png" alt="MyArxiv-Agent" width="500"></p>
<p align="center"><a href="README.md">中文</a> · <strong>English</strong></p>

# MyArxiv-Agent

An open-source personal workspace for arXiv papers by [@neflibata-feng](https://github.com/neflibata-feng). Fetch papers by topic, review your inbox, archive selected papers, and keep reading notes in your own GitHub repository. Manage the files through the web client or edit Markdown directly.

This repository provides the code and an empty starting point, not a personal paper collection.

## Getting started

### 1. Create your repository

Use **Use this template → Create a new repository** on GitHub. Choose your account, repository name, and visibility, then clone the new repository:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

The examples assume the default branch is `main`. A private repository restricts access to its contents; any deployed website has its own visibility settings.

### 2. Install dependencies

Use Python 3.11 or later. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r scripts/requirements.txt
```

### 3. Configure your interests

Edit the corresponding sections of `config.yaml`, preserving the rest of the file:

```yaml
meta:
  owner: "YOUR_GITHUB_USERNAME"
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

| Setting | Purpose |
| --- | --- |
| `meta.owner` | Repository owner's GitHub username |
| `fetch.query.categories` | arXiv subject categories |
| `fetch.query.keywords` | Keywords to match |
| `fetch.query.keyword_field` | Search field: `all`, `ti` for title, `abs` for abstract, etc. |
| `fetch.query.combine_mode` | Combine category and keyword groups; the example requires both |
| `fetch.query.id_list` | Optional exact arXiv IDs; see the configuration comments for filtering behavior |
| `fetch.arxiv_api.max_results` | Number of records requested per fetch |
| `inbox.render.max_items` / `max_bytes` | Limits for the rendered inbox; SQLite retains the full state |

Other options control summary length, version-update notices, note templates, paths, and HTTP retries. The web client's **Settings** page exposes common options; edit YAML for the remaining settings. Never store credentials in configuration or commits.

### 4. Initialize the database

```bash
python scripts/migrate_to_sqlite.py
```

This imports existing Inbox and Papers content, creates the database, and renders the inbox. Back up an existing collection before migration. Commit the initialized files:

```bash
git add config.yaml data/arxiv.db Inbox.md
git commit -m "chore:initialize paper workspace"
git push origin main
```

Keep `data/arxiv.db` together with `Inbox.md`, `Papers/`, `Notes/`, and `Contents.md`. SQLite is the complete source of paper and processing state; clearing the Markdown inbox does not clear the database.

### 5. Enable automation

Optional workflows live in `.github/workflow-templates/` and do not run until copied into `.github/workflows/` and committed to the default branch.

| Template | Purpose | Trigger |
| --- | --- | --- |
| `daily_scheduler.yml` | Fetch papers and update SQLite and Inbox | Daily at 01:25 UTC (09:25 China Standard Time), or manually |
| `auto_archive.yml` | Process checked and removed inbox entries, update archives and notes | Inbox changes, or manually |
| `deploy-web.yml` | Build the web client and publish to `gh-pages` | Changes under `web/` on `main`, or manually |

```bash
mkdir -p .github/workflows
cp .github/workflow-templates/daily_scheduler.yml .github/workflows/
cp .github/workflow-templates/auto_archive.yml .github/workflows/
cp .github/workflow-templates/deploy-web.yml .github/workflows/
git add .github/workflows/
git commit -m "ci:enable paper workflows"
git push origin main
```

Windows users can copy the files using File Explorer. Fetch and archive templates use Ubuntu 24.04 and Python 3.11. They check out and push to `main`; update branch references if your default branch differs. In **Settings → Actions → General → Workflow permissions**, allow repository content writes. Repository or organization rules must also permit these operations; branch rules requiring PRs will reject direct writes unless you adapt the workflows.

Run **Actions → Daily Arxiv Fetcher → Run workflow** once and inspect the result. Scheduled runs may be delayed by GitHub. In the inbox, check papers to keep and remove unwanted entries, then sync your changes. **Auto Archive & Organize** archives selected papers under `Papers/`, creates notes under `Notes/`, and updates `Contents.md`.

Pushes made with a workflow's `GITHUB_TOKEN` do not normally trigger another `push` workflow. The fetcher's own commit therefore does not automatically start archiving. Changes saved using your web PAT or a regular Git push can trigger it. See [GitHub's workflow trigger documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

For local use, sync the repository first, then run:

```bash
python scripts/fetch_arxiv.py
# Review Inbox.md before processing it.
python scripts/process_inbox.py
```

### arXiv rate limits

Requests use a browser-compatible User-Agent with an application identifier and maintainer link, a reused connection session, and a minimum three-second interval within each process. Retries use backoff with jitter and honor `Retry-After` seconds or HTTP dates. You can set your own application/contact header in `fetch.arxiv_api.http.user_agent`.

If retries are exhausted after a 429 followed by timeouts or other temporary failures, the fetcher exits with code `75`. The workflow waits at least five minutes, honors a longer server cooldown, and starts one replacement run. If the cooldown exceeds 15 minutes, it stops rather than retrying early. If the replacement run also fails due to rate limiting, it reports failure without another automatic restart. Pure network failures and permanent errors are not treated as rate limits.

Updating a template does not update a previously copied workflow: apply the changes to your active `.github/workflows/daily_scheduler.yml` too. User-Agent changes cannot guarantee relief from upstream limits on GitHub's shared outbound IP addresses.

## Web client

### Run locally

```bash
cd web
npm ci
npm run dev
```

### Deploy with GitHub Pages

1. Enable `deploy-web.yml` as described above.
2. Run **Actions → Deploy Web App → Run workflow** on `main`. The build is pushed to `gh-pages`.
3. In **Settings → Pages**, select **Deploy from a branch**, branch `gh-pages`, and folder `/ (root)`.
4. Open the URL shown by GitHub, usually `https://YOUR_USERNAME.github.io/YOUR_REPOSITORY/`.

Private-repository Pages availability depends on your GitHub plan; verify site visibility separately. The original project's brand site is maintained on `brand-site` and its deployment runs only in the original repository. It does not deploy your personal web client.

### Connect your repository

Create a fine-grained PAT in GitHub personal settings, restrict it to your paper repository, and grant **Contents: Read and write**. Enter `owner/repository` and the PAT on the web client's login screen. The paper-management views use `main`; check your branch name, access, token expiration, and branch rules if reads or saves fail.

The browser stores the PAT locally. Use a trusted device and never commit it.

## Research assistant

Research tasks run in GitHub Actions. The web client configures the model, submits tasks, and displays results. Features include interest-based paper recommendations, reversible feedback, local and arXiv retrieval, research answers, structured reviews, and explicit approval to create a note PR.

### Enable the workflow

If `research-agent.yml` is not already active, copy it into `.github/workflows/` and commit it to the default branch:

```bash
cp .github/workflow-templates/research-agent.yml .github/workflows/
git add .github/workflows/research-agent.yml
git commit -m "ci:启用研究助手"
git push origin main
```

1. In **Settings → Secrets and variables → Actions**, add your model API key. The default secret name is lowercase `key`.
2. In **Settings → Actions → General**, allow workflow content writes. To save review notes, enable **Allow GitHub Actions to create and approve pull requests**. The application creates PRs but does not approve or merge them.
3. Give the web client's PAT **Contents: Read and write**, **Actions: Read and write**, and **Pull requests: Read and write** when creating note PRs.
4. Open the **Research** tab, then **Research settings** (UI label: `研究配置`). Save your model, budget, interests, and subscriptions. Refresh the workflow status, then use **Test model connection** (`测试模型连接`) to verify an actual request; its result appears as a task.

### Model and budget settings

Choose DeepSeek, OpenAI, or an OpenAI-compatible service. The service must support Chat Completions, tool calls, JSON output, and token usage reports. Enter the provider's API base URL and model name; include `/v1` if required, but do not append `/chat/completions`.

The configured secret name must match a GitHub Actions secret. Only the name is saved in configuration; manage the key itself in GitHub Secrets. After switching providers, add the key under the new secret name before testing.

The web client writes settings under `agent` in `config.yaml`; the runner reads them at task startup:

```yaml
agent:
  runtime:
    provider: deepseek          # deepseek / openai / compatible
    base_url: https://api.deepseek.com
    model: deepseek-flash
    key_secret: key             # Actions secret name, not the API key
    default_budget: 50000       # Cumulative tokens per task
    max_budget: 1000000         # Maximum allowed task budget
    max_output_tokens: 4096     # Maximum output per model request
    max_rounds: 12              # Maximum model request rounds
    timeout_seconds: 90         # Timeout per model request
  interests:
    - multi agent collaboration
  subscriptions:
    - id: multi-agent
      query: multi agent collaboration
      enabled: true
```

A task budget covers input and output across all model requests in that task. It is not a monetary or account-wide spending cap. The default must not exceed the task maximum. Recommendations and feedback do not call the model; research and reviews do. Tasks stop if the provider does not report valid usage.

Subscriptions are independent of `fetch.query`. Use plain phrases, not raw arXiv query expressions. Up to 10 topics are supported, with at most three pages of 100 records per topic per run. Initial scans start from historical records, then continue from saved cursors; results are deduplicated across topics by base arXiv ID. Scheduled recommendations remain disabled unless the Actions variable `RESEARCH_SCHEDULE_ENABLED` is set to `true`. The schedule is 02:10 UTC (10:10 China Standard Time).

### Daily workflow

1. **Recommend papers**: combine pending papers with enabled subscription results and show ranking reasons. Like, dislike, and clear-feedback actions affect future rankings without training the model. Recommendations are not automatically added to Inbox.
2. **Ask a research question**: enter a question, optionally select up to 10 arXiv IDs already in the repository database, and set the task budget. Tools can search metadata, notes, indexed local text, and online arXiv metadata. Supplying an ID does not download or import a paper.
3. **Generate a review**: request a comparison of methods, results, and limitations. References must come from the current retrieval. Open **Review full draft** (`审阅完整草稿`), check the evidence, and confirm to create a note PR. Review and merge that PR on GitHub.
4. **Track tasks**: while visible, the page refreshes every 15 seconds. View the report, usage, sources, and tool results; download Markdown or open the Actions run for logs and artifacts. Failed or partial recommendation, research, and review tasks can be retried. Running tasks can be cancelled; wait for GitHub to confirm the result.

You can also use **Actions → Research Agent → Run workflow**:

| Operation | Inputs |
| --- | --- |
| `recommend` | Optional topic ID in `target`; `ranking=date` restores date order |
| `feedback` | One `paper_ids` value and `feedback=like`, `dislike`, or `clear` |
| `research` | `question`, optional `paper_ids`, optional `budget` |
| `review` | Same inputs as research; produces a draft for inspection |
| `approve` | Draft ID in `target`; creates a note PR |
| `tasks` | No additional inputs |
| `retry` | Failed task ID in `target`, optionally a new budget |

Leave `budget` empty to use the configured default. To retry an eligible failed fetch/archive workflow, use `actions:RUN_ID` as the target. Feedback and approval operations are not replayed by retry.

### Storage and limits

- `data/arxiv.db` stores paper metadata and processing state. Retrieval indexes configured Markdown, text, text-extractable PDFs, and abstracts, up to 2,000 chunks. It does not perform OCR or automatically download arbitrary websites or paid full text.
- Feedback, subscription progress, recent tasks, and drafts are stored in `data/agent-state.json` on the `agent-state` branch. State is limited to 900 KB; old previews, cache entries, drafts, and task records may be removed. Explicit feedback is not automatically deleted.
- Actions artifacts are retained for seven days. Long web reports are truncated; use the run artifact for the full output. A successful approval creates `Notes/Research-DRAFT_ID.md` on a dedicated branch and opens a PR.
- Questions and retrieved material are sent to the selected model provider. Stored state and artifacts follow repository visibility.
- Source validation confirms that a record was retrieved, not that a conclusion is correct. All research claims still require human review.
- Actions depends on GitHub scheduling, permissions, and provider availability. Invalid credentials, insufficient funds or budget, timeouts, and rate limits appear in task results or run logs. The workflow timeout is 25 minutes.

### Run the web client locally

Install Node.js 20 or later, then run from the repository root:

```bash
cd web
npm ci
npm run dev
```

Open the URL printed by Vite and connect your own paper repository. Research tasks still execute in GitHub Actions, with API keys stored in that repository's Actions secrets. Use `npm run build` for a production build and `npm run preview` to preview it.

### Troubleshooting

| Symptom | Action |
| --- | --- |
| Research workflow disabled or outdated | Copy the latest `research-agent.yml` template into the active directory, commit to the default branch, enable it in Actions, and refresh the page |
| 401/403, dispatch or PR creation fails | Check PAT expiration, repository access, Contents / Actions / Pull requests permissions, and Actions write/PR settings |
| Model connection fails | Check the exact secret name, model, base URL, balance, tool-call support, and usage reporting; the connection test consumes tokens |
| Budget exhausted or research times out | Narrow the question, select fewer papers, or retry with a larger budget within the configured limit; the workflow timeout is 25 minutes |
| arXiv returns 429 | Respect the logged cooldown and avoid repeated manual restarts; fetching automatically restarts at most once |
| Report truncated or old drafts missing | Download the run artifact for the full report; artifacts expire after seven days and old state records are pruned |

## Project layout

- `agent/`: model settings, retrieval tools, recommendations, feedback, subscriptions, task state, and review PRs; `skills/` contains research skill resources.

- `scripts/`: fetching, inbox processing, SQLite initialization, and arXiv HTTP utilities.
- `config.yaml`: queries, storage, paths, and rendering settings.
- `Inbox.md` / `Contents.md`: inbox and archive index.
- `Papers/` / `Notes/`: archived metadata and reading notes.
- `data/arxiv.db`: SQLite state, created during initialization.
- `web/`: web client.
- `.github/workflows/`: checks and the original project's brand-site deployment.
- `.github/workflow-templates/`: optional automation, disabled until copied into the active directory.

## Contributing

Open an issue for bugs or proposals; discuss larger changes before implementation. Fork the repository, create a branch from the latest `main`, and submit a PR with a clear description and validation results. Use the template feature for a personal paper workspace.

Read [AGENTS.md](AGENTS.md) when using AI tools. For web changes, run `npm ci` and `npm run build` in `web/`. Use temporary data when testing fetching or archiving. Do not commit personal paper data, databases, build output, or credentials.

## License and credits

This project is licensed under [Apache-2.0](LICENSE). Papers and metadata remain subject to the rights and terms set by their authors, publishers, and sources. Thanks to arXiv for providing open paper metadata.
