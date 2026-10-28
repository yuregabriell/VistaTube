#!/usr/bin/env python3
"""VistaTube 0.12: ensure Home actually scrolls inside the available viewport."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

A = "{http://schemas.android.com/apk/res/android}"
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
ET.register_namespace("app", "http://schemas.android.com/apk/res-auto")
ET.register_namespace("tools", "http://schemas.android.com/tools")

def patch(root: Path):
    xml = root / "app/src/main/res/layout/fragment_home.xml"
    tree = ET.parse(xml)
    frame = tree.getroot()
    swipe = next((x for x in frame if x.tag.endswith("CustomSwipeToRefresh")), None)
    if swipe is None:
        raise AssertionError("No SwipeRefreshLayout inside the Home root")
    scroll = next((x for x in swipe if x.tag == "ScrollView"), None)
    if scroll is None or scroll.get(A+"id") != "@+id/scroll":
        raise AssertionError("Home ScrollView missing or unexpectedly changed")

    # Prevent content-sized ScrollView from expanding past the NavHost's
    # viewport. Both the direct SwipeRefreshLayout child and the ScrollView
    # must be bounded by the visible fragment's height.
    swipe.set(A+"layout_height", "match_parent")
    scroll.set(A+"layout_height", "match_parent")
    scroll.set(A+"fillViewport", "true")
    scroll.set(A+"overScrollMode", "ifContentScrolls")

    column = next((x for x in scroll if x.tag == "LinearLayout"), None)
    if column is None:
        raise AssertionError("Home content must be a direct ScrollView child")
    column.set(A+"layout_height", "wrap_content")
    column.set(A+"paddingBottom", "24dp")

    recommended = next((x for x in column if x.get(A+"id")=="@+id/recommendedRV"),None)
    if recommended is None:
        raise AssertionError("Cannot find the personalised recommendation list")
    recommended.set(A+"layout_height","wrap_content")
    recommended.set(A+"nestedScrollingEnabled","false")

    # RecyclerView uses parent ScrollView as its sole vertical scroller. This
    # ensures nested gestures reach the ScrollView and its near-end listener.
    for item in column.iter():
        if item.tag == "androidx.recyclerview.widget.RecyclerView":
            item.set(A+"nestedScrollingEnabled","false")

    xml.write_text('<?xml version="1.0" encoding="utf-8"?>\n'
                   + ET.tostring(frame,encoding="unicode"),encoding="utf-8")
    verify=ET.parse(xml).getroot()
    sw=next(x for x in verify if x.tag.endswith("CustomSwipeToRefresh"))
    sc=next(x for x in sw if x.tag=="ScrollView")
    assert sw.get(A+"layout_height")=="match_parent"
    assert sc.get(A+"layout_height")=="match_parent"
    assert sc.get(A+"fillViewport")=="true"

    # An explicit scroll listener must already be present, otherwise a
    # scrollable list would appear but the ten-at-a-time pager would not run.
    home=root/"app/src/main/java/com/github/libretube/ui/fragments/HomeFragment.kt"
    text=home.read_text(encoding="utf-8")
    assert "binding.scroll.setOnScrollChangeListener" in text
    assert "homeViewModel.loadMoreRecommendations()" in text
    print("Verified bounded SwipeRefreshLayout/ScrollView, nested RV off, "
          "and existing infinite-scroll callback.")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    patch(parser.parse_args().upstream.resolve())
