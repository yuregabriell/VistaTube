#!/usr/bin/env python3
"""VistaTube 0.4: personalised, refreshed and paginated discovery feed."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

ANDROID = "{http://schemas.android.com/apk/res/android}"
AUTO = "{http://schemas.android.com/apk/res-auto}"
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
ET.register_namespace("app", "http://schemas.android.com/apk/res-auto")
ET.register_namespace("tools", "http://schemas.android.com/tools")

def replace_once(path, old, new):
    data = path.read_text(encoding="utf-8")
    if data.count(old) != 1:
        raise AssertionError(f"{path}: expected 1 match of {old[:100]!r}; found {data.count(old)}")
    path.write_text(data.replace(old, new), encoding="utf-8")

def apply(root):
    main = root/"app/src/main"
    base = main/"java/com/github/libretube"
    vm = base/"ui/models/HomeViewModel.kt"
    engine = base/"helpers/VistaRecommendationEngine.kt"
    home = base/"ui/fragments/HomeFragment.kt"
    layout = main/"res/layout/fragment_home.xml"

    replace_once(engine, '''             history: List<WatchHistoryItem>,
             limit: Int = 36): List<StreamItem> {''',
        '''             history: List<WatchHistoryItem>,
             searches: List<String> = emptyList(),
             limit: Int = 180): List<StreamItem> {''')
    replace_once(engine, '''        val now = System.currentTimeMillis()''',
        '''        // Search terms are the strongest explicit user-interest signal.
        searches.take(12).forEachIndexed { index, search ->
            val importance = 4.0 / (1.0 + index / 5.0)
            terms(search).forEach { token ->
                topics[token] = (topics[token] ?: 0.0) + importance
            }
        }
        val now = System.currentTimeMillis()''')
    replace_once(engine, '''            if (channel.isNotEmpty() && (perChannel[channel] ?: 0) >= 3) continue''',
        '''            if (channel.isNotEmpty() && (perChannel[channel] ?: 0) >= 5) continue''')

    replace_once(vm, '''import com.github.libretube.db.obj.PlaylistBookmark''',
        '''import com.github.libretube.db.obj.PlaylistBookmark
import com.github.libretube.db.obj.WatchHistoryItem
import com.github.libretube.extensions.toID''')
    replace_once(vm, '''    private var loadHomeJob: Job? = null''',
        '''    private var loadHomeJob: Job? = null
    private var recommendedItems = mutableListOf<StreamItem>()
    private var recommendationHistory = emptyList<WatchHistoryItem>()
    private var recommendationSearches = emptyList<String>()
    private var pendingPages = mutableListOf<Pair<String, String>>()
    private var recommendationsLoadingMore = false
    private var recommendationsGeneration = 0
    private var refreshIndex = 0''')
    replace_once(vm, '''        isLoading.value = true

        loadHomeJob?.cancel()''',
        '''        isLoading.value = true
        refreshIndex++
        recommendationsGeneration++
        recommendationsLoadingMore = false

        loadHomeJob?.cancel()''')
    start = vm.read_text(encoding="utf-8")
    a = start.index("    private suspend fun loadPersonalizedRecommendations() {")
    b = start.index("    private suspend fun loadTrending(context: Context) {", a)
    replacement = '''    private fun makeQueries(
        history: List<WatchHistoryItem>,
        searches: List<String>
    ): List<String> {
        // Prefer explicit recent searches; then creators and strong title phrases.
        val searchQueries = searches.asSequence()
            .map { it.trim() }
            .filter { it.length >= 3 && it.length <= 90 }
            .take(10)
            .toList()
        val creators = history.asSequence()
            .mapNotNull { it.uploader?.trim() }
            .filter { it.length in 3..75 }
            .distinct()
            .take(7)
            .toList()
        val titles = history.asSequence()
            .mapNotNull { it.title?.trim() }
            .map { it.replace(Regex("[^\\\\p{L}\\\\p{N} ]"), " ") }
            .map { it.split(Regex("\\\\s+")).filter { w -> w.length >= 3 }.take(5).joinToString(" ") }
            .filter { it.length >= 6 }
            .distinct()
            .take(7)
            .toList()
        val distinct = (searchQueries + creators + titles)
            .distinctBy { it.lowercase() }
        // Fresh installs have no local signals yet. Start with a varied
        // Portuguese-language discovery feed, never just 1–2 live trends.
        val seeds = if (distinct.isEmpty()) listOf(
            "entretenimento em português",
            "gaming brasileiro",
            "música brasileira",
            "humor português",
            "ciência tecnologia em português",
            "podcast brasileiro"
        ) else distinct

        // Rotating topics avoids refreshing the exact same set every time.
        val offset = (refreshIndex - 1).coerceAtLeast(0) % seeds.size
        val rotated = seeds.drop(offset) + seeds.take(offset)
        return rotated.take(6)
    }

    private suspend fun loadPersonalizedRecommendations() {
        if (!PreferenceHelper.getBoolean("vistatube_recommendations", true)) {
            recommendedItems.clear()
            pendingPages.clear()
            recommendations.value = emptyList()
            return
        }
        val generation = recommendationsGeneration
        val historyAndSearches = withContext(Dispatchers.IO) {
            DatabaseHelper.getWatchHistoryPage(1, 60) to
                DatabaseHolder.Database.searchHistoryDao().getAll()
                    .asReversed().map { it.query }.take(20)
        }
        if (generation != recommendationsGeneration) return
        val (history, searches) = historyAndSearches
        recommendationHistory = history
        recommendationSearches = searches
        val queries = makeQueries(history, searches)
        val api = MediaServiceRepository.instance

        // Collect multiple independent searches, never only two related videos.
        // Search queries go to the selected video-search backend; raw history stays local.
        val searchesResult = withContext(Dispatchers.IO) {
            queries.map { query ->
                async {
                    runCatching {
                        val result = api.getSearchResults(query, "videos")
                        val items = result.items
                            .filter { it.type == StreamItem.TYPE_STREAM }
                            .map { it.toStreamItem() }
                        Triple(query, items, result.nextpage)
                    }.getOrNull()
                }
            }.awaitAll().filterNotNull()
        }
        if (generation != recommendationsGeneration) return
        val newPages = searchesResult.mapNotNull { (query, _, page) ->
            page?.takeIf { it.isNotBlank() }?.let { query to it }
        }
        // Complement with related videos and subscribed creators, but avoid
        // inserting irrelevant generic trending when the user has interests.
        val related = withContext(Dispatchers.IO) {
            history.take(3).map { it.videoId }.distinct().map { id ->
                async {
                    runCatching { api.getStreams(id).relatedStreams }.getOrDefault(emptyList())
                }
            }.awaitAll().flatten()
        }
        if (generation != recommendationsGeneration) return
        val discovered = searchesResult.flatMap { it.second }
        val fallback = if (queries.isEmpty() || discovered.isEmpty() && related.isEmpty()) {
            feed.value.orEmpty() + trending.value?.second?.streams.orEmpty()
        } else {
            feed.value.orEmpty()
        }
        // On refresh, add one page of older results when available, so a pull
        // refresh is useful even when the search backend returns cached results.
        val older = withContext(Dispatchers.IO) {
            pendingPages.take(2).map { (query, token) ->
                async {
                    runCatching {
                        val result = api.getSearchResultsNextPage(query, "videos", token)
                        Triple(query, result.items
                            .filter { it.type == StreamItem.TYPE_STREAM }
                            .map { it.toStreamItem() }, result.nextpage)
                    }.getOrNull()
                }
            }.awaitAll().filterNotNull()
        }
        if (generation != recommendationsGeneration) return
        pendingPages = (newPages + older.mapNotNull { (query, _, token) ->
            token?.takeIf { it.isNotBlank() }?.let { query to it }
        }).toMutableList()
        // Keep already-discovered candidates to provide continuity across
        // refreshes, while newly queried results lead the next ranking.
        val pool = older.flatMap { it.second } + discovered + related + fallback + recommendedItems
        recommendedItems = pool.distinctBy { it.url.orEmpty().toID() }.take(350).toMutableList()
        updateRecommendedVideos()
    }

    private fun updateRecommendedVideos() {
        recommendations.value = VistaRecommendationEngine.rank(
            recommendedItems, recommendationHistory, recommendationSearches, 180
        )
    }

    fun loadMoreRecommendations() {
        if (recommendationsLoadingMore || pendingPages.isEmpty() ||
            !PreferenceHelper.getBoolean("vistatube_recommendations", true)
        ) return
        val generation = recommendationsGeneration
        recommendationsLoadingMore = true
        viewModelScope.launch {
            try {
                // Two result pages each time the user approaches the end.
                val requested = pendingPages.take(2)
                pendingPages = pendingPages.drop(2).toMutableList()
                val api = MediaServiceRepository.instance
                val newResults = withContext(Dispatchers.IO) {
                    requested.map { (query, token) ->
                        async {
                            runCatching {
                                val result = api.getSearchResultsNextPage(query, "videos", token)
                                Triple(query, result.items
                                    .filter { it.type == StreamItem.TYPE_STREAM }
                                    .map { it.toStreamItem() }, result.nextpage)
                            }.getOrNull()
                        }
                    }.awaitAll().filterNotNull()
                }
                if (generation != recommendationsGeneration) return@launch
                for ((query, items, next) in newResults) {
                    recommendedItems.addAll(items)
                    if (!next.isNullOrBlank()) pendingPages.add(query to next)
                }
                recommendedItems = recommendedItems
                    .distinctBy { it.url.orEmpty().toID() }
                    .take(350).toMutableList()
                updateRecommendedVideos()
            } finally {
                if (generation == recommendationsGeneration) recommendationsLoadingMore = false
            }
        }
    }

'''
    vm.write_text(start[:a]+replacement+start[b:],encoding="utf-8")
    replace_once(vm,'''        val videos = DatabaseHelper.getWatchHistoryPage(1, 20)''',
        '''        val videos = DatabaseHelper.getWatchHistoryPage(1, 12)''')
    replace_once(vm, '''            .filterUnwatched(videos.map { it.toStreamItem() })''',
        '''            .filterUnwatched(videos.map { it.toStreamItem() }).take(2)''')
    # Re-fetch subscribed feed on explicit pull-to-refresh; the original cached
    # video feed was reused forever, making refresh appear broken.
    replace_once(vm, '''SubscriptionHelper.getFeed(forceRefresh = false)''',
        '''SubscriptionHelper.getFeed(forceRefresh = refreshIndex > 1)''')

    replace_once(home, '''        binding.watchingRV.adapter = watchingAdapter''',
        '''        binding.watchingRV.adapter = watchingAdapter
        binding.scroll.setOnScrollChangeListener { _, _, scrollY, _, _ ->
            // recommendedRV lives in the ScrollView's direct vertical child.
            // Advance the search page cursors near the end of the For You feed.
            if (binding.recommendedRV.isVisible &&
                scrollY + binding.scroll.height >= binding.recommendedRV.bottom - 550
            ) {
                homeViewModel.loadMoreRecommendations()
            }
        }''')
    replace_once(home, '''        makeVisible(binding.watchingRV, binding.watchingTV)
        watchingAdapter.submitList(unwatchedVideos)''',
        '''        binding.watchingRV.isVisible = unwatchedVideos.isNotEmpty()
        binding.watchingTV.isVisible = unwatchedVideos.isNotEmpty()
        watchingAdapter.submitList(unwatchedVideos.take(2))''')
    # After initial HomeViewModel load, the remaining sections may still include
    # a small trending fallback. Hide the duplication for a populated For You feed.
    replace_once(home, '''        makeVisible(binding.trendingRV)
        trendingAdapter.submitList(trendingStreams.streams.take(40))''',
        '''        binding.trendingRV.isVisible = recommendations.value.isNullOrEmpty()
        trendingAdapter.submitList(trendingStreams.streams.take(40))''') if False else None

    tree = ET.parse(layout)
    scroll = next(x for x in tree.iter() if x.get(ANDROID+"id")=="@+id/scroll")
    column = next(x for x in scroll.iter() if x.tag=="LinearLayout" and x.get(ANDROID+"orientation")=="vertical")
    watchTitle = next(x for x in column if x.get(ANDROID+"id")=="@+id/watchingTV")
    watchRecycler = next(x for x in column if x.get(ANDROID+"id")=="@+id/watchingRV")
    column.remove(watchTitle)
    column.remove(watchRecycler)
    column.insert(0,watchTitle)
    column.insert(1,watchRecycler)
    # A subtle divider between the recent 1–2 unfinished videos and discovery.
    watchTitle.set(ANDROID+"paddingTop","12dp")
    watchTitle.set(ANDROID+"paddingBottom","4dp")
    layout.write_text('<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(tree.getroot(),encoding="unicode"),encoding="utf-8")
    ET.parse(layout)
    print("VistaTube 0.4: recent 2 continue-watching, search/history discovery with paginated refresh")

if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    apply(parser.parse_args().upstream.resolve())
