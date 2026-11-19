%global _build_id_links none
Name:           mtp
Version:        1.2.1
Release:        1%{?dist}
Summary:        MinimalTouchPlayer — minimalist touch music player

License:        MIT
URL:            https://github.com/Pirate85/minimaltouchplayer
Source0:        %{name}-%{version}.tar.gz

# System dependencies (NOT bundled in the package)
Requires:       python3 >= 3.10
Requires:       python3-numpy
Requires:       python3-pillow
Requires:       python3-pillow-tk
Requires:       ffmpeg
# Audio backend (at least one required — launcher checks at runtime)
Requires:       alsa-utils
Recommends:     pipewire-pulseaudio
Requires:       python3-tkinter

BuildArch:      noarch

%description
A square, dark-themed desktop music player with large touch-friendly buttons
and no album art. Supports MP3, FLAC, OGG, Opus, M4A/AAC, WAV, WMA, AIFF, APE, WebM.
Features: folder picker, live volume control, seek bar, position resume,
bilingual UI (DE/EN), keyboard shortcuts, zoom support, shuffle & repeat.

CustomTkinter GUI framework is vendored in the package — no pip install needed!


%prep
# Source tarball is created by build-rpm.sh with all files staged correctly
%setup -q -n %{name}-%{version}


%build
# Pure Python application — nothing to compile


%install
rm -rf %{buildroot}

# Application core
mkdir -p %{buildroot}/usr/share/mtp
cp mtp.py %{buildroot}/usr/share/mtp/
cp -r "MTP Icons" %{buildroot}/usr/share/mtp/

# Vendored Python packages (customtkinter, darkdetect, packaging)
cp -r vendor %{buildroot}/usr/share/mtp/vendor

# Launcher script
mkdir -p %{buildroot}/usr/bin
cp usr/bin/mtp %{buildroot}/usr/bin/
chmod 755 %{buildroot}/usr/bin/mtp

# Desktop integration
mkdir -p %{buildroot}/usr/share/applications
cp usr/share/applications/mtp.desktop %{buildroot}/usr/share/applications/

# Hicolor icon
mkdir -p %{buildroot}/usr/share/icons/hicolor/128x128/apps
cp usr/share/icons/hicolor/128x128/apps/mtp.png %{buildroot}/usr/share/icons/hicolor/128x128/apps/


%files
/usr/bin/mtp
/usr/share/mtp/mtp.py
/usr/share/mtp/MTP\ Icons/backward.png
/usr/share/mtp/MTP\ Icons/folder.png
/usr/share/mtp/MTP\ Icons/forward.png
/usr/share/mtp/MTP\ Icons/pause.png
/usr/share/mtp/MTP\ Icons/play.png
/usr/share/mtp/MTP\ Icons/repeat_all.png
/usr/share/mtp/MTP\ Icons/repeat_off.png
/usr/share/mtp/MTP\ Icons/repeat_one.png
/usr/share/mtp/MTP\ Icons/shuffle_off.png
/usr/share/mtp/MTP\ Icons/shuffle_on.png
/usr/share/mtp/vendor/*
/usr/share/applications/mtp.desktop
/usr/share/icons/hicolor/128x128/apps/mtp.png


%changelog
* Mon Nov 16 2026 Pirate85 <Pirate85@web.de> - 1.2.1-1
- Transparent icons (no gray background, ~60% smaller)
- Simplified folder picker: [↑] [▶ Play] [Abbrechen] in one row
- Vendored CustomTkinter + darkdetect — no pip install needed!
* Wed Oct 30 2026 Pirate85 <Pirate85@web.de> - 1.2.0-1
- Track dropdown, natural sort, folder picker track count
- Shuffle & repeat, engine rewrite (sink-paced timing)
* Thu Oct 24 2026 Pirate85 <Pirate85@web.de> - 1.1.0-1
- Initial public release
