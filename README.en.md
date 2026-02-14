<p align="center">
  <img src="assets/logo.png" alt="MyArxiv-Agent" width="500">
</p>

<p align="center">
  <a href="https://github.com/neflibata-feng/MyArxiv-Agent/actions/workflows/daily_scheduler.yml?query=branch%3Amain"><img src="https://img.shields.io/github/actions/workflow/status/neflibata-feng/MyArxiv-Agent/daily_scheduler.yml?branch=main&style=for-the-badge" alt="Daily Scheduler"></a>
  <a href="https://github.com/neflibata-feng/MyArxiv-Agent/actions/workflows/auto_archive.yml?query=branch%3Amain"><img src="https://img.shields.io/github/actions/workflow/status/neflibata-feng/MyArxiv-Agent/auto_archive.yml?branch=main&style=for-the-badge" alt="Auto Archive"></a>
  <a href="https://github.com/neflibata-feng/MyArxiv-Agent/actions/workflows/deploy-web.yml?query=branch%3Amain"><img src="https://img.shields.io/github/actions/workflow/status/neflibata-feng/MyArxiv-Agent/deploy-web.yml?branch=main&style=for-the-badge" alt="Deploy Web"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/Content%20License-CC%20BY--NC--SA%204.0-lightgrey?style=for-the-badge" alt="Content License"></a>
  <a href="LICENSE-APACHE"><img src="https://img.shields.io/badge/Code%20License-Apache--2.0-blue?style=for-the-badge" alt="Code License"></a>
</p>

<p align="center">
  <a href="README.md">中文</a> · <strong>English</strong>
</p>

## About

- This is a personal papers-and-notes repository maintained by **neflibata-feng**.
- It focuses on organizing and sharing AI Agent research since 2026.
- Paper metadata comes from **arXiv**. Notes are **original** and for research/engineering reference.

---

## License

- **Content license (unchanged)**: curated content and written materials (e.g., `Notes/`, Markdown docs, screenshots) are under **CC BY-NC-SA 4.0**. See [LICENSE](LICENSE).
- **Architecture & code license**: the automation framework and code (e.g., `scripts/`, `web/`, `.github/workflows/`) are under **Apache-2.0**. See [LICENSE-APACHE](LICENSE-APACHE).

> Note: paper copyrights belong to the original authors/publishers; this repo is for study and engineering practice.

---

## Disclaimer

1. This repository is non-commercial and respects IP. It provides metadata for **public** papers in the AI Agent area, does not store PDFs at scale, and will remove items upon request.
2. Please follow applicable laws and academic norms and respect the original authors' rights.
3. This repository primarily serves personal use; therefore, **contributions are accepted normally**.
4. Still, in the spirit of openness and sharing, you're welcome to browse the curated papers and notes (a **star** is appreciated).
5. This repository can also serve as a template for a personal arXiv automation knowledge workspace; feel free to **fork** and adapt it.

---

## Screenshots

- ![](assets/5.png)
- ![](assets/4.png)
- ![](assets/3.png)
- ![](assets/2.png)
- ![](assets/1.png)

---

## Repository Structure

```plaintext
/
├── .github/             # GitHub Actions workflows
├── scripts/             # automation scripts
├── assets/              # images and static assets
├── Inbox.md             # inbox (daily review)
├── Contents.md          # index (auto-generated)
├── pdfs/                # paper PDFs (optional)
├── Papers/              # paper metadata archive
├── Notes/               # personal notes
├── config.yaml          # global config
├── .gitignore           # git ignore rules
├── web/                 # web UI source
├── LICENSE              # content license
├── LICENSE-APACHE       # code license
└── README.md            # Chinese README
```

---

## Usage

### Core Workflow

1. **Daily Fetch**: Automatically fetches the latest papers for selected fields (default: AI Agent) into `Inbox.md` at a fixed time (default: 08:30 Beijing time). Default cap is 150/day with deduplication.
2. **Review & Pick**: In `Inbox.md`, mark papers you like with a check. The system will pick them up automatically. Delete lines you don't want; they will be ignored. Periodically clean up old entries to keep it tidy.
3. **Auto Archive**: After you commit changes to `Inbox.md`, the system will:
   - Archive selected papers into `Papers/`.
   - Create note templates under `Notes/`.
   - Update the index in `Contents.md`.

### Global Configuration

The repo root provides `config.yaml` to centrally manage fetching, deduplication, formatting, archiving, and indexing.

- Common options: categories/keywords, fetch count, abstract truncation length, Inbox/Contents templates, archive layout, etc.
- GitHub Actions uses this file by default; no extra changes needed.

> **arXiv API notes**
> - `fetch.query.id_list`: Optional. Specify arXiv IDs (supports `vN`); YAML list or comma-separated string. With only `id_list`, fetches by exact IDs; with other query terms, follows arXiv semantics (intersection/filtering).
> - `fetch.formatting.date_source`: `published`/`updated`, mapping to Atom `<published>` (v1) and `<updated>` (latest).
> - `features.arxiv_version_update_behavior`: `append_notice` adds a “version update” note; `replace` updates old `abs` links to the new version and also appends the note.

### Environment Variable Overrides

Supports overriding any `config.yaml` key via environment variables:

- Prefix: `ARXIV_AGENT__`
- Nested key separator: `__` (double underscore)

Examples:

- `ARXIV_AGENT__fetch__arxiv_api__max_results=200`
- `ARXIV_AGENT__fetch__query__categories=["cs.AI","cs.CL"]`

### FAQ

- **Time & scheduling**
  - **Fetch schedule**
    - arXiv typically starts updating around 08:00 (Beijing time) on weekdays. The default GitHub Actions schedule runs at 08:30 to catch daily updates consistently.
    - There are usually no updates on weekends; you can restrict runs to weekdays if you prefer.
  - **Cron not triggered?**
    - GitHub Actions may be delayed during peak hours, ranging from minutes to hours.
    - To mitigate this, workflows use caching by default; check whether dependency cache is hit.
    - You can also use third-party schedulers (e.g., cron-job.org) to trigger GitHub Actions.
    - If it still fails, try triggering the workflow manually.

- **Web UI**
  - **Cannot load content**
    - The web version is hosted on GitHub Pages and authenticates via a GitHub PAT.
    - Make sure your PAT is configured and has sufficient permissions; otherwise you can read in the repo but cannot edit via the web UI.
    - Create a fine-grained token in GitHub settings (Developer settings), select this repo, and grant read/write permissions.
  - **How to use the web UI**
    - You must fork this repo to your own account and enable GitHub Pages. The web UI needs write access to the repo, so it must be your fork.

---

## Acknowledgements

> Thank you to arXiv for use of its open access interoperability.
