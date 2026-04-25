#!/usr/bin/env bats

# Bats is a testing framework for Bash
# Documentation: https://bats-core.readthedocs.io/en/stable/
# Bats libraries: https://github.com/ztombol/bats-docs
#
# Install dependencies (macOS):
#   brew install bats-core bats-assert bats-support
#
# Run all tests (local, excludes release tag):
#   bats ./tests/test.bats --filter-tags '!release'
#
# Run all tests including release:
#   bats ./tests/test.bats
#
# Debug output:
#   bats ./tests/test.bats --show-output-of-passing-tests --verbose-run --print-output-on-failure

setup() {
  set -eu -o pipefail

  export GITHUB_REPO=studioraz/ddev-project-toolkit

  TEST_BREW_PREFIX="$(brew --prefix 2>/dev/null || true)"
  export BATS_LIB_PATH="${BATS_LIB_PATH:-}:${TEST_BREW_PREFIX}/lib:/usr/lib/bats"
  bats_load_library bats-assert
  bats_load_library bats-support

  export DIR="$(cd "$(dirname "${BATS_TEST_FILENAME}")/.." >/dev/null 2>&1 && pwd)"
  export PROJNAME="test-$(basename "${GITHUB_REPO}")"
  mkdir -p "${HOME}/tmp"
  export TESTDIR="$(mktemp -d "${HOME}/tmp/${PROJNAME}.XXXXXX")"
  export DDEV_NONINTERACTIVE=true
  export DDEV_NO_INSTRUMENTATION=true

  # Aggressive cleanup of any previous run to prevent Docker/Mutagen resource collisions
  ddev delete -Oy "${PROJNAME}" >/dev/null 2>&1 || true
  docker volume rm "${PROJNAME}_project_mutagen" >/dev/null 2>&1 || true

  cd "${TESTDIR}"
  run ddev config --project-name="${PROJNAME}" --project-type=php --project-tld=ddev.site \
    --default-container-timeout=120
  assert_success
  run ddev start -y
  assert_success
}

health_checks() {
  # Verify core addon files were deployed into .ddev/ (no bats-file dependency)
  [ -f ".ddev/commands/web/n98" ]
  [ -f ".ddev/commands/web/generate-env" ]
  [ -f ".ddev/commands/web/module-report" ]
  [ -f ".ddev/commands/web/dep" ]
  [ -f ".ddev/scripts/magento-toolkit/uninstall.sh" ]
  [ -f ".ddev/config.magento.hooks.yaml" ]
}

teardown() {
  set -eu -o pipefail
  ddev delete -Oy "${PROJNAME}" >/dev/null 2>&1 || true
  docker volume rm "${PROJNAME}_project_mutagen" >/dev/null 2>&1 || true
  # In GitHub Actions, preserve TESTDIR for artifact upload
  if [ -n "${GITHUB_ENV:-}" ]; then
    [ -e "${GITHUB_ENV:-}" ] && echo "TESTDIR=${HOME}/tmp/${PROJNAME}" >> "${GITHUB_ENV}"
  else
    [ -n "${TESTDIR:-}" ] && rm -rf "${TESTDIR}"
  fi
}

@test "install from directory" {
  set -eu -o pipefail
  echo "# ddev add-on get ${DIR} with project ${PROJNAME} in $(pwd)" >&3
  run ddev add-on get "${DIR}"
  assert_success
  run ddev restart -y
  assert_success
  health_checks
}

@test "n98 is lazy-installed on first invocation" {
  set -eu -o pipefail
  run ddev add-on get "${DIR}"
  assert_success

  # bin/n98 must NOT exist inside the container before the first ddev n98 call
  run ddev exec bash -c '[ ! -f bin/n98 ]'
  assert_success

  # First invocation should download and then run successfully
  run ddev n98 --version
  assert_success
  assert_output --partial "n98"

  # Binary must now exist inside the container
  run ddev exec bash -c '[ -f bin/n98 ]'
  assert_success
}

@test "n98 is not re-downloaded on subsequent invocations" {
  set -eu -o pipefail
  run ddev add-on get "${DIR}"
  assert_success

  # First call — triggers download
  run ddev n98 --version
  assert_success

  # Record modification time inside the container
  run ddev exec bash -c 'stat -c "%Y" bin/n98 2>/dev/null || stat -f "%m" bin/n98'
  assert_success
  local mtime_before="${output}"

  # Second call — must NOT re-download
  run ddev n98 --version
  assert_success

  run ddev exec bash -c 'stat -c "%Y" bin/n98 2>/dev/null || stat -f "%m" bin/n98'
  assert_success
  local mtime_after="${output}"

  [ "${mtime_before}" = "${mtime_after}" ]
}

@test "generate-env --dry-run outputs expected PHP" {
  set -eu -o pipefail
  run ddev add-on get "${DIR}"
  assert_success

  run ddev generate-env --dry-run
  assert_success

  # Database connection (use 'username' which has consistent single-space alignment)
  assert_output --partial "'username' => 'db'"
  # Session in Redis
  assert_output --partial "'save' => 'redis'"
  # OpenSearch catalog engine
  assert_output --partial "opensearch"
  # RabbitMQ queue
  assert_output --partial "rabbitmq"
  # Project hostname embedded
  assert_output --partial "${PROJNAME}.ddev.site"
}

@test "generate-env writes app/etc/env.php" {
  set -eu -o pipefail
  run ddev add-on get "${DIR}"
  assert_success

  # File must not exist yet inside the container
  run ddev exec bash -c '[ ! -f app/etc/env.php ]'
  assert_success

  run ddev generate-env
  assert_success
  assert_output --partial "env.php generated at"

  # File must now exist inside the container
  run ddev exec bash -c '[ -f app/etc/env.php ]'
  assert_success
}

@test "generate-env does not overwrite existing env.php without --force" {
  set -eu -o pipefail
  run ddev add-on get "${DIR}"
  assert_success

  # Write a sentinel file inside the container
  run ddev exec bash -c "mkdir -p app/etc && echo 'SENTINEL_CONTENT' > app/etc/env.php"
  assert_success

  run ddev generate-env
  assert_success

  # Sentinel must still be present inside the container
  run ddev exec bash -c "grep -q 'SENTINEL_CONTENT' app/etc/env.php"
  assert_success
}

@test "generate-env --force overwrites existing env.php" {
  set -eu -o pipefail
  run ddev add-on get "${DIR}"
  assert_success

  # Write a sentinel file inside the container
  run ddev exec bash -c "mkdir -p app/etc && echo 'SENTINEL_CONTENT' > app/etc/env.php"
  assert_success

  run ddev generate-env --force
  assert_success
  # Verify the file was (re)generated, not skipped
  assert_output --partial "env.php generated at"
}

# bats test_tags=release
@test "install from release" {
  set -eu -o pipefail
  echo "# ddev add-on get ${GITHUB_REPO} with project ${PROJNAME} in $(pwd)" >&3
  run ddev add-on get "${GITHUB_REPO}"
  assert_success
  run ddev restart -y
  assert_success
  health_checks
}
