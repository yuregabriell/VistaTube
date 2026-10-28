#!/usr/bin/env python3
"""VistaTube preview branding for pinned LibreTube v32.1."""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

PACKAGE = "app.vistatube.mobile"
VERSION = "0.6.0-preview"

ICON = '''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp"
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#0A111E" android:pathData="M0,0h108v108h-108z"/>
    <path android:fillColor="#142B4A" android:pathData="M27,19 L81,19 C85.5,19 89,22.5 89,27 L89,81 C89,85.5 85.5,89 81,89 L27,89 C22.5,89 19,85.5 19,81 L19,27 C19,22.5 22.5,19 27,19 Z"/>
    <path android:fillColor="#66D9FF" android:pathData="M28,34 L40,34 L54,69 L68,34 L80,34 L59,80 L49,80 Z"/>
    <path android:fillColor="#FFFFFF" android:pathData="M45,42 L72,54 L45,67 Z"/>
</vector>
'''

COLORS = {
    "blue_md_theme_light_primary": "#005FCC",
    "blue_md_theme_light_onPrimary": "#FFFFFF",
    "blue_md_theme_light_primaryContainer": "#DBEAFF",
    "blue_md_theme_light_onPrimaryContainer": "#062245",
    "blue_md_theme_light_secondary": "#365D77",
    "blue_md_theme_light_secondaryContainer": "#D1E6F8",
    "blue_md_theme_light_background": "#F5F8FF",
    "blue_md_theme_light_surface": "#F5F8FF",
    "blue_md_theme_light_surfaceVariant": "#E2EAF3",
    "blue_md_theme_light_inversePrimary": "#79BCFF",
    "blue_md_theme_dark_primary": "#79BCFF",
    "blue_md_theme_dark_onPrimary": "#002D57",
    "blue_md_theme_dark_primaryContainer": "#124776",
    "blue_md_theme_dark_onPrimaryContainer": "#D6EBFF",
    "blue_md_theme_dark_secondary": "#9ACBEA",
    "blue_md_theme_dark_onSecondary": "#18374B",
    "blue_md_theme_dark_secondaryContainer": "#1B344A",
    "blue_md_theme_dark_onSecondaryContainer": "#D0E8F9",
    "blue_md_theme_dark_background": "#0C121E",
    "blue_md_theme_dark_onBackground": "#E9F0FB",
    "blue_md_theme_dark_surface": "#0C121E",
    "blue_md_theme_dark_onSurface": "#E9F0FB",
    "blue_md_theme_dark_surfaceVariant": "#253244",
    "blue_md_theme_dark_onSurfaceVariant": "#C0CEDF",
    "blue_md_theme_dark_outline": "#7E93AE",
    "blue_md_theme_dark_inverseOnSurface": "#0C121E",
    "blue_md_theme_dark_inverseSurface": "#E9F0FB",
    "blue_md_theme_dark_inversePrimary": "#005FCC",
}

def replace(path, old, new, matches=1):
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != matches:
        raise RuntimeError(f"{path}: expected {matches} matches of {old!r}, found {count}")
    path.write_text(content.replace(old, new), encoding="utf-8")

def apply(root):
    app = root / "app"
    gradle = app / "build.gradle.kts"
    if not gradle.is_file():
        raise FileNotFoundError(f"Not a LibreTube checkout: {root}")
    replace(gradle, 'applicationId = "com.github.libretube"', f'applicationId = "{PACKAGE}"')
    replace(gradle, 'versionCode = 72', 'versionCode = 6')
    replace(gradle, 'versionName = "32.1"', f'versionName = "{VERSION}"')
    replace(gradle, 'resValue("string", "app_name", "LibreTube")', 'resValue("string", "app_name", "VistaTube")')
    replace(gradle, 'resValue("string", "app_name", "LibreTube Debug")', 'resValue("string", "app_name", "VistaTube")')
    res = app / "src/main/res"
    strings = res / "values/strings.xml"
    replace(strings, '<string name="app_name" translatable="false">LibreTube</string>', '<string name="app_name" translatable="false">VistaTube</string>')
    helper = app / "src/main/java/com/github/libretube/helpers/ThemeHelper.kt"
    replace(helper, '"Libre<span  style=\'color:$hexColor\';>Tube</span>"', '"Vista<span style=\'color:$hexColor\';>Tube</span>"')
    replace(helper, 'accentColor = if (DynamicColors.isDynamicColorAvailable()) "my" else "blue"', 'accentColor = "blue"')
    activity = app / "src/main/java/com/github/libretube/ui/base/BaseActivity.kt"
    replace(activity, 'getString(PreferenceKeys.THEME_MODE, "A")', 'getString(PreferenceKeys.THEME_MODE, "D")')
    appearance = res / "xml/appearance_settings.xml"
    replace(appearance, 'app:defaultValue="A"', 'app:defaultValue="D"')
    replace(appearance, 'app:defaultValue="purple"', 'app:defaultValue="blue"')
    replace(appearance, '''        <Preference
            android:icon="@drawable/ic_frame"
            app:key="icon_change"
            app:title="@string/app_icon" />
''', '')
    settings = res / "xml/settings.xml"
    replace(settings, '''        <Preference
            android:icon="@drawable/ic_update"
            app:key="update"
            app:summary="@string/version"
            app:title="@string/update_summary" />
''', '')
    general = res / "xml/general_settings.xml"
    replace(general, '''        <SwitchPreferenceCompat
            android:defaultValue="false"
            android:icon="@drawable/ic_download_filled"
            app:key="automatic_update_checks"
            app:title="@string/show_updates"
            app:summary="@string/show_updates_summary" />
''', '')
    colors_path = res / "values/colors.xml"
    colors_text = colors_path.read_text(encoding="utf-8")
    for name, value in COLORS.items():
        pattern = rf'(<color\s+name="{re.escape(name)}">)#[0-9A-Fa-f]{{6,8}}(</color>)'
        colors_text, count = re.subn(pattern, lambda m: m.group(1) + value + m.group(2), colors_text)
        if count != 1:
            raise RuntimeError(f"Expected 1 occurrence of color {name}; found {count}")
    colors_path.write_text(colors_text, encoding="utf-8")
    icon = res / "drawable/vistatube_icon.xml"
    icon.write_text(ICON, encoding="utf-8")
    manifest = app / "src/main/AndroidManifest.xml"
    manifest_text = manifest.read_text(encoding="utf-8").replace('android:banner="@mipmap/ic_launcher"', 'android:banner="@drawable/vistatube_icon"')
    manifest_text, count = re.subn(r'android:(icon|roundIcon)="@mipmap/ic_launcher(?:_round)?"',
        lambda m: f'android:{m.group(1)}="@drawable/vistatube_icon"', manifest_text)
    if count < 4:
        raise RuntimeError(f"Unexpected Android manifest structure: {count} icons")
    manifest.write_text(manifest_text, encoding="utf-8")
    for theme in (res / "values/themes.xml", res / "values-night/themes.xml"):
        replace(theme, '@drawable/splash_icon', '@drawable/vistatube_icon')
    replace(root / "settings.gradle.kts", 'rootProject.name = "LibreTube"', 'rootProject.name = "VistaTube"')
    (root / "VISTATUBE_ATTRIBUTION.md").write_text(
        "# VistaTube attribution\n\nUnofficial modification of LibreTube v32.1.\n"
        "Upstream: https://github.com/libre-tube/LibreTube\n"
        "Original authors retain copyright; GPL-3.0-or-later.\n"
        "Not endorsed by LibreTube, YouTube or Google.\n", encoding="utf-8")
    for xml in (strings, appearance, settings, general, colors_path, icon, manifest):
        ET.parse(xml)
    print(f"VistaTube customizations applied: {PACKAGE}, {VERSION}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    apply(args.upstream.resolve())
