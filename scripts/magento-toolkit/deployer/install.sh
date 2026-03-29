#!/usr/bin/env bash
## #ddev-generated: If you want to edit and own this file, remove this line.
## Description: Installs studioraz/deployer-magento globally via Composer inside the DDEV web container.
##              Skips install if the dep binary already exists (idempotent).

if [ -f "${HOME}/.composer/vendor/bin/dep" ]; then
  echo "deployer already installed, skipping."
  exit 0
fi

echo "Installing studioraz/deployer-magento globally..."
composer config --global repositories.packagist.org composer https://packagist.org
composer global require studioraz/deployer-magento
echo "deployer installed at ~/.composer/vendor/bin/dep"

