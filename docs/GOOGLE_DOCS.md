# Google Docs: weekly pulse append

After each successful **Phase 4** run, the pipeline writes:

| File | Purpose |
|------|--------|
| `data/reports/<ISO_WEEK>_gdoc_payload.json` | Structured payload for **MCP** (recommended) or manual paste |
| `data/reports/<ISO_WEEK>_pulse.md` | Full Markdown report |

---

## Pipeline → MCP → Google Docs (automated)

Phase 4 can append to a Doc **without Cursor** by spawning the same **`@a-bonus/google-docs-mcp`** package over the **MCP stdio** protocol from Python ([`shared/mcp_google_docs_append.py`](../shared/mcp_google_docs_append.py)).

Set:

| Variable | Value |
|----------|--------|
| `GOOGLE_DOCS_APPEND_ENABLED` | `true` |
| `GOOGLE_DOCS_APPEND_TRANSPORT` | `mcp` |
| `GOOGLE_DOCS_DOCUMENT_ID` | Doc ID from the URL |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth Desktop client (same as Cursor MCP) |

On the machine that runs the scheduler, run **`npx -y @a-bonus/google-docs-mcp auth` once** so `~/.config/google-docs-mcp/token.json` exists. Install **Node.js** (`npx` on `PATH`) and **`pip install mcp`** (see `requirements.txt`).

**Default** `GOOGLE_DOCS_APPEND_TRANSPORT=direct` uses the **Google Docs REST API** + **service account** in [`shared/google_docs_client.py`](../shared/google_docs_client.py) — better for headless CI when you do not want OAuth tokens on disk.

---

## `@a-bonus/google-docs-mcp` (configured in this repo)

This project wires **[a-bonus/google-docs-mcp](https://github.com/a-bonus/google-docs-mcp)** via **[`.cursor/mcp.json`](../.cursor/mcp.json)** (npm package [`@a-bonus/google-docs-mcp`](https://www.npmjs.com/package/@a-bonus/google-docs-mcp)).

**Workspace root:** Open the **inner** project folder (the one that contains **`.env`** and **`.cursor/`** next to each other) as the Cursor workspace. MCP uses `"${workspaceFolder}/.cursor/google-docs-mcp.sh"`. If you instead open a **parent** folder, set the command to `"${workspaceFolder}/WeeklyProductPulse/.cursor/google-docs-mcp.sh"`.

### 1. Google Cloud (OAuth Desktop client)

Follow the upstream **[README](https://github.com/a-bonus/google-docs-mcp#quick-start)**:

1. Enable **Google Docs API**, **Google Sheets API**, and **Google Drive API** for a project.
2. Configure the **OAuth consent screen** (External; add your Google account as a **Test user**).
3. Create **OAuth client ID** → type **Desktop app**.
4. Copy **Client ID** and **Client Secret**.

### 2. Put credentials in `.env` (not committed)

Copy [`.env.example`](../.env.example) to `.env` and set:

```bash
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=....
```

The MCP config runs **[`.cursor/google-docs-mcp.sh`](../.cursor/google-docs-mcp.sh)**, which **`source`s `../.env`** before `npx`. (Relying on Cursor’s `envFile` alone often **does not** inject variables into the MCP child process, which leads to “No OAuth credentials found” in MCP logs.)

### 3. Authorize once (browser)

From the directory that contains `.env` (the inner `WeeklyProductPulse` project folder):

```bash
cd /path/to/WeeklyProductPulse/WeeklyProductPulse   # folder with .env
set -a && source .env && set +a
npx -y @a-bonus/google-docs-mcp auth
```

Or:

```bash
GOOGLE_CLIENT_ID="..." GOOGLE_CLIENT_SECRET="..." npx -y @a-bonus/google-docs-mcp auth
```

This stores a refresh token under `~/.config/google-docs-mcp/token.json`.

### 4. Restart Cursor

Open **Settings → MCP** and confirm **`google-docs`** is listed and enabled. Check **Output → MCP Logs** if it fails to start.

### 5. Weekly append (after Phase 4)

1. Run Phase 4 so `data/reports/<week>_gdoc_payload.json` exists.
2. In **Agent**, ask to use tools such as **`appendMarkdownToGoogleDoc`** or **`appendText`** with:
   - **Document ID** from your Doc URL: `https://docs.google.com/document/d/DOCUMENT_ID/edit`
   - Content built from the payload: `weekly_pulse`, `fee_scenario`, `explanation_bullets`, `source_links`, `date`

Example: *“Call `appendMarkdownToGoogleDoc` to append the contents of `data/reports/2026-W12_gdoc_payload.json` (or the markdown body from `weekly_pulse`) to document `DOCUMENT_ID`.”*

Upstream tool list includes `readDocument`, `appendText`, `appendMarkdownToGoogleDoc`, `replaceDocumentWithMarkdown`, and more — see the [GitHub README](https://github.com/a-bonus/google-docs-mcp#what-can-it-do).

---

## Other MCP servers (optional)

If you prefer a different Docs MCP, browse **[Cursor Marketplace](https://cursor.com/marketplace)** or **[cursor.directory](https://cursor.directory/)** and add it to **`.cursor/mcp.json`** or **`~/.cursor/mcp.json`**. Official Cursor docs: [Model Context Protocol](https://cursor.com/docs/context/mcp).

---

## Connect via MCP (Cursor) — **no Python Google API**

The **Google Docs API in this repo** (`shared/google_docs_client.py`) is optional. If you only want **Cursor + MCP**, you do **not** need:

- `GOOGLE_DOCS_APPEND_ENABLED`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `pip install google-api-python-client`

Those are for **headless / cron** append (see [Option B — Python API](#option-b--automated-append-google-docs-api) below).

### How MCP fits

1. **MCP servers run inside Cursor** (Agent/Composer), not inside your WeeklyProductPulse Python process.
2. You **install and authenticate** a Google-related MCP server once in Cursor.
3. After each weekly run, you (or the Agent) use MCP **tools** to create/append content in a Doc, using the fields from `*_gdoc_payload.json`.

### Weekly workflow (any MCP)

1. Run Phase 4 (e.g. `python -m phase4_report.report_generator --week 2026-W12`).
2. Open `data/reports/<week>_gdoc_payload.json` or ask the Agent to read it.
3. Use your MCP tools to append to Doc **DOCUMENT_ID** from  
   `https://docs.google.com/document/d/DOCUMENT_ID/edit`

### Payload shape (for MCP tools)

```json
{
  "iso_week": "2026-W12",
  "date": "2026-03-22",
  "generated_at_utc": "2026-03-22T...",
  "weekly_pulse": "# full markdown ...",
  "fee_scenario": "Mutual fund exit load",
  "explanation_bullets": ["...", "..."],
  "source_links": [{"label": "...", "url": "https://..."}]
}
```

Map these keys to whatever your MCP server expects (plain text append vs structured blocks).

### If you don’t find a Docs MCP you trust

- You can still open `*_gdoc_payload.json` and **paste** sections manually into a Doc.
- Or use **Option B** below for fully automated append without opening Cursor.

---

## Option B — Automated append (Google Docs API, Python)

For **cron / CI / headless** runs without Cursor, enable the built-in append in this repo:

1. Enable **Google Docs API** in Google Cloud; create a **service account** and download JSON.
2. **Share** the target Doc with the service account email (Editor).
3. Set:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
export GOOGLE_DOCS_DOCUMENT_ID="your-doc-id-from-the-url"
export GOOGLE_DOCS_APPEND_ENABLED=true
```

4. Run Phase 4. See [`shared/google_docs_client.py`](../shared/google_docs_client.py).

CLI: `--google-doc-append` / `--no-google-doc-append`.

**Note:** API append failures are logged; Phase 4 still writes Markdown + `*_gdoc_payload.json`.

---

## Document ID

From a Doc URL: `https://docs.google.com/document/d/DOCUMENT_ID/edit` — use `DOCUMENT_ID`.
