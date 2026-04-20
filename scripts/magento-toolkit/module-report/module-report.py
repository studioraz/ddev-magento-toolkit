#!/usr/bin/env python3
#ddev-generated
"""
Magento 2 Third-Party Module Compatibility Report Generator
Generates a CSV of all active 3rd-party modules with current, latest, and
compatible versions for a target Magento/PHP upgrade.

Usage (inside ddev web container via `ddev module-report`):
    python3 .ddev/scripts/magento-toolkit/module-report/module-report.py [options]

Options:
    --target-magento=2.4.8-p3   Target Magento version (default: 2.4.8-p3)
    --target-php=8.3             Target PHP version (default: 8.3)
    --output=report.csv          Output CSV file (default: module-report.csv)
    --format=csv|ai-prompt       Output format (default: csv)
    --no-api                     Skip all remote API calls (offline mode)
    --include-children           Include child/dep modules (default: parents only)
    --verbose                    Print progress details
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Magento framework version → Magento product version mapping (approximate)
# magento/framework patch version in composer.lock corresponds to Magento version
FRAMEWORK_TO_MAGENTO = {
    "103.0.7":  "2.4.7",
    "103.0.7-p1": "2.4.7-p1",
    "103.0.7-p2": "2.4.7-p2",
    "103.0.7-p3": "2.4.7-p3",
    "103.0.7-p4": "2.4.7-p4",
    "103.0.7-p5": "2.4.7-p5",
    "103.0.7-p6": "2.4.7-p6",
    "103.0.7-p7": "2.4.7-p7",
    "103.0.7-p8": "2.4.7-p8",
    "103.0.8":    "2.4.8",
    "103.0.8-p1": "2.4.8-p1",
    "103.0.8-p2": "2.4.8-p2",
    "103.0.8-p3": "2.4.8-p3",
}

# Reverse map: Magento version → expected framework minor version range
MAGENTO_FRAMEWORK_MINOR = {
    "2.4.7": "103.0.7",
    "2.4.8": "103.0.8",
}

# Packages to skip entirely (non-Magento ecosystem)
SKIP_PREFIXES = [
    "magento/", "php", "ext-", "laminas/", "symfony/", "composer/",
    "guzzlehttp/", "monolog/", "league/", "psr/", "wikimedia/", "twig/",
    "colinmollenhour/", "web-token/", "spomky-labs/", "paragonie/",
    "firebase/", "brick/", "phpseclib/", "bacon/", "christian-riesen/",
    "dasprid/", "endroid/", "twilio/", "aws/", "elasticsearch/",
    "open-telemetry/", "opentelemetry/", "nikic/", "pelago/", "ezyang/",
    "jdorn/", "knplabs/", "mpdf/", "phpoffice/", "tecnickcom/",
    "ryangjchandler/", "phpstan/", "doctrine/", "webmozart/",
    "seld/", "justinrainbow/", "ralouphie/", "dflydev/", "fig/",
    "tubalmartin/", "magento-hackathon/", "phpmd/", "squizlabs/",
]

AMASTY_FEED_URL = "https://feed.amasty.net/feed-extensions-m2.xml"
MIRASVIT_FEED_URL = "https://files.mirasvit.com/feed/package-list.json"
MAGEFAN_FEED_URL = "https://magefan.com/media/product-versions-extended.json"
MAGEWORX_FEED_URL = "https://www.mageworx.com/extensions_list.js"
PACKAGIST_API = "https://packagist.org/packages/{}.json"

# Hyva-compat name patterns
HYVA_COMPAT_PATTERNS = ["-hyva", "hyva-"]

# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate Magento 2 3rd-party module compatibility report"
    )
    parser.add_argument("--target-magento", default="2.4.8-p3",
                        help="Target Magento version (default: 2.4.8-p3)")
    parser.add_argument("--target-php", default="8.3",
                        help="Target PHP version (default: 8.3)")
    parser.add_argument("--output", default="var/module-report.csv",
                        help="Output file path (default: var/module-report.csv)")
    parser.add_argument("--format", choices=["csv", "ai-prompt"], default="csv",
                        help="Output format (default: csv)")
    parser.add_argument("--no-api", action="store_true",
                        help="Skip all remote API calls (offline mode)")
    parser.add_argument("--include-children", action="store_true",
                        help="Include child/dep modules in the report (default: parents only)")
    parser.add_argument("--include-child-pricing", action="store_true",
                        help="Show Price column for child/dep modules too (default: parent only)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print progress details")
    return parser.parse_args()

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

_verbose = False

def log(msg):
    if _verbose:
        print(f"  {msg}", file=sys.stderr)

def info(msg):
    print(f"[INFO] {msg}", file=sys.stderr)

def warn(msg):
    print(f"[WARN] {msg}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Step 1: Data collection
# ---------------------------------------------------------------------------

def find_project_root():
    """Find Magento project root (where composer.json lives)."""
    candidates = []

    ddev_approot = os.environ.get("DDEV_APPROOT")
    if ddev_approot:
        candidates.append(Path(ddev_approot))

    candidates.append(Path.cwd())

    script_path = Path(__file__).resolve()
    candidates.extend(script_path.parents)

    seen = set()
    for c in candidates:
        c = c.resolve()
        if c in seen:
            continue
        seen.add(c)
        if (c / "composer.json").exists() and (c / "app" / "etc" / "config.php").exists():
            return c
    raise RuntimeError("Cannot find Magento project root. Run from project directory.")


def load_composer_json(root):
    with open(root / "composer.json") as f:
        return json.load(f)


def load_composer_lock(root):
    with open(root / "composer.lock") as f:
        return json.load(f)


def load_config_php(root):
    """Parse app/etc/config.php and return {ModuleName: 0|1}."""
    config_file = root / "app" / "etc" / "config.php"
    if not config_file.exists():
        warn("app/etc/config.php not found — cannot determine enabled/disabled status.")
        return {}
    content = config_file.read_text(errors="ignore")
    # Extract all 'Module_Name' => 0|1 pairs
    pattern = re.compile(r"'([A-Z][A-Za-z0-9]+_[A-Z][A-Za-z0-9]+)'\s*=>\s*([01])")
    return {m.group(1): int(m.group(2)) for m in pattern.finditer(content)}


def is_third_party(package_name):
    """Return True if this composer package is a 3rd-party Magento module."""
    return "/" in package_name and not any(
        package_name.startswith(p) for p in SKIP_PREFIXES
    )


def scan_vendor_modules(root, third_party_packages):
    """
    For each 3rd-party composer package, find which Magento module names it registers
    by scanning vendor/{vendor}/{pkg}/registration.php files.

    Returns: {composer_pkg: [MagentoModuleName, ...]}
    """
    pkg_to_modules = defaultdict(list)
    vendor_dir = root / "vendor"

    for pkg_name in third_party_packages:
        parts = pkg_name.split("/")
        if len(parts) != 2:
            continue
        vendor, package = parts
        reg_file = vendor_dir / vendor / package / "registration.php"
        if not reg_file.exists():
            # Try nested: some packages register from subdirs
            for f in (vendor_dir / vendor / package).rglob("registration.php"):
                _extract_module_names(f, pkg_to_modules[pkg_name])
            continue
        _extract_module_names(reg_file, pkg_to_modules[pkg_name])
        # Also check subdirectory registration files (multi-module packages)
        for f in (vendor_dir / vendor / package).rglob("registration.php"):
            if f != reg_file:
                _extract_module_names(f, pkg_to_modules[pkg_name])

    return dict(pkg_to_modules)


def _extract_module_names(reg_file, module_list):
    try:
        content = reg_file.read_text(errors="ignore")
        modules = re.findall(
            r"ComponentRegistrar::MODULE,\s*'([^']+)'", content
        )
        for m in modules:
            if m not in module_list:
                module_list.append(m)
    except OSError:
        pass


def get_installed_versions(lock_data):
    """Return {composer_pkg_name: installed_version} from composer.lock."""
    result = {}
    for pkg in lock_data.get("packages", []):
        result[pkg["name"]] = pkg.get("version", "unknown")
    return result


def get_package_source_url(lock_data, pkg_name):
    """Return source/dist URL for a package from composer.lock."""
    for pkg in lock_data.get("packages", []):
        if pkg["name"] == pkg_name:
            source = pkg.get("source", {})
            dist = pkg.get("dist", {})
            return source.get("url") or dist.get("url") or ""
    return ""


def get_package_deps(lock_data, pkg_name):
    """Return the require dict for a package from composer.lock."""
    for pkg in lock_data.get("packages", []):
        if pkg["name"] == pkg_name:
            return pkg.get("require", {})
    return {}


# ---------------------------------------------------------------------------
# Step 2: Parent/child classification
# ---------------------------------------------------------------------------

def classify_packages(third_party_packages, pkg_to_modules, lock_data):
    """
    Determine parent/child relationships.

    Returns: {
        composer_pkg: {
            "role": "parent" | "child-same-pkg" | "child-dep" | "child-hyva",
            "parent": composer_pkg_name | None,
            "magento_modules": [list],
            "primary_module": str,  # the "main" Magento module for this package
        }
    }
    """
    pkg_set = set(third_party_packages)
    classifications = {}

    # Build reverse map: which pkg A requires pkg B (among 3rd-party only)
    required_by = defaultdict(list)  # B -> [A, ...]
    for pkg_name in third_party_packages:
        deps = get_package_deps(lock_data, pkg_name)
        for dep_name in deps:
            if dep_name in pkg_set:
                required_by[dep_name].append(pkg_name)

    for pkg_name in third_party_packages:
        modules = pkg_to_modules.get(pkg_name, [])
        primary = _pick_primary_module(pkg_name, modules)

        is_hyva = any(p in pkg_name for p in HYVA_COMPAT_PATTERNS)
        parents_of_this = required_by.get(pkg_name, [])

        # A package is a "child-hyva" if it has hyva in its name AND it's required by something
        # A package is a "child-dep" if it's required by another 3rd-party package
        # A package is a "parent" if not required by anything (or only required by itself)
        if is_hyva and parents_of_this:
            # Find the non-hyva parent that requires this
            non_hyva_parents = [p for p in parents_of_this if not any(h in p for h in HYVA_COMPAT_PATTERNS)]
            if non_hyva_parents:
                classifications[pkg_name] = {
                    "role": "child-hyva",
                    "parent": non_hyva_parents[0],
                    "magento_modules": modules,
                    "primary_module": primary,
                }
                continue

        if parents_of_this:
            # If every package requiring this one is a hyva compat layer, this package is
            # still a parent (the hyva layer is its child, not the other way around).
            non_hyva_parents = [p for p in parents_of_this if not any(h in p for h in HYVA_COMPAT_PATTERNS)]
            if not non_hyva_parents:
                classifications[pkg_name] = {
                    "role": "parent",
                    "parent": None,
                    "magento_modules": modules,
                    "primary_module": primary,
                }
                continue

            # Pick the most "direct" parent (prefer one that explicitly requires this pkg)
            # Exclude metapackages from being "the parent" if possible
            direct_parents = [p for p in non_hyva_parents if "metapackage" not in p]
            parent = direct_parents[0] if direct_parents else non_hyva_parents[0]
            classifications[pkg_name] = {
                "role": "child-dep",
                "parent": parent,
                "magento_modules": modules,
                "primary_module": primary,
            }
        else:
            classifications[pkg_name] = {
                "role": "parent",
                "parent": None,
                "magento_modules": modules,
                "primary_module": primary,
            }

    # Same-package children: packages with multiple Magento modules
    # The non-primary modules within the same package are "same-pkg children"
    # (we don't add extra rows for them, but we mark them in the module list)
    for pkg_name, info in classifications.items():
        modules = info["magento_modules"]
        primary = info["primary_module"]
        if len(modules) > 1:
            info["child_modules"] = [m for m in modules if m != primary]
        else:
            info["child_modules"] = []

    return classifications


def _pick_primary_module(pkg_name, modules):
    """
    Given a composer package name and its registered Magento modules,
    pick the most representative / 'primary' module name.
    Heuristic: find the module whose normalized name best matches the
    package-name keyword (without vendor and 'module-' prefix).
    Prefer shorter/simpler matches.
    """
    if not modules:
        return ""
    if len(modules) == 1:
        return modules[0]

    # Extract keyword from package name: strip vendor and 'module-'
    # e.g. mirasvit/module-gdpr → "gdpr"
    pkg_keyword = re.sub(r".*/(?:module-)?", "", pkg_name).lower()
    pkg_keyword = re.sub(r"[^a-z0-9]", "", pkg_keyword)

    scored = []
    for mod in modules:
        # Normalize module name: Mirasvit_GdprCookie → gdprcookie
        mod_lower = re.sub(r"[^a-z0-9]", "", mod.lower())
        # Remove vendor prefix (first word before underscore, lowercased)
        if "_" in mod:
            mod_key = re.sub(r"[^a-z0-9]", "", mod.split("_", 1)[1].lower())
        else:
            mod_key = mod_lower

        # Score: does mod_key start with the pkg_keyword? (strongest signal)
        if mod_key == pkg_keyword:
            score = 1000  # exact match
        elif mod_key.startswith(pkg_keyword):
            score = 500 - len(mod_key)  # starts with keyword, prefer shorter
        elif pkg_keyword in mod_key:
            score = 200 - len(mod_key)  # contains keyword
        else:
            # Fallback: count common chars
            score = sum(1 for c in mod_key if c in pkg_keyword) - len(mod_key) * 0.1

        scored.append((score, mod))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


# ---------------------------------------------------------------------------
# Step 3: Version lookup
# ---------------------------------------------------------------------------

def http_get(url, timeout=15):
    """Simple HTTP GET, returns (body_str, status_code)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Magento-Module-Reporter/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace"), resp.status
    except urllib.error.HTTPError as e:
        return "", e.code
    except Exception as e:
        warn(f"HTTP error fetching {url}: {e}")
        return "", 0


def fetch_amasty_feed():
    """
    Fetch Amasty's public extension feed XML.
    Returns: {module_code: {"version": "x.y.z", "url": "...", "name": "..."}}
    """
    info("Fetching Amasty extension feed...")
    body, status = http_get(AMASTY_FEED_URL)
    if not body:
        warn(f"Could not fetch Amasty feed (status {status})")
        return {}

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        warn(f"Failed to parse Amasty feed XML: {e}")
        return {}

    result = {}
    channel = root.find("channel")
    if channel is None:
        return {}

    for item in channel.findall("item"):
        code = (item.findtext("code") or "").strip()
        version = (item.findtext("version") or "").strip()
        url = (item.findtext("link") or "").strip()
        name = (item.findtext("title") or "").strip()
        price = (item.findtext("price") or "").strip()
        release_date = (item.findtext("date") or "").strip()
        if code and version and code not in result:
            result[code] = {
                "version": version,
                "url": url,
                "name": name,
                "price": price,
                "release_date": release_date,
            }

    log(f"Amasty feed: {len(result)} modules found")
    return result


def fetch_mirasvit_feed():
    """
    Fetch Mirasvit package feed JSON.
    Returns: {composer_package: {version, url, title, sku, docs_url, changelog_url}}
    """
    info("Fetching Mirasvit package feed...")
    body, status = http_get(MIRASVIT_FEED_URL)
    if not body or status != 200:
        warn(f"Could not fetch Mirasvit feed (status {status})")
        return {}

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        warn(f"Failed to parse Mirasvit feed JSON: {e}")
        return {}

    result = {}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            pkg = (item.get("package") or "").strip()
            if not pkg:
                continue
            result[pkg] = {
                "version": (item.get("version") or "").strip(),
                "url": (item.get("url") or "").strip(),
                "title": (item.get("title") or "").strip(),
                "sku": (item.get("sku") or "").strip(),
                "docs_url": (item.get("docs_url") or "").strip(),
                "changelog_url": (item.get("changelog_url") or "").strip(),
            }

    log(f"Mirasvit feed: {len(result)} packages found")
    return result


def fetch_magefan_feed():
    """
    Fetch Magefan product versions feed JSON.
    Returns: {composer_package_name: {version, product_url, product_name, change_log_url, documentation_url}}
    """
    info("Fetching Magefan product feed...")
    body, status = http_get(MAGEFAN_FEED_URL)
    if not body or status != 200:
        warn(f"Could not fetch Magefan feed (status {status})")
        return {}
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        warn(f"Failed to parse Magefan feed JSON: {e}")
        return {}

    result = {}
    if isinstance(data, dict):
        for _, item in data.items():
            if not isinstance(item, dict):
                continue
            pkg = (item.get("composer_package_name") or "").strip()
            if not pkg:
                continue
            result[pkg] = {
                "version": (item.get("version") or "").strip(),
                "url": (item.get("product_url") or "").strip(),
                "title": (item.get("product_name") or "").strip(),
                "changelog_url": (item.get("change_log_url") or "").strip(),
                "docs_url": (item.get("documentation_url") or "").strip(),
            }

    log(f"Magefan feed: {len(result)} packages found")
    return result


def fetch_mageworx_feed():
    """
    Fetch MageWorx extensions feed JSON.
    Returns: {composer_package: {version, url, title, price, user_guide, marketplace_link}}
    """
    info("Fetching MageWorx extensions feed...")
    body, status = http_get(MAGEWORX_FEED_URL)
    if not body or status != 200:
        warn(f"Could not fetch MageWorx feed (status {status})")
        return {}
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        warn(f"Failed to parse MageWorx feed JSON: {e}")
        return {}

    exts = data.get("extensions") if isinstance(data, dict) else None
    if not isinstance(exts, dict):
        return {}

    result = {}
    for pkg, item in exts.items():
        if not isinstance(item, dict):
            continue
        result[pkg] = {
            "version": (item.get("version") or "").strip(),
            "url": (item.get("url") or "").strip(),
            "title": (item.get("title") or "").strip(),
            "price": item.get("price", ""),
            "user_guide": (item.get("user_guide") or "").strip(),
            "marketplace_link": (item.get("marketplace_link") or "").strip(),
        }

    log(f"MageWorx feed: {len(result)} packages found")
    return result


def extract_repo_credentials(comp_json, root=None):
    """
    Parse composer.json repositories + auth.json for all repo URLs and credentials.
    Returns list of {url, user, password} dicts.
    """
    # Load auth.json if available
    auth_creds = {}  # hostname → {username, password}
    auth_path = (root / "auth.json") if root else Path("auth.json")
    if auth_path.exists():
        try:
            with open(auth_path) as f:
                auth_data = json.load(f)
            for host, cred in auth_data.get("http-basic", {}).items():
                auth_creds[host] = {
                    "user": cred.get("username", ""),
                    "password": cred.get("password", ""),
                }
        except (json.JSONDecodeError, OSError):
            pass

    repos = []
    for repo in comp_json.get("repositories", []):
        if not isinstance(repo, dict):
            continue
        if repo.get("type") != "composer":
            continue
        raw_url = repo.get("url", "")
        if not raw_url:
            continue

        # Check if credentials are embedded in the URL
        m = re.match(r"(https?://)([^:@]+):([^@]+)@(.+)", raw_url)
        if m:
            repos.append({
                "user": m.group(2),
                "password": m.group(3),
                "url": m.group(1) + m.group(4).rstrip("/"),
            })
            continue

        # No embedded credentials — look up from auth.json by hostname
        clean_url = raw_url.rstrip("/")
        host_m = re.match(r"https?://([^/]+)", clean_url)
        host = host_m.group(1) if host_m else ""

        # Try full host match, then subdomain-stripped match
        cred = auth_creds.get(host) or auth_creds.get(host.split(".", 1)[-1] if "." in host else host)

        repos.append({
            "user": cred["user"] if cred else None,
            "password": cred["password"] if cred else None,
            "url": clean_url,
        })

    return repos


def find_package_repo(lock_data, pkg_name, repos):
    """
    Determine which composer repo a package comes from by matching
    its dist URL against known repo URLs.
    Returns the matching repo dict or None.
    """
    dist_url = get_package_source_url(lock_data, pkg_name)
    if not dist_url:
        return None

    best_match = None
    best_len = 0
    for repo in repos:
        repo_base = re.sub(r"^https?://", "", repo["url"].rstrip("/"))
        dist_clean = re.sub(r"^https?://[^@]+@", "", dist_url)  # strip creds from dist url
        if repo_base in dist_clean and len(repo_base) > best_len:
            best_match = repo
            best_len = len(repo_base)
    return best_match


def fetch_repo_versions(pkg_name, repo, lock_data):
    """
    Query a private Composer repository for available versions of a package.
    Handles both p2/{package}.json format and legacy includes-based repos (Mirasvit).
    Returns: list of {version, require} dicts (stable, newest first)
    """
    base_url = repo["url"].rstrip("/")
    user = repo.get("user")
    password = repo.get("password")

    vendor, package = pkg_name.split("/", 1)

    # Try Composer v2 p2 endpoints first (modern repos like packagist.com)
    for endpoint in [
        f"{base_url}/p2/{vendor}/{package}.json",
        f"{base_url}/p/{vendor}/{package}.json",
    ]:
        body, status = http_get_auth(endpoint, user, password)
        if body and status == 200:
            versions = _parse_composer_p2_response(body, pkg_name)
            if versions:
                return versions

    # Fall back to packages.json + includes pattern (Mirasvit-style repos)
    body, status = http_get_auth(f"{base_url}/packages.json", user, password)
    if not body or status != 200:
        return []

    try:
        root_data = json.loads(body)
    except json.JSONDecodeError:
        return []

    # Check if package is directly listed
    if pkg_name in root_data.get("packages", {}):
        return _parse_legacy_versions(root_data["packages"][pkg_name])

    # Follow includes links
    includes = root_data.get("includes", {})
    for include_path in includes.keys():
        # Normalize path (may have leading slash or not)
        inc_path = include_path.lstrip("/")
        inc_url = f"{base_url}/{inc_path}"
        inc_body, inc_status = http_get_auth(inc_url, user, password)
        if not inc_body or inc_status != 200:
            continue
        try:
            inc_data = json.loads(inc_body)
        except json.JSONDecodeError:
            continue
        if pkg_name in inc_data.get("packages", {}):
            return _parse_legacy_versions(inc_data["packages"][pkg_name])

    return []


def _parse_legacy_versions(version_map):
    """
    Parse legacy Composer v1 packages.json version map:
    {"1.0.0": {require: {...}}, "1.0.1": {...}}
    Returns: list of {version, require} dicts, stable only, newest first.
    """
    result = []
    seen = set()
    for ver_key, ver_info in version_map.items():
        if ver_key in seen:
            continue
        seen.add(ver_key)
        if ver_key.startswith("dev-") or "dev" in ver_key.lower():
            continue
        ver = ver_key.lstrip("v")
        if re.search(r"(alpha|beta|rc)", ver, re.IGNORECASE):
            continue
        result.append({
            "version": ver,
            "require": ver_info.get("require", {}),
        })
    result.sort(key=lambda x: _version_tuple(x["version"]), reverse=True)
    return result


def http_get_auth(url, user=None, password=None, timeout=20):
    """HTTP GET with optional Basic Auth."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Magento-Module-Reporter/1.0"}
        )
        if user and password:
            import base64
            credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
            req.add_header("Authorization", f"Basic {credentials}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace"), resp.status
    except urllib.error.HTTPError as e:
        return "", e.code
    except Exception as e:
        log(f"HTTP error {url}: {e}")
        return "", 0


def _parse_composer_p2_response(body, pkg_name):
    """Parse Composer v2 p2/{package}.json response into version list."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []

    packages = data.get("packages", {}).get(pkg_name, [])
    result = []
    seen = set()
    for ver_info in packages:
        ver_key = ver_info.get("version", "")
        if not ver_key or ver_key in seen:
            continue
        seen.add(ver_key)
        if ver_key.startswith("dev-") or "dev" in ver_key.lower():
            continue
        ver = ver_key.lstrip("v")
        if re.search(r"(alpha|beta|rc)", ver, re.IGNORECASE):
            continue
        result.append({
            "version": ver,
            "require": ver_info.get("require", {}),
        })

    result.sort(key=lambda x: _version_tuple(x["version"]), reverse=True)
    return result


def fetch_packagist_versions(pkg_name, repo=None):
    """
    Fetch all available versions for a package.
    If a private repo is provided, query it. Otherwise fall back to packagist.org.
    Returns: list of {version, require} dicts (stable versions only)
    """
    if repo:
        versions = fetch_repo_versions(pkg_name, repo, None)
        if versions:
            return versions

    # Fall back to packagist.org
    url = PACKAGIST_API.format(pkg_name)
    body, status = http_get(url)
    if not body or status != 200:
        log(f"Packagist: no data for {pkg_name} (status {status})")
        return []

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []

    package = data.get("package", {})
    versions_data = package.get("versions", {})

    result = []
    for ver_key, ver_info in versions_data.items():
        if ver_key.startswith("dev-") or "dev" in ver_key.lower():
            continue
        version = ver_key.lstrip("v")
        if re.search(r"(alpha|beta|rc)", version, re.IGNORECASE):
            continue
        result.append({
            "version": version,
            "require": ver_info.get("require", {}),
        })

    result.sort(key=lambda x: _version_tuple(x["version"]), reverse=True)
    return result


def fetch_composer_available(pkg_name):
    """
    Fallback: use `ddev exec composer show {package} --available` to get versions.
    Returns: (latest_version_str, [list of versions]) or (None, [])
    """
    try:
        result = subprocess.run(
            ["ddev", "exec", "composer", "show", pkg_name, "--available", "--format=json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None, []
        data = json.loads(result.stdout)
        versions = data.get("versions", [])
        stable = [v for v in versions if not re.search(r"(dev|alpha|beta|rc)", v, re.IGNORECASE)]
        if stable:
            return stable[0], stable
        return versions[0] if versions else None, versions
    except Exception as e:
        log(f"composer show failed for {pkg_name}: {e}")
        return None, []


def fetch_all_latest_via_composer():
    """
    Run `composer show --installed --latest --format=json` inside ddev ONCE
    to get installed + latest versions for ALL packages at once.

    Returns: {
        pkg_name: {
            "installed": "x.y.z",
            "latest": "x.y.z",
            "latest-status": "up-to-date" | "semver-safe-update" | "update-possible"
        }
    }
    or {} if ddev is not available.
    """
    info("Fetching latest versions via `composer show --installed --latest`...")
    # Detect if we're already inside a ddev container (DDEV_SITENAME or IS_DDEV_PROJECT is set)
    in_ddev = bool(os.environ.get("IS_DDEV_PROJECT") or os.environ.get("DDEV_SITENAME"))
    if in_ddev:
        cmd = ["composer", "show", "--installed", "--latest", "--format=json"]
    else:
        cmd = ["ddev", "exec", "composer", "show", "--installed", "--latest", "--format=json"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            warn(f"composer show --latest failed (exit {result.returncode}): {result.stderr[:200]}")
            return {}

        data = json.loads(result.stdout)
        packages = data.get("installed", [])
        out = {}
        for p in packages:
            name = p.get("name", "")
            if name:
                out[name] = {
                    "installed": p.get("version", ""),
                    "latest": p.get("latest", ""),
                    "latest-status": p.get("latest-status", ""),
                }
        info(f"  Got latest info for {len(out)} packages")
        return out
    except subprocess.TimeoutExpired:
        warn("composer show --latest timed out after 300s")
        return {}
    except Exception as e:
        warn(f"composer show --latest error: {e}")
        return {}


def _version_tuple(version_str):
    """Convert version string to tuple for sorting, e.g. '2.4.7-p8' → (2, 4, 7, 8)."""
    # Replace -p with . for sorting
    v = re.sub(r"-p(\d+)", r".\1", version_str)
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts[:5])


def is_compatible_with_magento(pkg_require, target_magento):
    """
    Check if a package version's require constraints are compatible with
    the target Magento version by checking magento/framework version requirement.
    """
    fw_constraint = pkg_require.get("magento/framework", "")
    if not fw_constraint:
        # No framework constraint = likely compatible
        return True

    # Determine target framework version prefix
    target_minor = _magento_to_framework_minor(target_magento)
    if not target_minor:
        return True  # Can't determine, assume OK

    return _constraint_allows_version(fw_constraint, target_minor)


def _magento_to_framework_minor(magento_version):
    """
    Map a Magento version string to the expected magento/framework minor version.
    e.g. "2.4.8-p3" → "103.0.8"
    """
    # Extract major minor
    m = re.match(r"2\.4\.(\d+)", magento_version)
    if not m:
        return None
    minor = int(m.group(1))
    # Framework minor = 103.0.{minor}
    return f"103.0.{minor}"


def _constraint_allows_version(constraint, target_prefix):
    """
    Very simplified Composer constraint check.
    Checks if the constraint string allows versions with the given prefix.
    """
    constraint = constraint.strip()

    # Handle OR constraints — Composer allows both || and |
    if "||" in constraint or re.search(r"(?<!\|)\|(?!\|)", constraint):
        parts = re.split(r"\|\||\|", constraint)
        return any(_constraint_allows_version(p.strip(), target_prefix) for p in parts)

    # Handle AND (comma or space-separated ranges)
    parts = re.split(r"\s*,\s*", constraint)
    if len(parts) > 1:
        return all(_single_constraint_allows(p.strip(), target_prefix) for p in parts if p.strip())

    return _single_constraint_allows(constraint, target_prefix)


def _single_constraint_allows(constraint, target_prefix):
    """Check a single constraint clause."""
    constraint = constraint.strip()
    if not constraint or constraint == "*":
        return True

    # Handle wildcard: "103.0.*" — the target must start with "103.0."
    if constraint.endswith(".*"):
        prefix = constraint[:-2]  # e.g. "103.0"
        target_clean = re.sub(r"-p\d+$", "", target_prefix)  # strip patch
        return target_clean.startswith(prefix)

    # Extract operator and version
    m = re.match(r"([~^<>=!]+)?\s*v?(\d[\d.]*(?:-p\d+)?)", constraint)
    if not m:
        return True

    op = m.group(1) or "="
    ver = m.group(2)

    target_tuple = _version_tuple(target_prefix)
    constraint_tuple = _version_tuple(ver)

    if op in ("^", "~"):
        if not constraint_tuple:
            return True
        # ^103.0.7 / ~103.0.7 → allows 103.0.x for x >= 7
        return (target_tuple[:2] == constraint_tuple[:2] and
                target_tuple[2:3] >= constraint_tuple[2:3])
    elif op == ">=":
        return target_tuple >= constraint_tuple
    elif op == ">":
        return target_tuple > constraint_tuple
    elif op in ("<", "<="):
        return False  # conservative
    elif op == "!=":
        return target_tuple != constraint_tuple
    else:
        # Exact match — check prefix
        return str(target_prefix).startswith(ver.rsplit(".", 1)[0])


def find_compatible_version(versions, target_magento):
    """
    From a list of {version, require} dicts (newest first),
    find the MINIMUM version that is compatible with the target Magento version.
    Returns (min_compatible_version_str, latest_version_str).

    If the package has no magento/framework constraints at all, returns ("", latest)
    meaning any version is compatible — the caller should note this.
    """
    if not versions:
        return None, None

    latest = versions[0]["version"]

    # Check if ANY version constrains magento/framework
    has_framework_constraint = any(
        v["require"].get("magento/framework") for v in versions
    )
    if not has_framework_constraint:
        # Package doesn't constrain Magento framework — any version should work
        return "", latest

    compatible_versions = [
        v for v in versions
        if is_compatible_with_magento(v["require"], target_magento)
    ]

    if not compatible_versions:
        return None, latest  # no version explicitly supports target

    # Return oldest compatible (minimum version to upgrade to)
    oldest_compatible = compatible_versions[-1]["version"]
    return oldest_compatible, latest


# ---------------------------------------------------------------------------
# Step 4: Build the full report rows
# ---------------------------------------------------------------------------

FREE_LICENSES = {
    "MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0",
    "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0",
    "OSL-3.0", "AFL-3.0", "ISC", "MPL-2.0",
}


def get_vendor_display_name(pkg_name, root=None):
    """
    Derive a human-readable vendor name dynamically from the package prefix.
    Splits on hyphens and title-cases each word (e.g. 'hyva-themes' → 'Hyva Themes',
    'community-engineering' → 'Community Engineering').
    No hardcoded list — works for any vendor automatically.
    """
    prefix = pkg_name.split("/")[0]
    return " ".join(word.title() for word in prefix.replace("-", " ").split())


def get_license_type(pkg_name, root):
    """
    Read the license field from vendor/{vendor}/{pkg}/composer.json.
    Returns ("free", "MIT") or ("proprietary", "proprietary") or ("unknown", "").
    """
    parts = pkg_name.split("/")
    if len(parts) != 2:
        return "unknown", ""
    vendor, package = parts
    comp_path = root / "vendor" / vendor / package / "composer.json"
    if not comp_path.exists():
        return "unknown", ""
    try:
        data = json.loads(comp_path.read_text(errors="ignore"))
    except (json.JSONDecodeError, OSError):
        return "unknown", ""

    lic = data.get("license", "")
    if isinstance(lic, list):
        lic = lic[0] if lic else ""
    lic = str(lic).strip()

    if not lic:
        return "unknown", ""
    if lic.lower() in ("proprietary", "commercial"):
        return "proprietary", lic
    # Normalise common free identifiers
    for free in FREE_LICENSES:
        if free.lower() in lic.lower():
            return "free", lic
    # Anything else that looks OSI-like treat as free
    if re.match(r"[A-Z].*-\d+(\.\d+)*(-only|-or-later)?$", lic):
        return "free", lic
    return "unknown", lic


def build_report(args, root):
    comp_json = load_composer_json(root)
    lock_data = load_composer_lock(root)
    config_modules = load_config_php(root)

    installed_versions = get_installed_versions(lock_data)

    # Direct requires from composer.json
    direct_requires = {k for k in comp_json.get("require", {}) if is_third_party(k)}

    # ALL 3rd-party packages installed (from composer.lock — includes transitive deps)
    all_installed_3p = [
        p["name"] for p in lock_data.get("packages", [])
        if is_third_party(p["name"])
    ]

    # Map ALL installed 3rd-party packages to Magento module names (vendor scan)
    info("Scanning vendor registration files...")
    pkg_to_modules = scan_vendor_modules(root, all_installed_3p)

    # Include a package if it's a direct require OR registers at least one Magento module
    third_party = sorted(
        p for p in all_installed_3p
        if p in direct_requires or len(pkg_to_modules.get(p, [])) > 0
    )

    transitive_pkgs = {p for p in third_party if p not in direct_requires}
    info(f"Found {len(third_party)} third-party packages "
         f"({len(direct_requires)} direct, {len(transitive_pkgs)} transitive with Magento modules)")

    # Classify parent/child
    info("Classifying parent/child relationships...")
    classifications = classify_packages(third_party, pkg_to_modules, lock_data)

    # --- Version data collection ---
    composer_latest = {}  # {pkg_name: {installed, latest, latest-status}}
    amasty_feed = {}      # {module_code: {version, url, price}} — for product URLs
    mirasvit_feed = {}    # {composer_pkg: {version, url, sku}} — for latest released
    magefan_feed = {}     # {composer_pkg: {version, url, title}} — for latest released
    mageworx_feed = {}    # {composer_pkg: {version, url, title, price}} — for latest released
    repos = []            # private repo credentials for compatible-version API calls

    if not args.no_api:
        # PRIMARY: one composer show --installed --latest call covers ALL vendors
        composer_latest = fetch_all_latest_via_composer()

        # Amasty feed for product page URLs and prices
        amasty_feed = fetch_amasty_feed()

        # Mirasvit feed for latest released and product URL
        mirasvit_feed = fetch_mirasvit_feed()

        # Magefan feed for latest released and product URL
        magefan_feed = fetch_magefan_feed()

        # MageWorx feed for latest released and product URL/price
        mageworx_feed = fetch_mageworx_feed()

        # Repo credentials for compatible-version detection via private repo API
        repos = extract_repo_credentials(comp_json, root)

    # Build rows
    rows = []
    packagist_cache = {}

    for pkg_name in sorted(third_party):
        cls = classifications.get(pkg_name, {})
        role = cls.get("role", "parent")
        parent_pkg = cls.get("parent")
        magento_modules = cls.get("magento_modules", [])
        primary_module = cls.get("primary_module", "")
        child_modules = cls.get("child_modules", [])

        if not args.include_children and role in ("child-dep", "child-hyva"):
            continue

        installed_ver = installed_versions.get(pkg_name, "not-installed")
        source_url = get_package_source_url(lock_data, pkg_name)

        # Module status from config.php
        module_status = _get_module_status(primary_module, magento_modules, config_modules)

        # Vendor display name + license type (from local composer.json — no API needed)
        vendor_display = get_vendor_display_name(pkg_name, root)
        license_category, license_raw = get_license_type(pkg_name, root)

        # Version lookup
        latest_ver = ""
        latest_status = ""
        compatible_ver = ""
        module_url = ""
        price = ""
        latest_released = ""  # absolute latest from vendor's own repo/feed
        notes = []

        # Tag transitive deps (installed as dependency of another package, not directly required)
        if pkg_name in transitive_pkgs:
            notes.append("transitive dep")

        if not args.no_api:
            vendor = pkg_name.split("/")[0]

            # --- Latest version: from composer show (covers all vendors) ---
            cdata = composer_latest.get(pkg_name, {})
            latest_ver = cdata.get("latest", "")
            latest_status = cdata.get("latest-status", "")

            # --- Product URL + price + latest released: from Amasty feed ---
            if vendor == "amasty":
                feed_data = _find_amasty_feed_data(primary_module, magento_modules, amasty_feed)
                if feed_data:
                    module_url = feed_data.get("url", "")
                    latest_released = feed_data.get("version", "")
                    raw_price = feed_data.get("price", "")
                    # Only show price for parent modules (or if --include-child-pricing)
                    if raw_price and (role == "parent" or args.include_child_pricing):
                        price = f"${raw_price}"
            elif vendor == "mirasvit":
                feed_data = mirasvit_feed.get(pkg_name, {})
                if feed_data:
                    latest_released = feed_data.get("version", "") or latest_released
                    if feed_data.get("url"):
                        module_url = feed_data.get("url", "")
            elif vendor == "magefan":
                feed_data = magefan_feed.get(pkg_name, {})
                if feed_data:
                    latest_released = feed_data.get("version", "") or latest_released
                    if feed_data.get("url"):
                        module_url = feed_data.get("url", "")
            elif vendor == "mageworx":
                feed_data = mageworx_feed.get(pkg_name, {})
                if feed_data:
                    latest_released = feed_data.get("version", "") or latest_released
                    if feed_data.get("url"):
                        module_url = feed_data.get("url", "")
                    raw_price = feed_data.get("price", "")
                    if raw_price and (role == "parent" or args.include_child_pricing):
                        price = f"${raw_price}"

            # --- Compatible version + latest released: via private repo API ---
            pkg_repo = find_package_repo(lock_data, pkg_name, repos)

            if vendor == "studioraz":
                notes.append("internal")
                # No compatible version check needed for internal modules
            else:
                versions = _get_package_versions(pkg_name, pkg_repo, packagist_cache)
                compat, repo_latest = find_compatible_version(versions, args.target_magento)
                compatible_ver = compat if compat is not None else ""
                if not versions:
                    notes.append("check manually for compatibility")
                # Latest released from repo (for non-amasty; amasty uses feed above)
                if repo_latest and vendor != "amasty":
                    latest_released = repo_latest

            # Add update-available note: only when latest is genuinely newer than installed
            if latest_status == "update-possible" and latest_ver and installed_ver:
                if _version_tuple(latest_ver) > _version_tuple(installed_ver):
                    notes.append("major update available")

        # Build sub-module list for display
        child_module_str = "; ".join(child_modules) if child_modules else ""

        # Determine update status label from composer latest-status
        if not args.no_api and latest_ver:
            lt = _version_tuple(latest_ver)
            it = _version_tuple(installed_ver) if installed_ver not in ("", "not-installed") else None
            if it is None:
                update_status = "not installed"
            elif lt == it:
                update_status = "up to date"
            elif lt > it:
                update_status = "update available"
            else:
                update_status = "ahead of repo"  # installed newer than repo knows about
        else:
            update_status = ""

        # Already compatible: is current installed version >= minimum compatible version?
        if compatible_ver and compatible_ver not in ("—", "any (no constraint)") and installed_ver not in ("", "not-installed"):
            already_compat = "yes" if _version_tuple(installed_ver) >= _version_tuple(compatible_ver) else "no — upgrade needed"
        elif compatible_ver == "any (no constraint)":
            already_compat = "yes"
        else:
            already_compat = ""

        rows.append({
            "Module Name": primary_module or pkg_name,
            "Vendor": vendor_display,
            "Composer Name": pkg_name,
            "Status": module_status,
            "Role": role,
            "Parent Package": parent_pkg or "",
            "Child Modules": child_module_str,
            "License Type": license_raw,
            "Price": price,
            "Current Version": installed_ver,
            "Latest Available": latest_ver or "—",
            "Latest Released": latest_released,
            "Update Status": update_status,
            "Compatible Version": (
                "any (no constraint)" if compatible_ver == "" and not args.no_api
                else compatible_ver or ("—" if not args.no_api else "")
            ),
            "Already Compatible": already_compat,
            "Repository URL": module_url or source_url,
            "Notes": "; ".join(notes),
        })

        log(f"  {pkg_name}: {installed_ver} → latest={latest_ver or '?'} released={latest_released or '?'} ({update_status}) compat={compatible_ver or '?'}")

    # Add app/code local modules
    info("Scanning app/code for local modules...")
    appcode_rows = scan_appcode_modules(root, config_modules)
    info(f"  Found {len(appcode_rows)} local modules in app/code")
    rows.extend(appcode_rows)

    return rows



def scan_appcode_modules(root, config_modules):
    """
    Scan app/code for locally installed (non-composer) Magento modules.
    Returns a list of row dicts ready to be appended to the CSV output.
    """
    appcode_dir = root / "app" / "code"
    if not appcode_dir.exists():
        return []

    rows = []
    seen_modules = set()

    for reg_file in sorted(appcode_dir.rglob("registration.php")):
        try:
            content = reg_file.read_text(errors="ignore")
        except OSError:
            continue

        modules = re.findall(r"ComponentRegistrar::MODULE,\s*'([^']+)'", content)
        if not modules:
            continue

        # Skip if we've already processed the primary module (avoid duplicates)
        if modules[0] in seen_modules:
            continue
        seen_modules.update(modules)

        module_dir = reg_file.parent

        # Try to get name and version from composer.json in the module dir
        composer_name = ""
        version = ""
        comp_path = module_dir / "composer.json"
        if comp_path.exists():
            try:
                cdata = json.loads(comp_path.read_text(errors="ignore"))
                composer_name = cdata.get("name", "")
                version = cdata.get("version", "")
            except (json.JSONDecodeError, OSError):
                pass

        primary_module = modules[0]
        child_modules = modules[1:]
        module_status = _get_module_status(primary_module, modules, config_modules)

        # Get vendor display + license from local composer.json if present
        vendor_display = get_vendor_display_name(composer_name) if composer_name else "local"
        if comp_path.exists():
            try:
                cdata_lic = json.loads(comp_path.read_text(errors="ignore"))
                lic_raw = cdata_lic.get("license", "")
                if isinstance(lic_raw, list):
                    lic_raw = lic_raw[0] if lic_raw else ""
                license_raw = str(lic_raw).strip()
            except (json.JSONDecodeError, OSError):
                license_raw = ""
        else:
            license_raw = ""

        rows.append({
            "Module Name": primary_module,
            "Vendor": vendor_display,
            "Composer Name": composer_name,
            "Status": module_status,
            "Role": "local",
            "Parent Package": "",
            "Child Modules": "; ".join(child_modules),
            "License Type": license_raw,
            "Price": "",
            "Current Version": version,
            "Latest Available": "—",
            "Latest Released": "",
            "Update Status": "",
            "Compatible Version": "—",
            "Already Compatible": "",
            "Repository URL": "",
            "Notes": "app/code",
        })

    return rows


def _get_module_status(primary_module, all_modules, config_modules):
    """Return 'enabled', 'disabled', or 'not-registered' based on config.php."""
    if not all_modules:
        return "not-registered"

    # Check primary first, then any module in the package
    for mod in ([primary_module] + all_modules):
        if mod in config_modules:
            return "enabled" if config_modules[mod] else "disabled"

    return "not-registered"


def _find_amasty_feed_data(primary_module, all_modules, amasty_feed):
    """Find Amasty feed data by trying various module code formats."""
    if not amasty_feed:
        return None

    # Try exact match with primary module
    for mod in ([primary_module] + all_modules):
        if mod in amasty_feed:
            return amasty_feed[mod]

    # Try partial match (Amasty feed uses short codes sometimes)
    if primary_module:
        short = primary_module.replace("Amasty_", "")
        for code, data in amasty_feed.items():
            if short.lower() in code.lower():
                return data

    return None


def _get_package_versions(pkg_name, repo, cache):
    """Fetch and cache versions — tries private repo first, then packagist.org."""
    if pkg_name not in cache:
        log(f"Fetching versions: {pkg_name}")
        cache[pkg_name] = fetch_packagist_versions(pkg_name, repo)
        time.sleep(0.2)
    return cache[pkg_name]


def _get_packagist_versions(pkg_name, cache):
    """Legacy wrapper — fetch from public packagist only."""
    return _get_package_versions(pkg_name, None, cache)


# ---------------------------------------------------------------------------
# Step 5: Output
# ---------------------------------------------------------------------------

def get_columns(include_children):
    columns = [
        "Module Name",
        "Vendor",
        "Composer Name",
        "Status",
        "License Type",
        "Price",
        "Current Version",
        "Latest Available",
        "Latest Released",
        "Update Status",
        "Compatible Version",
        "Already Compatible",
        "Repository URL",
        "Notes",
    ]
    if include_children:
        columns.insert(4, "Role")
        columns.insert(5, "Parent Package")
        columns.insert(6, "Child Modules")
    return columns


def write_csv(rows, output_path, columns):
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    info(f"CSV report written to: {output_path}")


def write_ai_prompt(rows, output_path, target_magento, target_php, columns):
    """Write a text prompt suitable for pasting into Claude/ChatGPT."""
    lines = [
        f"# Magento Module Compatibility Analysis Request",
        f"",
        f"I am upgrading a Magento 2 project from its current version to **{target_magento}** (PHP {target_php}).",
        f"Please analyze the following third-party modules and for each one that does NOT have a",
        f"'Compatible Version' filled in, tell me:",
        f"1. Whether the module supports Magento {target_magento} / PHP {target_php}",
        f"2. The minimum version required for compatibility",
        f"3. Any breaking changes or migration steps needed",
        f"4. The official product page or changelog URL",
        f"",
        f"## Modules (CSV format)",
        f"",
        f"```",
        ",".join(columns),
    ]
    for row in rows:
        lines.append(",".join(str(row.get(col, "")) for col in columns))
    lines += [
        "```",
        "",
        "Focus especially on modules where 'Compatible Version' is empty or '—'.",
        "For private/internal modules (marked 'internal' in Notes), you can skip them.",
    ]

    prompt_text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt_text)
    info(f"AI prompt written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _verbose
    args = parse_args()
    _verbose = args.verbose

    info(f"Magento Module Compatibility Reporter")
    info(f"Target: Magento {args.target_magento} / PHP {args.target_php}")

    root = find_project_root()
    info(f"Project root: {root}")

    rows = build_report(args, root)
    columns = get_columns(args.include_children)

    info(f"Total packages processed: {len(rows)}")

    # Determine output path
    output = args.output
    if args.format == "ai-prompt" and not output.endswith(".txt"):
        output = output.replace(".csv", ".txt") if output.endswith(".csv") else output + ".txt"

    if args.format == "ai-prompt":
        write_ai_prompt(rows, output, args.target_magento, args.target_php, columns)
    else:
        write_csv(rows, output, columns)

    # Print summary to stdout
    vendor_rows = [r for r in rows if r["Role"] != "local"]
    local_rows  = [r for r in rows if r["Role"] == "local"]
    parents  = sum(1 for r in vendor_rows if r["Role"] == "parent")
    children = sum(1 for r in vendor_rows if r["Role"] != "parent")
    enabled  = sum(1 for r in rows if r["Status"] == "enabled")
    disabled = sum(1 for r in rows if r["Status"] == "disabled")
    up_to_date   = sum(1 for r in vendor_rows if r["Update Status"] == "up to date")
    has_updates  = sum(1 for r in vendor_rows if r["Update Status"] == "update available")
    needs_upgrade = sum(1 for r in rows if r["Already Compatible"] == "no — upgrade needed")
    no_compat    = sum(1 for r in vendor_rows if r["Compatible Version"] == "—")

    print(f"\n{'='*60}")
    print(f"  Module Report Summary  (target: Magento {args.target_magento})")
    print(f"{'='*60}")
    print(f"  Total:                 {len(rows)}  (vendor: {len(vendor_rows)}, app/code: {len(local_rows)})")
    print(f"  Parents (vendor):      {parents}")
    print(f"  Children/deps:         {children}")
    print(f"  Local (app/code):      {len(local_rows)}")
    print(f"  Enabled:               {enabled}")
    print(f"  Disabled:              {disabled}")
    print(f"  Up to date:            {up_to_date}")
    print(f"  Update available:      {has_updates}")
    print(f"  Needs upgrade (compat):{needs_upgrade}  ← must update before Magento upgrade")
    print(f"  No compat data:        {no_compat}  ← check manually")
    print(f"  Output:                {output}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
