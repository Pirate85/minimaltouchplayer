#!/usr/bin/env bash
# ============================================================
#  MinimalTouchPlayer (MTP) — .deb package builder
#  Usage: ./packaging/build-deb.sh
#  Output: packaging/mtp_1.1.0_all.deb
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PKG_NAME="mtp"
VERSION="1.1.0"
BUILD_DIR="${SCRIPT_DIR}/deb"
OUTPUT="${SCRIPT_DIR}/${PKG_NAME}_${VERSION}_all.deb"

echo "🎵 Building ${PKG_NAME} v${VERSION} (MinimalTouchPlayer)"
echo "   Source:  ${PROJECT_ROOT}"
echo "   Output:  ${OUTPUT}"
echo ""

# --- Sanity checks -------------------------------------------------
[[ -f "${PROJECT_ROOT}/mtp.py" ]] || { echo "❌ mtp.py not found"; exit 1; }
[[ -f "${PROJECT_ROOT}/icon.png" ]]       || { echo "❌ icon.png not found"; exit 1; }
command -v dpkg-deb &>/dev/null           || { echo "❌ dpkg-deb not found (apt install dpkg-dev)"; exit 1; }

# --- Clean previous build artifacts --------------------------------
rm -f "${OUTPUT}"

# --- Copy app files into package tree ------------------------------
echo "📋 Copying application files…"
cp "${PROJECT_ROOT}/mtp.py" "${BUILD_DIR}/usr/share/mtp/mtp.py"

# Install icon as hicolor theme icon (so .desktop can reference by name)
ICON_DST="${BUILD_DIR}/usr/share/icons/hicolor/128x128/apps/${PKG_NAME}.png"
cp "${PROJECT_ROOT}/icon.png" "$ICON_DST"

# --- Set permissions -------------------------------------------------
chmod 644 "${BUILD_DIR}/DEBIAN/control"
# Maintainer scripts must be executable (755)
for script in postinst postrm prerm; do
    [[ -f "${BUILD_DIR}/DEBIAN/${script}" ]] && chmod 755 "${BUILD_DIR}/DEBIAN/${script}"
done
chmod 755 "${BUILD_DIR}/usr/bin/${PKG_NAME}"
chmod 644 "${BUILD_DIR}/usr/share/applications/${PKG_NAME}.desktop"
chmod 644 "$ICON_DST"
chmod 644 "${BUILD_DIR}/usr/share/mtp/mtp.py"

# Ensure correct permissions throughout
find "${BUILD_DIR}" -type d -exec chmod 755 {} \;
find "${BUILD_DIR}" -type f ! -path "*/DEBIAN/*" -exec chmod 644 {} \;
chmod 755 "${BUILD_DIR}/usr/bin/${PKG_NAME}"
# Re-assert maintainer script permissions (find above may have reset them)
for script in postinst postrm prerm; do
    [[ -f "${BUILD_DIR}/DEBIAN/${script}" ]] && chmod 755 "${BUILD_DIR}/DEBIAN/${script}"
done

# --- Build -----------------------------------------------------------
echo "🔨 Running dpkg-deb…"
dpkg-deb --build --root-owner-group "${BUILD_DIR}" "${OUTPUT}"

echo ""
echo "✅ Done! Package: ${OUTPUT}"
echo ""
echo "Install with:"
echo "   sudo dpkg -i $(basename "$OUTPUT")"
echo "   # or:  sudo apt install ./$(basename "$OUTPUT")"
echo ""
echo "Uninstall with:"
echo "   sudo dpkg -r ${PKG_NAME}"
