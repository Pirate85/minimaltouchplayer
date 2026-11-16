#!/usr/bin/env bash
# ============================================================
#  MinimalTouchPlayer (MTP) — .rpm package builder
#  Usage: ./packaging/build-rpm.sh
#  Output: packaging/mtp-1.2.1-1.noarch.rpm
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PKG_NAME="mtp"
VERSION="1.2.1"
RELEASE="1"
OUTPUT="${SCRIPT_DIR}/${PKG_NAME}-${VERSION}-${RELEASE}.noarch.rpm"

echo "🎵 Building ${PKG_NAME} v${VERSION} (MinimalTouchPlayer) — RPM"
echo "   Source:  ${PROJECT_ROOT}"
echo "   Output:  ${OUTPUT}"
echo ""

# --- Sanity checks -------------------------------------------------
[[ -f "${PROJECT_ROOT}/mtp.py" ]] || { echo "❌ mtp.py not found"; exit 1; }
command -v rpmbuild &>/dev/null    || { echo "❌ rpmbuild not found (apt install rpm-build)"; exit 1; }

# --- Clean previous build ------------------------------------------
rm -f "${OUTPUT}"

# --- Setup rpmbuild tree in /tmp (avoid spaces in path!) ------------
RPM_TOPDIR="/tmp/rpm-build-mtp"
rm -rf "$RPM_TOPDIR"
mkdir -p "${RPM_TOPDIR}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

echo "📦 Preparing source tarball…"
SRC_NAME="${PKG_NAME}-${VERSION}"
STAGING="/tmp/mtp-rpm-staging"
rm -rf "$STAGING" && mkdir -p "${STAGING}/${SRC_NAME}"

# Copy application files into staging
cp "${PROJECT_ROOT}/mtp.py"         "${STAGING}/${SRC_NAME}/"
cp -r "${PROJECT_ROOT}/MTP Icons"   "${STAGING}/${SRC_NAME}/"
if [[ -d "${SCRIPT_DIR}/vendor" ]]; then
    cp -r "${SCRIPT_DIR}/vendor"    "${STAGING}/${SRC_NAME}/vendor/"
fi

# Copy packaging assets (launcher, desktop file, icon)
mkdir -p "${STAGING}/${SRC_NAME}/usr/bin"
mkdir -p "${STAGING}/${SRC_NAME}/usr/share/applications"
mkdir -p "${STAGING}/${SRC_NAME}/usr/share/icons/hicolor/128x128/apps"

cp "${SCRIPT_DIR}/deb/usr/bin/mtp"                                "${STAGING}/${SRC_NAME}/usr/bin/"
chmod 755 "${STAGING}/${SRC_NAME}/usr/bin/${PKG_NAME}"
cp "${SCRIPT_DIR}/deb/usr/share/applications/${PKG_NAME}.desktop" "${STAGING}/${SRC_NAME}/usr/share/applications/"
cp "${PROJECT_ROOT}/icon.png"                                      "${STAGING}/${SRC_NAME}/usr/share/icons/hicolor/128x128/apps/mtp.png"

# Create source tarball (in /tmp — no spaces!)
tar czf "${RPM_TOPDIR}/SOURCES/${SRC_NAME}.tar.gz" -C "$STAGING" "${SRC_NAME}"
rm -rf "$STAGING"

# --- Copy spec file --------------------------------------------------
cp "${SCRIPT_DIR}/mtp.spec" "${RPM_TOPDIR}/SPECS/"

# --- Build (nodeps: skip system RPM DB check on non-Fedora) ----------
echo "🔨 Running rpmbuild…"
rpmbuild --define "_topdir ${RPM_TOPDIR}" \
         --nodeps \
         -bb "${RPM_TOPDIR}/SPECS/${PKG_NAME}.spec" 2>&1 | tail -20

# --- Collect output ---------------------------------------------------
BUILT_RPM=$(find "${RPM_TOPDIR}/RPMS" -name "*.rpm" 2>/dev/null | head -1)
if [[ -n "$BUILT_RPM" && -f "$BUILT_RPM" ]]; then
    cp "$BUILT_RPM" "$OUTPUT"
fi

# Cleanup build tree (keep the final .rpm in packaging/)
rm -rf "$RPM_TOPDIR"

echo ""
if [[ -f "$OUTPUT" ]]; then
    echo "✅ Done! Package: ${OUTPUT}"
    ls -lh "$OUTPUT"
else
    echo "❌ Build failed — no .rpm found!"
    exit 1
fi
echo ""
echo "Install with:"
echo "   sudo rpm -i $(basename "${OUTPUT}")"
echo "   # or:  sudo dnf install ./$(basename "${OUTPUT}")"
echo ""
echo "Uninstall with:"
echo "   sudo rpm -e mtp"
