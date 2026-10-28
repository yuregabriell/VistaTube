#!/usr/bin/env python3
"""Android TV landscape adaptation for VistaTube; leaves mobile UI and data intact."""
from pathlib import Path
import sys
root = Path(sys.argv[1])
main = root / "app/src/main/java/com/github/libretube/ui/activities/MainActivity.kt"
source = main.read_text(encoding="utf-8")
needle = "        super.onCreate(savedInstanceState)\n"
assert source.count(needle) == 1
source = source.replace(needle, needle + '''
        // TV uses native widescreen landscape; on phones keep the original orientation.
        if ((resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_TYPE_MASK) ==
            android.content.res.Configuration.UI_MODE_TYPE_TELEVISION) {
            requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        }
''', 1)
main.write_text(source, encoding="utf-8")
gradle = root / "app/build.gradle.kts"
text = gradle.read_text(encoding="utf-8")
# Keep the prior VistaTube versioning and source pin.
assert "0.14.0-preview" in text
gradle.write_text(text.replace("0.14.0-preview", "0.15.0-preview"), encoding="utf-8")
print("VistaTube: native Leanback TV icon retained; widescreen in TV only.")
