#!/usr/bin/env python3
"""VistaTube 0.5: one relevant Home feed, fresh subscriptions, bounded topics."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

ANDROID="{http://schemas.android.com/apk/res/android}"
ET.register_namespace("android","http://schemas.android.com/apk/res/android")
ET.register_namespace("app","http://schemas.android.com/apk/res-auto")
ET.register_namespace("tools","http://schemas.android.com/tools")

def once(path,old,new):
    contents=path.read_text(encoding="utf-8")
    n=contents.count(old)
    if n!=1:
        raise AssertionError(f"{path}: expected 1 match, got {n} for {old[:85]!r}")
    path.write_text(contents.replace(old,new),encoding="utf-8")

def apply(root):
    src=root/"app/src/main"
    base=src/"java/com/github/libretube"
    engine=base/"helpers/VistaRecommendationEngine.kt"
    vm=base/"ui/models/HomeViewModel.kt"
    home=base/"ui/fragments/HomeFragment.kt"
    subs=base/"ui/fragments/SubscriptionsFragment.kt"
    home_xml=src/"res/layout/fragment_home.xml"

    # Recommendation priority is explicit subscription and watch/search affinity.
    once(engine,"""             searches: List<String> = emptyList(),
             limit: Int = 180): List<StreamItem> {""",
         """             searches: List<String> = emptyList(),
             subscribedChannels: Set<String> = emptySet(),
             limit: Int = 180): List<StreamItem> {""")
    once(engine,"""                val creatorScore = (creators[channel] ?: 0.0) * 2.25""",
         """                // Strong affinity for existing subscriptions; still allow discovery
                // outside them when topics and channel interests match.
                val subscriptionScore = if (channel in subscribedChannels) 12.0 else 0.0
                val creatorScore = (creators[channel] ?: 0.0) * 4.0 + subscriptionScore""")
    once(engine,"""                } else topical + description + creatorScore + freshness""",
         """                } else topical * 2.0 + description + creatorScore + freshness""")
    once(engine,"""            if (channel.isNotEmpty() && (perChannel[channel] ?: 0) >= 5) continue""",
         """            // Keep diversity but do not arbitrarily stop after only a few
            // favourite-channel videos.
            if (channel.isNotEmpty() && (perChannel[channel] ?: 0) >= 24) continue""")

    once(vm,"""    private var recommendationSearches = emptyList<String>()""",
         """    private var recommendationSearches = emptyList<String>()
    private var recommendationSubscribedChannels = emptySet<String>()""")
    # prevent unrelated generic film results before a user has local watch or search signals
    once(vm,'''        val seeds = if (distinct.isEmpty()) listOf(
            "entretenimento em português",
            "gaming brasileiro",
            "música brasileira",
            "humor português",
            "ciência tecnologia em português",
            "podcast brasileiro"
        ) else distinct''', '''        val seeds = distinct
        if (seeds.isEmpty()) return emptyList()''')
    # Replace the title-derived queries by delimiters, not the full regex
    # literal (Python/Kotlin escaping differs by source version).
    source = vm.read_text(encoding="utf-8")
    left = source.index("        val titles = history.asSequence()")
    right = source.index("        val distinct =", left)
    vm.write_text(source[:left] + "        val titles = emptyList<String>()\n" +
                  source[right:], encoding="utf-8")
    once(vm,'''        recommendationSearches = searches
        val queries = makeQueries(history, searches)''',
         '''        recommendationSearches = searches
        val subscriptionInfo = withContext(Dispatchers.IO) {
            runCatching { SubscriptionHelper.getSubscriptions() }.getOrDefault(emptyList())
        }
        val subscriptionNames = subscriptionInfo.map { it.name.lowercase().trim() }.toSet()
        recommendationSubscribedChannels = subscriptionNames
        // A separate feed retrieval is required even when the user disabled the
        // old Featured widget on Home; never gate recommendations on that widget.
        val subscriptionsFeed = withContext(Dispatchers.IO) {
            runCatching { SubscriptionHelper.getFeed(forceRefresh = refreshIndex > 1) }
                .getOrDefault(emptyList())
        }
        if (generation != recommendationsGeneration) return
        val queries = makeQueries(history, searches + subscriptionInfo.map { it.name })''')
    once(vm,'''        val fallback = if (queries.isEmpty() || discovered.isEmpty() && related.isEmpty()) {
            feed.value.orEmpty() + trending.value?.second?.streams.orEmpty()
        } else {
            feed.value.orEmpty()
        }''',
         '''        // Subscription activity is the primary source; unrelated global
        // trending is deliberately not inserted into For You.
        val fallback = subscriptionsFeed + feed.value.orEmpty()''')
    once(vm,'''        val pool = older.flatMap { it.second } + discovered + related + fallback + recommendedItems''',
         '''        val pool = fallback + related + older.flatMap { it.second } + discovered + recommendedItems''')
    once(vm,'''            recommendedItems, recommendationHistory, recommendationSearches, 180''',
         '''            recommendedItems, recommendationHistory,
            recommendationSearches, recommendationSubscribedChannels, 180''')
    # Stop tiny feed: initial subscription feed and discovery pages are rendered
    # together, plus loadMore keeps fetching pages while available.
    once(home,'''            feed.observe(viewLifecycleOwner, ::showFeed)
            bookmarks.observe(viewLifecycleOwner, ::showBookmarks)
            playlists.observe(viewLifecycleOwner, ::showPlaylists)''',
         '''            // VistaTube has one unified discovery feed: old Featured/Highlights,
            // bookmarks and playlist carousels belong to Library, not Home.''')
    once(home,'''            trending.observe(viewLifecycleOwner, ::showTrending)''',
         '''            // Global trending is not a source of unrelated Home recommendations.''')
    once(home,'''        val trendingCategories = MediaServiceRepository.instance.getTrendingCategories()''',
         '''        val trendingCategories = MediaServiceRepository.instance.getTrendingCategories()
        // Keep old category controls in the source for settings compatibility,
        // but display a clean For You feed instead of Trending/Featured duplicates.''')
    once(home,'''        binding.trendingRV.adapter = trendingAdapter''',
         '''        binding.trendingRV.adapter = trendingAdapter
        binding.featuredTV.isGone = true
        binding.featuredRV.isGone = true
        binding.trendingTV.isGone = true
        binding.trendingRV.isGone = true
        binding.bookmarksTV.isGone = true
        binding.bookmarksRV.isGone = true
        binding.playlistsTV.isGone = true
        binding.playlistsRV.isGone = true''')
    once(home,'''        binding.trendingRV.isGone = hasVideos
        recommendedAdapter.submitList(videos.orEmpty())''',
         '''        binding.trendingRV.isGone = true
        recommendedAdapter.submitList(videos.orEmpty())''')

    # Hide the empty legacy category ribbon without removing binding IDs.
    tree=ET.parse(home_xml)
    column=next(x for x in tree.iter() if x.tag=="LinearLayout" and x.get(ANDROID+"orientation")=="vertical"
                and any(el.get(ANDROID+"id")=="@+id/recommendedRV" for el in x.iter()))
    chip=next(x for x in column if any(el.get(ANDROID+"id")=="@+id/home_category_group" for el in x.iter()))
    chip.set(ANDROID+"visibility","gone")
    # For You begins immediately after the short Continue Watching group.
    head=next(x for x in column if x.get(ANDROID+"id")=="@+id/recommended_header")
    head.set(ANDROID+"text","Para ti")
    head.set(ANDROID+"paddingTop","14dp")
    home_xml.write_text('<?xml version="1.0" encoding="utf-8"?>\n'
                        +ET.tostring(tree.getroot(),encoding="unicode"),encoding="utf-8")
    ET.parse(home_xml)

    # Force a feed refresh every time the user re-enters Subscriptions; no
    # duplicate initial load. Refresh still respects the existing user filters.
    once(subs,'''        if (viewModel.videoFeed.value == null) {
            viewModel.fetchFeed(requireContext(), forceRefresh = false)
        }''',
         '''        // Feed refresh happens in onResume on each tab visit.''')
    once(subs,'''    private fun setupSortAndFilter() {''',
         '''    override fun onResume() {
        super.onResume()
        // New uploads are fetched automatically when opening this tab.
        viewModel.fetchFeed(requireContext(), forceRefresh = true)
        viewModel.fetchSubscriptions(requireContext())
    }

    private fun setupSortAndFilter() {''')
    print("VistaTube v0.5: one subscription-first For You feed, auto-refresh Subscriptions")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    apply(parser.parse_args().upstream.resolve())
