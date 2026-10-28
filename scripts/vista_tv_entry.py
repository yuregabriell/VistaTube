#!/usr/bin/env python3
"""VistaTube native TV entry, preserving the original LibreTube phone UI and data."""
import argparse
from pathlib import Path
import shutil

def patch(root: Path) -> None:
    source = root / "app/src/main/java/com/github/libretube/ui/activities"
    source.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve().parents[1] / "patches/VistaTubeTvActivity.java",
                 source / "VistaTubeTvActivity.java")
    manifest = root / "app/src/main/AndroidManifest.xml"
    xml = manifest.read_text(encoding="utf-8")
    category = '                <category android:name="android.intent.category.LEANBACK_LAUNCHER" />'
    assert category in xml, "No upstream TV launchers found"
    xml = xml.replace(category, "")
    marker = "    <application"
    assert xml.count(marker) == 1
    # Insert the TV entry after opening application tag rather than before it.
    at = xml.index(">", xml.index(marker)) + 1
    entry = '''
        <!-- TV-native remote-first start page; phones keep the original aliases. -->
        <activity
            android:name=".ui.activities.VistaTubeTvActivity"
            android:exported="true"
            android:screenOrientation="landscape"
            android:theme="@style/BaseTheme">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LEANBACK_LAUNCHER" />
            </intent-filter>
        </activity>
'''
    xml = xml[:at] + entry + xml[at:]
    assert xml.count("android.intent.category.LEANBACK_LAUNCHER") == 1
    manifest.write_text(xml, encoding="utf-8")

    activity = source / "MainActivity.kt"
    code = activity.read_text(encoding="utf-8")
    anchor = '''        navController.graph = navController.navInflater.inflate(R.navigation.nav).also {
            it.setStartDestination(startFragmentId)
        }'''
    assert code.count(anchor) == 1, "MainActivity graph initialization changed"
    code = code.replace(anchor, anchor + '''
        vistaNavigateFromTv(intent)
''', 1)
    anchor = "    override fun onNewIntent(intent: Intent) {"
    assert code.count(anchor) == 1, "MainActivity new intent handling changed"
    tv_method = '''
    /**
     * The TV Hub uses only the existing LibreTube navigation and local data.
     * It never substitutes generated or third-party video recommendations.
     */
    private fun vistaNavigateFromTv(incoming: Intent?) {
        if (!this::navController.isInitialized) return
        when (incoming?.getStringExtra("vista_tv_section")) {
            "subscriptions" -> navController.navigate(R.id.subscriptionsFragment)
            "library" -> navController.navigate(R.id.libraryFragment)
            "search" -> {
                val q = incoming.getStringExtra("vista_tv_query")?.trim().orEmpty()
                if (q.isNotEmpty()) navController.navigate(NavDirections.showSearchResults(q.take(100)))
                else navController.navigate(R.id.searchFragment)
            }
        }
    }

'''
    code = code.replace(anchor, tv_method + anchor, 1)
    anchor = '''        this.intent = intent
        loadIntentData()'''
    assert code.count(anchor) == 1, "MainActivity onNewIntent body changed"
    code = code.replace(anchor, '''        this.intent = intent
        vistaNavigateFromTv(intent)
        loadIntentData()''', 1)
    activity.write_text(code, encoding="utf-8")
    print("VistaTube remote-ready TV entry and native navigation installed, mobile unaffected.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    patch(args.upstream.resolve())
