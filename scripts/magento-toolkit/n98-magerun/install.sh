if [ -f "${DDEV_APPROOT}/bin/n98" ]; then
    echo "n98 already installed at bin/n98"
    exit 0
fi
if [ -d "${DDEV_APPROOT}/src" ]; then 
    BIN_DIR="${DDEV_APPROOT}/src/bin"
else 
    BIN_DIR="${DDEV_APPROOT}/bin"
fi
mkdir -p "$BIN_DIR"
wget https://files.magerun.net/n98-magerun2.phar -O "$BIN_DIR/n98"
chmod +x "$BIN_DIR/n98"
echo "n98 installed at $BIN_DIR/n98"