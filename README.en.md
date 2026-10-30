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

## GitHub Actions research system (in development)

## Project layout

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
