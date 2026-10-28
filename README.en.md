<p align="center"><img src="assets/ascii-art-text.png" alt="MyArxiv-Agent" width="500"></p>
<p align="center"><a href="README.md">中文</a> · <strong>English</strong></p>

# MyArxiv-Agent

An open-source template for fetching arXiv papers, reviewing an inbox, archiving metadata, and keeping reading notes. The web client can also manage repository content. This repository supplies an empty starting point rather than a personal paper collection. Issues, suggestions, and pull requests are welcome.

## Getting started

1. Fork this repository, or use **Use this template** if the repository owner has enabled GitHub's template feature. Work in your own repository.
2. Install Python 3.9 or later and dependencies from the repository root:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r scripts/requirements.txt
   ```

3. Edit `config.yaml`, including `meta.owner`, `fetch.query`, `fetch.arxiv_api.max_results`, and `inbox.render`. Configuration can also be overridden with environment variables such as `ARXIV_AGENT__fetch__arxiv_api__max_results=100`.
4. Run `python scripts/migrate_to_sqlite.py` to initialize the database. The command imports existing Inbox and Papers content; the new template starts empty. Back up existing data before migrating another repository.
5. Run `python scripts/fetch_arxiv.py`. Check papers to archive or remove unwanted entries in `Inbox.md`, then run `python scripts/process_inbox.py`. Results appear in `Papers/`, `Notes/`, and `Contents.md`. Keep `data/arxiv.db` with these files: SQLite holds the complete state and Inbox is only a limited view.

Optional fetching, archiving, and web app deployment workflow templates are stored in `.github/workflow-templates/` and do not run by default. In your own repository, review and copy the workflows you need into `.github/workflows/`, then adjust the default branch, schedule, permissions, and branch protection before committing. The fetch and archive templates push directly to `main`; branches requiring pull requests reject direct pushes, so adapt them to a pull-request workflow or adjust the rules. Enable repository content write permissions and run a manual check. Sync your repository before fetching, archiving, or editing through the web client.

## Web client

Run locally with `cd web`, `npm ci`, and `npm run dev`. Sign in with your own `owner/repository` and a fine-grained GitHub PAT limited to that repository with `Contents: Read and write`. The browser stores the PAT locally; use a trusted device and never commit the token. The client writes directly to `main`, so protected branch rules may prevent saves.

The project brand site lives on the `codex/brand-site` branch and is deployed by a workflow on the main branch that runs only in the original repository. To use your own web app, run the local development server or run `npm run build` and publish `web/dist/` with a static hosting service.

## Project layout

`scripts/` contains the Python tools; `config.yaml` controls queries and paths; `Inbox.md` and `Contents.md` are empty starting views; `Papers/` and `Notes/` hold archives and notes; `data/arxiv.db` is created during initialization; `web/` contains the web client; and `agent/skills/` contains reusable research and writing skills that are not automatically integrated into the fetch pipeline.

## Contributing

Please open an issue to report problems or propose improvements, and submit pull requests with a clear description. Discuss larger changes in an issue first. Review your diff and run relevant checks: for web changes, run `npm ci` and `npm run build` in `web/`; use temporary data when testing fetching or archiving. Do not commit personal paper data, databases, build output, or credentials.

## Licenses and credits

This project is licensed under [Apache-2.0](LICENSE). Rights and terms for papers and their metadata are determined separately by their authors, publishers, and data sources; the project license does not alter them. Thanks to arXiv for its open metadata.
