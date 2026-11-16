<div align="center">

# VULNFORGE

### Discover the surface. Connect the evidence.

A modular command center for web security assessments.

**Python 3.11+** · **CLI + Interactive Wizard** · **Four Report Formats**

Created by **dineth**

[Get started](#get-started) · [Choose a workflow](#choose-a-workflow) · [Tune an assessment](#tune-an-assessment) · [Review the results](#review-the-results)

</div>

---

## One engagement, connected tools

VulnForge turns individual security utilities into a coordinated assessment. Discovered hosts become service targets; responding services become crawl inputs; collected URLs feed focused checks. A shared engagement context carries the evidence between stages.

```text
  DISCOVER       IDENTIFY       EXPLORE        ASSESS        REVIEW
  ────────       ────────       ───────        ──────        ──────
  Subdomains  →  Services    →  Endpoints   →  Findings   →  Reports
  DNS            Technology    Content        Web tests     AI triage
```

Stages execute in sequence, while modules assigned to the same stage can run together. Install the utilities you need: modules with unavailable dependencies are skipped with an explanation.

<details>
<summary><strong>Explore the toolchain</strong></summary>

| Assessment task | Utilities or approach |
| :--- | :--- |
| Find subdomains | crt.sh through curl, subfinder |
| Resolve names | dnsx |
| Identify responding services | whatweb |
| Collect application routes | katana |
| Capture page previews | gowitness and a compatible browser |
| Discover directories and files | ffuf |
| Match vulnerability templates | nuclei |
| Check SQL injection | sqlmap |
| Check cross-site scripting | dalfox |
| Highlight SSRF and IDOR candidates | Local parameter inspection |
| Test blind SSRF callbacks | interactsh-client or a configured listener |
| Prioritize collected evidence | Optional OpenAI-compatible model endpoint |

Parameter inspection identifies review candidates; it does not confirm a vulnerability. Injection checks are most useful after crawling has collected URLs with query parameters.

</details>

## Get started

Prepare a Python environment, install the application dependencies, then inspect the tools available on your machine.

```bash
git clone https://github.com/Dineth-Basura/VULNFORGE.git
cd VULNFORGE

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python vulnforge.py check
```

The Python requirements do not install external scanner binaries. Use the toolchain table to choose your local installations. For automatic OAST collection, install `interactsh-client`; a callback domain in the profile provides a manual-confirmation alternative.

Launch the guided interface:

```bash
python vulnforge.py
```

Arrow-key menus use `questionary` when available. A numbered prompt interface provides a fallback.

## Choose a workflow

| Workflow | Behavior | Example |
| :--- | :--- | :--- |
| Manual | Leaves intrusive modules disabled until selected | `python vulnforge.py scan example.com` |
| Selective | Runs only the modules you name | `python vulnforge.py scan example.com --only http-probe,nuclei-scan` |
| Automatic | Makes intrusive modules eligible alongside other configured modules | `python vulnforge.py scan example.com --mode auto` |

Manual mode can also run eligible non-intrusive modules such as screenshots and configured AI triage. Enable an individual intrusive module with `--enable`:

```bash
python vulnforge.py scan example.com --enable content-discovery
```

Inspect command options and module readiness:

```bash
python vulnforge.py --help
python vulnforge.py scan --help
python vulnforge.py modules
```

## Tune an assessment

Start with `profiles/default.yaml`. Supply another file using `--profile`; put module-specific settings under `modules:` with the module's name as the key.

```yaml
roe:
  scope_allow: ["example.com", "*.example.com"]
  deny_paths: ["/logout", "/*/delete*"]
  rate_limit: 100
  max_subdomains: 50

auth:
  headers: ["X-Api-Key: YOUR_KEY"]
  cookies: "session=YOUR_SESSION"
  user_agent: "VulnForge assessment"
```

Rate-aware tools receive a divided request budget with a minimum allocation of one request per second. Enforcement depends on the external binaries; this is not a shared traffic meter or guaranteed aggregate cap. URL filtering also does not form a network boundary around tool-generated traffic, crawler requests, or redirects.

### Access authenticated pages

Pass credentials for the engagement and route supported tool traffic through your proxy:

```bash
python vulnforge.py scan example.com \
  --header 'Authorization: Bearer YOUR_TOKEN' \
  --cookie 'sid=YOUR_SESSION' \
  --proxy http://127.0.0.1:8080
```

### Work through a target list

Use a text file containing one target per line. Set how many targets may run at once:

```bash
python vulnforge.py scan --list targets.txt --concurrency 3
```

### Continue an interrupted run

Point resume at the directory containing the saved checkpoint:

```bash
python vulnforge.py scan --resume runs/EXISTING_RUN_DIRECTORY/
```

### Add model-assisted review

Configure a compatible hosted or local endpoint through environment variables:

```bash
export VULNFORGE_LLM_KEY='YOUR_KEY'
export VULNFORGE_LLM_URL='http://localhost:11434/v1'
export VULNFORGE_LLM_MODEL='llama3.1'

python vulnforge.py scan example.com --enable ai-triage
```

A non-empty key is the opt-in switch, even when a local server ignores authentication. The configured endpoint receives finding details and evidence. These environment values take precedence over the profile's `llm:` block.

## Review the results

Each assessment creates a directory below `runs/`. Change that location with `--output`.

```text
runs/<target>_<timestamp>/
├── report.md          Human-readable findings
├── report.html        Browser view
├── report.json        Structured assessment data
├── report.sarif       SARIF 2.1.0 export
├── checkpoint.json    Phase completion and resume state
└── …                  Individual tool artifacts
```

SQLite history tracks newly observed, known, and resolved findings between recorded scans. The default database is `~/.local/share/vulnforge/state.db`, or the equivalent under `XDG_DATA_HOME`. Choose another database with `--db PATH`, or omit persistence with `--no-store`.

## Build on the framework

Application code lives in `vforge/`; `vulnforge.py` starts the CLI. Extend the pipeline by placing a `Module` subclass in `vforge/modules/`. Give it a name, phase, dependency list, and asynchronous `run(ctx)` method. The registry discovers it automatically.

Run the development checks:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q vforge vulnforge.py
```

**Validation status:** 45 tests passed in the latest local run. Coverage includes configuration, module parsing, report output, history, checkpoints, triage, prompts, and Dalfox v2/v3 command selection. Additional CLI checks exercised parameter auditing, report creation, history differences, and resume.

Live scanner integrations still require verification against a controlled application on a host that permits network sockets. Binary availability and automated tests alone do not establish end-to-end scanner compatibility.

---

Use VulnForge only for systems you own or have explicit authorization to assess, within the agreed engagement boundaries.
