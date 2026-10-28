#!/usr/bin/env python3
"""Add optional Vista ID local linking to pinned LibreTube sources."""
import argparse
from pathlib import Path
import shutil

def patch(root: Path):
    here = Path(__file__).resolve().parents[1]
    target = root / "app/src/main/java/com/github/libretube/ui/preferences"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(here / "patches/VistaIdAccountActivity.kt", target / "VistaIdAccountActivity.kt")

    manifest = root / "app/src/main/AndroidManifest.xml"
    text = manifest.read_text(encoding="utf-8")
    anchor = '        <activity\n            android:name=".ui.activities.SettingsActivity"'
    assert anchor in text, "LibreTube SettingsActivity manifest anchor missing"
    text = text.replace(anchor, '''        <activity
            android:name=".ui.preferences.VistaIdAccountActivity"
            android:exported="false" />

''' + anchor, 1)
    manifest.write_text(text, encoding="utf-8")

    preferences = root / "app/src/main/res/xml/settings.xml"
    xml = preferences.read_text(encoding="utf-8")
    anchor = '    <PreferenceCategory>'
    assert anchor in xml, "LibreTube settings XML anchor missing"
    xml = xml.replace(anchor, '''    <Preference
        android:icon="@drawable/ic_settings"
        app:key="vista_id"
        app:title="Vista ID (opcional)"
        app:summary="Associar perfil local, sem apagar playlists ou histórico. Cloud ainda não disponível." />

''' + anchor, 1)
    preferences.write_text(xml, encoding="utf-8")

    settings = target / "MainSettings.kt"
    source = settings.read_text(encoding="utf-8")
    anchor = '        val update = findPreference<Preference>("update")'
    assert anchor in source, "LibreTube MainSettings.kt anchor missing"
    source = source.replace('import android.os.Bundle', 'import android.os.Bundle\nimport android.content.Intent', 1)
    source = source.replace(anchor, '''        findPreference<Preference>("vista_id")?.setOnPreferenceClickListener {
            startActivity(Intent(requireContext(), VistaIdAccountActivity::class.java))
            true
        }

''' + anchor, 1)
    settings.write_text(source, encoding="utf-8")
    print("Vista ID optional local linking patched.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("upstream", type=Path)
    args = p.parse_args()
    patch(args.upstream.resolve())
