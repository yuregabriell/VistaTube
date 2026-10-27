#!/usr/bin/env python3
"""VistaTube 0.2: fixes player geometry + YouTube-like home/library/historical UI."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

A = "{http://schemas.android.com/apk/res/android}"
APP = "{http://schemas.android.com/apk/res-auto}"
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
ET.register_namespace("app", "http://schemas.android.com/apk/res-auto")
ET.register_namespace("tools", "http://schemas.android.com/tools")
ET.register_namespace("motion", "http://schemas.android.com/apk/res-auto")

def read(path):
    return path.read_text(encoding="utf-8")

def replace_exact(path, needle, replacement, n=1):
    s=read(path)
    if s.count(needle) != n:
        raise AssertionError(f"{path} expected {n} matches of {needle[:75]!r}, got {s.count(needle)}")
    path.write_text(s.replace(needle,replacement),encoding="utf-8")

def save_xml(path, root):
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(root,encoding="unicode"),encoding="utf-8")
    ET.parse(path)

def find_id(node, v):
    for el in node.iter():
        if el.get(A+"id") in ("@+id/"+v,"@id/"+v):
            return el
    raise AssertionError(f"Missing view {v}")

def style_player(res):
    # MotionLayout start state did not explicitly define the video container.
    # This can leave the 100dp end-state miniplayer surface attached to a
    # full-width black frame on some Android skins.
    scene = res/"xml/player_scene.xml"
    root=ET.parse(scene).getroot()
    start=find_id(root,"start")
    for element in list(start):
        if element.get(A+"id")=="@+id/main_container":
            raise AssertionError("Already patched")
    container=ET.Element("Constraint",{
        A+"id":"@+id/main_container",
        A+"layout_width":"match_parent",
        A+"layout_height":"0dp",
        APP+"layout_constraintDimensionRatio":"16:9",
        APP+"layout_constraintStart_toStartOf":"parent",
        APP+"layout_constraintEnd_toEndOf":"parent",
        APP+"layout_constraintTop_toTopOf":"parent",
    })
    start.insert(0,container)
    save_xml(scene,root)

    player = res.parent/"java/com/github/libretube/ui/fragments/PlayerFragment.kt"
    old = """        binding.playerMotionLayout.progress = 1F
        binding.playerMotionLayout.transitionToStart()"""
    new = """        // VistaTube: the initial player may inherit the 100dp miniplayer geometry
        // when MotionLayout transitions before its first measured frame.
        // Reset to the expanded constraint set after the first layout pass.
        binding.playerMotionLayout.progress = 1F
        binding.playerMotionLayout.transitionToStart()
        binding.playerMotionLayout.post {
            if (_binding != null && commonPlayerViewModel.isMiniPlayerVisible.value != true &&
                commonPlayerViewModel.isFullscreen.value != true
            ) {
                binding.playerMotionLayout.progress = 0f
                binding.playerMotionLayout.requestLayout()
                binding.player.requestLayout()
            }
        }"""
    replace_exact(player,old,new)

def style_home(res):
    layout=res/"layout/fragment_home.xml"
    root=ET.parse(layout).getroot()
    scroll=find_id(root,"scroll")
    column=next(x for x in scroll.iter() if x.tag=="LinearLayout" and x.get(A+"orientation")=="vertical")
    trending_title=find_id(column,"trendingTV")
    trending_list=find_id(column,"trendingRV")
    # Put the real (non-ad) video feed first, rather than bury it below five carousels.
    column.remove(trending_title)
    # trendingRV nested under RelativeLayout; move the whole wrapper.
    parent=next(x for x in column if trending_list in list(x.iter()))
    column.remove(parent)
    chips=ET.Element("HorizontalScrollView",{
        A+"layout_width":"match_parent",
        A+"layout_height":"wrap_content",
        A+"scrollbars":"none",
        A+"fillViewport":"false",
        A+"paddingStart":"10dp",
        A+"paddingEnd":"10dp",
        A+"paddingTop":"8dp",
        A+"paddingBottom":"3dp",
    })
    ET.SubElement(chips,"com.google.android.material.chip.ChipGroup",{
        A+"id":"@+id/home_category_group",
        A+"layout_width":"wrap_content",
        A+"layout_height":"wrap_content",
        APP+"singleSelection":"true",
        APP+"selectionRequired":"true",
        APP+"chipSpacingHorizontal":"7dp",
    })
    column.insert(0,chips)
    column.insert(1,parent)
    # Category heading follows primary feed; avoid repeated "trending" heading.
    column.insert(2,trending_title)
    trending_title.set(A+"visibility","gone")
    trending_list.set(APP+"spanCount","1")
    trending_list.set(A+"layout_width","match_parent")
    save_xml(layout,root)

    row=res/"layout/trending_row.xml"
    xml=ET.parse(row).getroot()
    thumbnail=find_id(xml,"thumbnailcard")
    thumbnail.set(A+"layout_marginStart","0dp")
    thumbnail.set(A+"layout_marginEnd","0dp")
    thumbnail.set(A+"layout_marginTop","0dp")
    thumbnail.set(APP+"cardCornerRadius","0dp")
    find_id(xml,"textView_title").set(A+"textSize","16sp")
    find_id(xml,"textView_channel").set(A+"textSize","13sp")
    save_xml(row,xml)

    home=res.parent/"java/com/github/libretube/ui/fragments/HomeFragment.kt"
    old="""        val trendingCategories = MediaServiceRepository.instance.getTrendingCategories()
        binding.trendingCategory.isVisible = trendingCategories.size > 1"""
    new="""        val trendingCategories = MediaServiceRepository.instance.getTrendingCategories()
        // Use real media-service categories, not hardcoded labels without content.
        val activeCategory = PreferenceHelper.getString(
            PreferenceKeys.TRENDING_CATEGORY, TrendingCategory.LIVE.name
        )
        binding.homeCategoryGroup.removeAllViews()
        trendingCategories.forEach { category ->
            val chip = com.google.android.material.chip.Chip(requireContext()).apply {
                text = getString(category.titleRes)
                isCheckable = true
                isChecked = category.name == activeCategory
                setOnClickListener {
                    PreferenceHelper.putString(PreferenceKeys.TRENDING_CATEGORY, category.name)
                    fetchHomeFeed()
                }
            }
            binding.homeCategoryGroup.addView(chip)
        }
        binding.trendingCategory.isVisible = false"""
    replace_exact(home,old,new)
    replace_exact(home,"makeVisible(binding.trendingRV, binding.trendingTV)",
                  "makeVisible(binding.trendingRV)")
    replace_exact(home,"trendingAdapter.submitList(trendingStreams.streams.take(10))",
                  "trendingAdapter.submitList(trendingStreams.streams.take(40))")

def style_library(res):
    layout=res/"layout/fragment_library.xml"
    root=ET.parse(layout).getroot()
    nested=next(x for x in root.iter() if x.tag=="androidx.core.widget.NestedScrollView")
    column=next(x for x in nested if x.tag=="LinearLayout")
    # Page identity and embedded horizontal watch-history row.
    header=ET.Element("LinearLayout",{
        A+"layout_width":"match_parent",A+"layout_height":"wrap_content",
        A+"orientation":"vertical",A+"paddingTop":"12dp",
    })
    ET.SubElement(header,"TextView",{
        A+"layout_width":"match_parent",A+"layout_height":"wrap_content",
        A+"paddingHorizontal":"16dp",A+"paddingBottom":"12dp",
        A+"text":"A tua biblioteca", A+"textSize":"26sp",A+"textStyle":"bold",
    })
    history_title=ET.SubElement(header,"TextView",{
        A+"id":"@+id/history_header",
        A+"layout_width":"match_parent",A+"layout_height":"wrap_content",
        A+"paddingHorizontal":"16dp",A+"paddingVertical":"12dp",
        A+"text":"Histórico  ›", A+"textSize":"20sp", A+"textStyle":"bold",
        A+"background":"?attr/selectableItemBackground",
        A+"visibility":"gone"
    })
    ET.SubElement(header,"androidx.recyclerview.widget.RecyclerView",{
        A+"id":"@+id/history_preview",A+"layout_width":"match_parent",
        A+"layout_height":"wrap_content",A+"clipToPadding":"false",
        A+"paddingHorizontal":"10dp",A+"nestedScrollingEnabled":"false",
        A+"visibility":"gone"
    })
    column.insert(0,header)
    # Large section title and generous touch targets in the library.
    playlists_title=next((e for e in column.iter() if e.tag=="TextView" and e.get(A+"text")=="@string/playlists"),None)
    if playlists_title is not None:
        playlists_title.set(A+"textSize","22sp")
        playlists_title.set(A+"paddingStart","16dp")
    save_xml(layout,root)

    lib=res.parent/"java/com/github/libretube/ui/fragments/LibraryFragment.kt"
    replace_exact(lib,"import com.github.libretube.db.DatabaseHolder",
        """import com.github.libretube.db.DatabaseHolder
import com.github.libretube.db.DatabaseHelper
import com.github.libretube.ui.adapters.VideoCardsAdapter
import androidx.recyclerview.widget.LinearLayoutManager""")
    replace_exact(lib,"    private val playlistBookmarkAdapter = PlaylistBookmarkAdapter()",
        """    private val playlistBookmarkAdapter = PlaylistBookmarkAdapter()
    private val historyPreviewAdapter = VideoCardsAdapter(columnWidthDp = 220f)""")
    replace_exact(lib,"        binding.bookmarksRecView.adapter = playlistBookmarkAdapter",
        """        binding.bookmarksRecView.adapter = playlistBookmarkAdapter
        binding.historyPreview.layoutManager = LinearLayoutManager(
            requireContext(), LinearLayoutManager.HORIZONTAL, false
        )
        binding.historyPreview.adapter = historyPreviewAdapter
        binding.historyHeader.setOnClickListener {
            findNavController().navigate(R.id.action_libraryFragment_to_watchHistoryFragment)
        }""")
    needle="""    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }"""
    new="""    override fun onResume() {
        super.onResume()
        loadHistoryPreview()
    }

    private fun loadHistoryPreview() {
        if (!PreferenceHelper.getBoolean(PreferenceKeys.WATCH_HISTORY_TOGGLE, true)) {
            _binding?.historyHeader?.isGone = true
            _binding?.historyPreview?.isGone = true
            return
        }
        viewLifecycleOwner.lifecycleScope.launch {
            val videos = withContext(Dispatchers.IO) {
                DatabaseHelper.getWatchHistoryPage(1, 12).map { it.toStreamItem() }
            }
            val ui = _binding ?: return@launch
            ui.historyHeader.isVisible = videos.isNotEmpty()
            ui.historyPreview.isVisible = videos.isNotEmpty()
            historyPreviewAdapter.submitList(videos)
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }"""
    replace_exact(lib,needle,new)

def style_downloads_history(res):
    dl=res/"layout/fragment_downloads.xml"
    root=ET.parse(dl).getroot()
    col=find_id(root,"downloads_container")
    col.insert(0,ET.Element("TextView",{
        A+"layout_width":"match_parent",A+"layout_height":"wrap_content",
        A+"paddingStart":"16dp",A+"paddingTop":"12dp",A+"paddingBottom":"12dp",
        A+"text":"Downloads",A+"textSize":"24sp",A+"textStyle":"bold"
    }))
    save_xml(dl,root)
    hist=res/"layout/fragment_watch_history.xml"
    root=ET.parse(hist).getroot()
    tb=find_id(root,"watch_history_collapsing_tb")
    # A vertical container avoids the title overlapping the existing filter chips.
    tb.tag="LinearLayout"
    tb.set(A+"orientation","vertical")
    tb.attrib.pop(APP+"titleCollapseMode",None)
    tb.insert(0,ET.Element("TextView",{
        A+"layout_width":"match_parent",A+"layout_height":"wrap_content",
        A+"paddingStart":"16dp",A+"paddingTop":"12dp",A+"paddingBottom":"6dp",
        A+"text":"Histórico",A+"textSize":"24sp",A+"textStyle":"bold",
    }))
    save_xml(hist,root)

def main(path):
    root=path.resolve()/"app/src/main"
    res=root/"res"
    style_player(res)
    style_home(res)
    style_library(res)
    style_downloads_history(res)
    print("VistaTube UI 0.2 applied: player, home, library, history, downloads")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    main(parser.parse_args().upstream)
