# AGENTS.md – ddev-magento-toolkit

## What This Repo Is
A **DDEV add-on** (not a standalone app). It installs into a consumer Magento 2 project's `.ddev/` directory via:
```bash
ddev add-on get studioraz/ddev-magento-toolkit
```
All files in `project_files` (see `install.yaml`) are copied into the target project's `.ddev/` folder on install/update.

---

## Key Files
| File | Purpose |
|------|---------|
| `install.yaml` | DDEV add-on manifest – declares `project_files`, `dependencies`, `post_install_actions`, `removal_actions` |
| `config.magento.hooks.yaml` | DDEV lifecycle hooks (`post-import-db`, `post-start`) copied to target project |
| `commands/web/generate-env` | Bash script that writes `app/etc/env.php` from inside the DDEV web container |
| `commands/web/n98` | Lazy-installs `n98-magerun2.phar` on first use, then runs `php <bindir>/n98 "$@"` inside the container |
| `commands/web/dep` | Thin wrapper: runs `php ~/.composer/vendor/bin/dep "$@"` (global Composer install, not `vendor/bin/`) |
| `commands/web/module-report` | Wrapper that runs the shared Python compatibility report shipped by this add-on |
| `scripts/magento-toolkit/module-report/module-report.py` | Shared Magento module compatibility report generator copied into each project's `.ddev/scripts/` |

---

## The `#ddev-generated` Convention
- **Every file managed by this add-on must contain `#ddev-generated`** in its first few lines.
- DDEV uses this marker to identify and overwrite the file on `ddev add-on get` upgrades.
- **Removing the line from a file means DDEV will never overwrite it** – this is the intended way to "own" a file in the consumer project.
- New scripts/commands added to this repo must include `#ddev-generated` (or `## #ddev-generated:` for bash header comments).

---

## Architecture: How `generate-env` Works
- Runs **inside** the DDEV web container (requires `DDEV_PROJECT` and `DDEV_APPROOT` env vars).
- Uses a bash heredoc with `${PLACEHOLDER}` literals, then substitutes them via **pure bash string replacement** (`${var//pattern/replacement}`) – deliberately avoids `envsubst` or `sed` to prevent unintended env var expansion.
- Cache `id_prefix` is deterministic per project (first 3 chars of `md5($DDEV_PROJECT)`).
- OpenSearch hostname follows DDEV's internal naming: `ddev-${DDEV_PROJECT}-opensearch` (not simply `opensearch`).
- Controlled by two optional env vars in `.ddev/config.yaml`: `ADMIN_URI` (default `admin`) and `MAGE_MODE` (default `developer`).

---

## Add-on Dependencies (auto-installed)
- `ddev/ddev-redis` – session (db 2) + default cache (db 0) + page_cache (db 1)
- `ddev/ddev-opensearch` – catalog search engine
- `ddev/ddev-rabbitmq` – message queue (AMQP)

---

## n98 Install Path Logic
`commands/web/n98` lazy-installs n98 on first invocation:
- If `$DDEV_APPROOT/src` exists → installs to `src/bin/n98`
- Otherwise → installs to `bin/n98`

---

## Hardcoded Dev Credentials
`config.magento.hooks.yaml` sets admin password `qwaszx1234$` for user `studioraz` on every `post-import-db`. This is **intentional for local dev only** and documented as such. Do not change to "fix" a security issue – instead document that consumers should override it.

---

## Adding a New Command
1. Create `commands/web/<command-name>` as a bash script with DDEV header comments:
   ```bash
   ## #ddev-generated: If you want to edit and own this file, remove this line.
   ## Description: …
   ## Usage: <command-name> [args]
   ```
2. Register it in `install.yaml` under `project_files`.
3. If the command depends on helper scripts or templates, place them under `scripts/magento-toolkit/...` and add those paths to `project_files` too.
4. No build step needed – files are consumed directly after `ddev add-on get`.

---

## Testing Changes
There is no automated test suite. Validate manually:
```bash
ddev add-on get studioraz/ddev-magento-toolkit   # install/upgrade
ddev generate-env --dry-run                       # preview env.php
ddev n98 list                                     # verify n98 works
ddev module-report --no-api                       # verify bundled report command
scripts/check-for-updates.sh                      # compare installed vs latest tag
```
