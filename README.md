# DDEV Magento Toolkit

A comprehensive DDEV add-on that provides essential tools and configurations for Magento 2 development. This toolkit streamlines your Magento development workflow by providing pre-configured services, custom commands, and automated setup scripts.

## Features

- **n98-magerun2 Integration**: Access to the powerful Magento CLI tool via `ddev n98`
- **Deployer Support**: Run Deployer commands with `ddev dep`
- **Automated Environment Configuration**: Generate `env.php` with proper DDEV settings using `ddev generate-env`
- **Module Compatibility Report**: Generate a CSV or AI prompt for third-party Magento module upgrade planning with `ddev module-report`
- **Pre-configured Services**: 
  - Redis for session storage and caching
  - OpenSearch for catalog search
- **Automated Post-Import Hooks**: Automatically configure stores and admin users after database imports
- **Auto-start Environment Setup**: Generates `env.php` automatically on project start if missing

## Prerequisites

- [DDEV](https://ddev.readthedocs.io/) installed (minimum version 1.19.0 recommended)
- A Magento 2 project
- Basic familiarity with DDEV commands

## Installation

Install the toolkit using DDEV's `get` command:

```bash
ddev add-on get studioraz/ddev-magento-toolkit
```

This will:
1. Install the required dependencies (Redis RabbitMQ and OpenSearch)
2. Copy custom commands to your project's `.ddev/commands/web/` and `.ddev/commands/host/` directories
3. Set up configuration hooks in `.ddev/config.magento.hooks.yaml`
4. Download and install n98-magerun2 to your project's `bin/` directory
5. Make all scripts executable

After installation, restart DDEV to apply changes:

```bash
ddev restart
```

## Available Commands

### `ddev n98`

Run n98-magerun2 commands inside the web container. This is a powerful CLI tool for Magento 2 development.

**Usage:**
```bash
ddev n98 [flags] [args]
```

**Examples:**
```bash
# List all available commands
ddev n98 list

# Enable maintenance mode
ddev n98 maintenance:enable

# Disable maintenance mode
ddev n98 maintenance:disable

# Clear cache
ddev n98 cache:flush

# Reset sample data
ddev n98 sampledata:reset

# Change admin password
ddev n98 admin:user:change-password <username> <newpassword>

# List all admin users
ddev n98 admin:user:list
```

**Note:** The n98-magerun2 tool is automatically installed to `bin/n98` in your project root (or `src/bin/n98` if your project has a `src/` directory).

### `ddev dep`

Run Deployer commands inside the DDEV web container. Deployer must be installed in your project via Composer.

**Usage:**
```bash
ddev dep [args]
```

**Examples:**
```bash
# Deploy to production
ddev dep deploy production

# List available tasks
ddev dep list

# Run a specific task
ddev dep task:name
```

**Requirements:** Deployer must be installed as a Composer dependency (`vendor/bin/dep` must exist).

### `ddev generate-env`

Generate or regenerate the `app/etc/env.php` configuration file for your Magento project with proper DDEV settings.

**Usage:**
```bash
ddev generate-env [flags]
```

**Flags:**
- `--force` - Override an existing env.php file
- `--dry-run` - Simulate the generation without writing the file

**Examples:**
```bash
# Generate env.php (only if it doesn't exist)
ddev generate-env

# Force regenerate env.php
ddev generate-env --force

# Preview what would be generated
ddev generate-env --dry-run
```

**Generated Configuration:**
- Database connection to DDEV's database service
- Redis configuration for session storage and caching
- OpenSearch configuration for catalog search
- RabbitMQ configuration for message queue 
- Admin URI (customizable via `ADMIN_URI` environment variable)
- Magento mode (customizable via `MAGE_MODE` environment variable)
- Secure base URLs for your DDEV site
- Encryption key (preserved from existing env.php or generated)

### `ddev install-mageos`

Install a fresh MageOS codebase into a clean DDEV project, run the initial Magento installer, and then regenerate `env.php` with this add-on's DDEV defaults.

**Quick Start — install MageOS from scratch:**

1. Create and enter a new project directory:
   ```bash
   mkdir my-shop && cd my-shop
   ```
2. Initialise DDEV for Magento 2:
   ```bash
   ddev config --project-type=magento2 --disable-settings-management
   ```
3. Install this add-on (pulls Redis, OpenSearch, and RabbitMQ automatically):
   ```bash
   ddev add-on get studioraz/ddev-magento-toolkit
   ```
4. Start the DDEV environment:
   ```bash
   ddev start
   ```
5. Run the installer (takes ~10 minutes — DDEV restarts automatically when done):
   ```bash
   ddev install-mageos
   ```
6. Open the site in your browser:
   ```bash
   ddev launch
   ```

**Usage:**
```bash
ddev install-mageos [flags]
```

**Examples:**
```bash
# Install the latest MageOS release
ddev install-mageos

# Install a specific MageOS version and customize the storefront/admin paths
ddev install-mageos \
  --mageos-version=1.0.2 \
  --base-url=https://my-shop.ddev.site/ \
  --backend-frontname=backend
```

**Flags:**
- `--mageos-version=<version>` - Optional version passed to `composer create-project`
- `--base-url=<url>` - Storefront URL used during `setup:install` (defaults to `https://<project>.ddev.site/`)
- `--backend-frontname=<path>` - Admin URI (default: `admin`)
- `--admin-user=<username>` - Admin username (default: `studioraz`)
- `--admin-password=<password>` - Admin password (default: `qwaszx1234$`)
- `--admin-firstname=<name>` - Admin first name (default: `Studio`)
- `--admin-lastname=<name>` - Admin last name (default: `Raz`)
- `--admin-email=<email>` - Admin email (default: `admin@example.com`)
- `--language=<locale>` - Store locale (default: `en_US`)
- `--currency=<code>` - Store currency (default: `USD`)
- `--timezone=<timezone>` - Store timezone (default: `UTC`)
- `--force` - Allow installation even if the project root already contains files besides DDEV scaffolding

**Notes:**
- Run this from a clean DDEV project root after installing the add-on.
- The command scaffolds `mageos/project-community-edition` from `https://repo.mage-os.org/`.
- After `setup:install`, it runs `ddev generate-env --force` so Redis, RabbitMQ, and OpenSearch are wired up with this toolkit's defaults.

### `ddev module-report`

Generate a report of third-party Magento modules, including installed version, latest available version, latest released version, and minimum compatible version for a target Magento upgrade.

**Usage:**
```bash
ddev module-report [flags]
```

**Examples:**
```bash
# Default report
ddev module-report

# Target a specific Magento version
ddev module-report --target-magento=2.4.8-p3 --output=var/upgrade-2.4.8.csv

# Include child dependency modules
ddev module-report --include-children

# Generate AI prompt output instead of CSV
ddev module-report --format=ai-prompt --output=var/module-report.txt
```

**Notes:**
- The command is self-contained in the add-on and runs the Python script copied to `.ddev/scripts/magento-toolkit/module-report/module-report.py`.
- It scans the consumer Magento project root automatically via `DDEV_APPROOT` and project files like `composer.json` and `app/etc/config.php`.
- Output defaults to `var/module-report.csv`.

## Configuration

### Hooks

The toolkit installs hooks in `.ddev/config.magento.hooks.yaml` that automate common tasks:

```yaml
hooks:
  post-import-db:
    - exec: bin/magento config:data:import config/store dev
    - exec: bin/n98 admin:user:change-password studioraz qwaszx1234$
  post-start:
    - exec-host: '[ -f app/etc/env.php ] || ddev generate-env'
```

**post-import-db hooks:**
- Imports store configuration from `config/store` directory (requires Magento config data import)
- Sets admin password for user `studioraz` to `qwaszx1234$` ⚠️ **(local development only - see security note below)**

**post-start hooks:**
- Automatically generates `env.php` if it doesn't exist when starting DDEV

### Customization Options

You can customize the environment generation by setting environment variables in your `.ddev/config.yaml`:

```yaml
web_environment:
  - ADMIN_URI=admin
  - MAGE_MODE=developer
```

Available environment variables:
- `ADMIN_URI` - Admin panel URI (default: `admin`)
- `MAGE_MODE` - Magento mode: `developer`, `production`, or `default` (default: `developer`)

### Security Note

⚠️ **IMPORTANT SECURITY WARNING** ⚠️

The default admin password set by the post-import-db hook is `qwaszx1234$` for user `studioraz`. 

**This is a hardcoded credential intended ONLY for local development environments.**

**You MUST:**
1. **Never use these credentials in production or staging environments**
2. **Change this password immediately after import**, or
3. **Modify the hook** in `.ddev/config.magento.hooks.yaml` to use your preferred credentials

To customize the admin user and password, edit `.ddev/config.magento.hooks.yaml`:

```yaml
hooks:
  post-import-db:
    - exec: bin/magento config:data:import config/store dev
    - exec: bin/n98 admin:user:change-password <your-username> <your-secure-password>
```

**Recommended:** Use strong, unique passwords and avoid storing credentials in version control.

## Usage Examples

### Setting Up a New Magento Project

```bash
# Install the toolkit
ddev add-on get studioraz/ddev-magento-toolkit

# Start DDEV (env.php will be auto-generated)
ddev start

# Import a database
ddev import-db --src=database.sql.gz

# Access the admin panel
# URL: https://your-project.ddev.site/admin
# Default User: studioraz
# Default Password: qwaszx1234$ (⚠️ CHANGE IMMEDIATELY - for local dev only!)
```

### Creating a Brand-New MageOS Project

```bash
# 1. Create and enter the project directory
mkdir my-shop && cd my-shop

# 2. Initialise DDEV for Magento 2
ddev config --project-type=magento2 --disable-settings-management

# 3. Install this add-on (auto-installs Redis, OpenSearch, RabbitMQ)
ddev add-on get studioraz/ddev-magento-toolkit

# 4. Start the environment
ddev start

# 5. Scaffold MageOS and run the Magento installer (~10 min)
ddev install-mageos

# 6. Open the site (DDEV restarts automatically before this)
ddev launch
```

### Working with an Existing Project

```bash
# Install the toolkit
ddev add-on get studioraz/ddev-magento-toolkit

# Regenerate env.php with DDEV settings
ddev generate-env --force

# Clear cache and reindex
ddev magento cache:flush
ddev magento indexer:reindex

# Access your site
ddev launch
```

### Daily Development Workflow

```bash
# Clear cache
ddev n98 cache:flush

# Enable/disable maintenance mode
ddev n98 maintenance:enable
ddev n98 maintenance:disable

# Check configuration
ddev n98 config:list

# Manage admin users
ddev n98 admin:user:list
ddev n98 admin:user:change-password username newpassword

# Deploy code (if using Deployer)
ddev dep deploy staging
```

## Dependencies

This toolkit automatically installs the following DDEV add-ons:

- **[ddev-redis](https://github.com/ddev/ddev-redis)**: Redis service for session storage and caching
- **[ddev-opensearch](https://github.com/ddev/ddev-opensearch)**: OpenSearch service for Magento catalog search
- **[ddev-rabbitmq](https://github.com/ddev/ddev-rabbitmq)**: RabbitMQ service for Magento message queue

These services are configured automatically in the generated `env.php` file.

## Project Structure

After installation, the toolkit adds the following files to your `.ddev` directory:

```
.ddev/
├── commands/
│   ├── host/
│   │   └── install-mageos          # Fresh MageOS installer
│   └── web/
│       ├── dep                     # Deployer command
│       ├── n98                     # n98-magerun2 command
│       ├── generate-env            # Environment generator command
│       └── module-report           # Module compatibility report command
├── scripts/
│   └── magento-toolkit/
│       ├── module-report/
│       │   └── module-report.py     # Shared module report generator
│       └── uninstall.sh             # Cleanup script
└── config.magento.hooks.yaml        # Post-import and post-start hooks
```

The n98-magerun2 tool is downloaded automatically on first `ddev n98` invocation to:
- `bin/n98` (standard Magento structure)
- `src/bin/n98` (if your project has a `src/` directory)

## Troubleshooting

### n98 command fails

**Error:** `n98 not found. Installing n98-magerun2 …` hangs or fails

**Solution:**
```bash
# Retry – n98 is downloaded automatically on first use
ddev n98 list
```

### dep command fails

**Error:** `deployer does not exist`

**Solution:** Install Deployer via Composer:
```bash
ddev composer require deployer/deployer --dev
```

### env.php generation fails

**Error:** `DDEV_PROJECT and DDEV_APPROOT must be set`

**Solution:** The `generate-env` command must be run from within DDEV:
```bash
# Don't run: generate-env (on host)
# Do run: ddev generate-env (via DDEV)
```

### Redis or OpenSearch not available

**Error:** Connection errors to Redis or OpenSearch services

**Solution:**
1. Verify the services are installed:
   ```bash
   ddev describe
   ```
2. If missing, reinstall the toolkit:
   ```bash
   ddev add-on get studioraz/ddev-magento-toolkit
   ddev restart
   ```

### Admin password not set after database import

**Solution:** Manually set the admin password:
```bash
ddev n98 admin:user:change-password your-username your-password
```

Or create a new admin user:
```bash
ddev magento admin:user:create \
  --admin-user=admin \
  --admin-password=YourPassword123 Let me know if there is anything else I can help you with.


  --admin-email=admin@example.com \
  --admin-firstname=Admin \
  --admin-lastname=User
```

### Cache issues after configuration changes

**Solution:** Clear all caches:
```bash
ddev n98 cache:flush
ddev magento setup:upgrade
ddev magento setup:di:compile
ddev magento setup:static-content:deploy -f
```

## Upgrading

To upgrade to the latest version of the toolkit:

```bash
ddev add-on get studioraz/ddev-magento-toolkit
ddev restart
```

Files marked with `#ddev-generated` will be automatically updated. If you've customized any toolkit files, remove the `#ddev-generated` line to prevent them from being overwritten.

## Removing the Toolkit

To remove the toolkit:

```bash
ddev add-on remove studioraz/ddev-magento-toolkit
```

This will:
1. Remove n98-magerun2 from your project
2. Delete all toolkit files marked with `#ddev-generated`
3. Keep your customized files (those without `#ddev-generated`)

**Note:** This will not remove the Redis and OpenSearch services. To remove them:

```bash
ddev add-on remove ddev/ddev-redis
ddev add-on remove ddev/ddev-opensearch
ddev add-on remove ddev/ddev-rabbitmq
```

## Contributing

Contributions are welcome! Here's how you can help:

### Reporting Issues

If you encounter any problems:
1. Check the [Troubleshooting](#troubleshooting) section
2. Search existing [issues](https://github.com/studioraz/ddev-magento-toolkit/issues)
3. Open a new issue with:
   - Clear description of the problem
   - Steps to reproduce
   - DDEV version (`ddev version`)
   - Magento version
   - Error messages or logs

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Test thoroughly with a Magento project
5. Ensure all scripts are marked with `#ddev-generated` if they should be auto-updated
6. Commit with clear messages: `git commit -m "Add: description of changes"`
7. Push to your fork: `git push origin feature/your-feature-name`
8. Open a Pull Request

### Running the Test Suite

The addon ships with a [Bats](https://bats-core.readthedocs.io/) (Bash Automated Testing System) test suite located in `tests/test.bats`.

**Prerequisites:**

```bash
# Install bats-core
brew install bats-core

# Clone the required helper libraries
mkdir -p /tmp/bats-libs
git clone https://github.com/bats-core/bats-support /tmp/bats-libs/bats-support
git clone https://github.com/bats-core/bats-assert  /tmp/bats-libs/bats-assert
```

**Run the tests:**

```bash
BATS_LIB_PATH=/tmp/bats-libs bats ./tests/test.bats --filter-tags '!release' --timing
```

The `--filter-tags '!release'` flag skips the release-install test (which requires a published GitHub tag) so the full suite can run against your local working copy.

**What the tests cover:**
- Addon file deployment from a local directory
- n98-magerun2 lazy installation on first `ddev n98` invocation
- n98-magerun2 not re-downloaded on subsequent invocations
- `ddev generate-env --dry-run` output
- `ddev generate-env` writes `app/etc/env.php`
- `ddev generate-env` does not overwrite an existing file without `--force`
- `ddev generate-env --force` overwrites an existing file

### Development Guidelines

- Keep commands simple and focused
- Include usage examples in command headers
- Mark generated files with `#ddev-generated`
- Test with multiple Magento versions when possible
- Update this README if adding new features
- Follow existing code style and conventions

## License

This project is open-source and available under the MIT License.

## Support

- **Issues:** [GitHub Issues](https://github.com/studioraz/ddev-magento-toolkit/issues)
- **DDEV Documentation:** [ddev.readthedocs.io](https://ddev.readthedocs.io/)
- **Magento Documentation:** [devdocs.magento.com](https://devdocs.magento.com/)

## Related Resources

- [DDEV Documentation](https://ddev.readthedocs.io/)
- [n98-magerun2 Documentation](https://github.com/netz98/n98-magerun2)
- [Deployer Documentation](https://deployer.org/)
- [Magento 2 Developer Documentation](https://devdocs.magento.com/)
- [DDEV Add-on Development](https://ddev.readthedocs.io/en/stable/users/extend/additional-services/)

## Acknowledgments

- Built for the [DDEV](https://ddev.com/) local development environment
- Integrates [n98-magerun2](https://github.com/netz98/n98-magerun2) by netz98
- Supports [Deployer](https://deployer.org/) deployment tool
- Designed for [Magento 2](https://magento.com/) e-commerce platform
