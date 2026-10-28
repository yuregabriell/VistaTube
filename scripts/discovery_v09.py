#!/usr/bin/env python3
"""VistaTube 0.9: discover + personalised feed, ten videos per scroll page.

Applied after every earlier VistaTube patch to the pinned LibreTube v32.1 tree.
Unlike v0.4-v0.8, never holds the UI for a giant single recommendation request.
"""
from pathlib import Path
import argparse

def swap(path, old, new):
    text=path.read_text(encoding="utf-8")
    count=text.count(old)
    if count!=1:
        raise AssertionError(f"{path}: expected one match of {old[:95]!r}; found {count}")
    path.write_text(text.replace(old,new),encoding="utf-8")

# Kotlin inserted verbatim into HomeViewModel after v0.8.
DISCOVERY = r'''    // Ten results at a time. User scrolling, not background requests,
    // is the only thing that can increase this displayed count.
    private var vistaVisibleCount = 10
    private var vistaLastScrollAt = 0L
    private var vistaBusyDiscovering = false
    private var vistaSubscribedVideos = mutableListOf<StreamItem>()
    private var vistaRelatedVideos = mutableListOf<StreamItem>()
    private var vistaExplorationVideos = mutableListOf<StreamItem>()
    private var vistaQueryQueue = mutableListOf<String>()

    private val vistaStopwords = setOf(
        "video", "videos", "episodio", "completo", "completa", "oficial",
        "reaction", "reagindo", "parte", "jogando", "assistindo", "dublado",
        "legendado", "trailer", "canal", "sobre", "para", "com", "como",
        "essa", "esse", "isso", "uma", "uns", "das", "dos", "que",
        "agora", "hoje", "ontem", "muito", "mais", "the", "and",
        "this", "with", "full", "new", "latest", "what", "would"
    )

    private fun vistaTopics(history: List<WatchHistoryItem>): List<String> {
        val textTopics = history.asSequence().take(35).mapNotNull { item ->
            val useful = item.title.orEmpty()
                .lowercase()
                .replace(Regex("[^a-z0-9à-ÿ]+"), " ")
                .split(" ")
                .filter { it.length >= 4 && it !in vistaStopwords && it.toIntOrNull() == null }
                .take(3)
            useful.joinToString(" ").takeIf { it.length >= 6 }
        }.distinct().take(12).toList()
        return textTopics
    }

    private fun vistaQueries(
        history: List<WatchHistoryItem>,
        searches: List<String>,
        channelNames: List<String>
    ): List<String> {
        // Explicit searches and watched-video topics discover videos from new
        // creators, not just from already subscribed channels.
        val typed = searches.asSequence()
            .map { it.trim() }
            .filter { it.length in 3..90 }
            .take(10).toList()
        val themes = vistaTopics(history)
        val relatedCreators = history.mapNotNull { it.uploader?.trim() }
            .filter { it.length in 3..65 }.distinct().take(6)
        val channels = channelNames.filter { it.length in 3..65 }.take(8)
        val sources = listOf(typed, themes, relatedCreators, channels)
        val ordered = mutableListOf<String>()
        for (index in 0 until sources.maxOfOrNull { it.size }.orEmptyInt()) {
            for (source in sources) if (index < source.size) ordered.add(source[index])
        }
        return ordered.distinctBy { it.lowercase() }.take(32)
    }

    private fun Int?.orEmptyInt(): Int = this ?: 0

    private fun vistaAdd(
        destination: MutableList<StreamItem>,
        items: List<StreamItem>
    ) {
        val known = destination.map { it.url.orEmpty().toID() }.toHashSet()
        for (video in items) {
            val id = video.url.orEmpty().toID()
            if (id.isNotBlank() && id !in known && !video.isUpcoming) {
                destination.add(video)
                known.add(id)
            }
        }
        if (destination.size > 300) {
            destination.subList(300, destination.size).clear()
        }
    }

    private fun vistaRank(list: List<StreamItem>): List<StreamItem> =
        VistaRecommendationEngine.rank(
            list, recommendationHistory, recommendationSearches,
            recommendationSubscribedChannels, 250
        )

    private fun updateRecommendedVideos() {
        // Interleave creators the user follows, related watched-video topics,
        // and wider exploration. When one source is empty, other sources fill
        // the ten-result batch. Each category preserves relevance ranking.
        val buckets = listOf(
            vistaRank(vistaSubscribedVideos),
            vistaRank(vistaRelatedVideos),
            vistaRank(vistaExplorationVideos)
        )
        val positions = IntArray(3)
        val pattern = intArrayOf(0, 1, 2, 0, 1, 2, 0, 2, 1, 2)
        val combined = mutableListOf<StreamItem>()
        val seen = mutableSetOf<String>()
        var round = 0
        while (combined.size < 300 && round < 900) {
            val priority = pattern[round % pattern.size]
            var picked = false
            for (offset in 0..2) {
                val bucket = (priority + offset) % 3
                val options = buckets[bucket]
                while (positions[bucket] < options.size) {
                    val item = options[positions[bucket]++]
                    val id = item.url.orEmpty().toID()
                    if (id.isBlank() || !seen.add(id)) continue
                    combined.add(item)
                    picked = true
                    break
                }
                if (picked) break
            }
            if (!picked) break
            round++
        }
        recommendedItems = combined.toMutableList()
        recommendations.value = combined.take(vistaVisibleCount)
    }

    private suspend fun vistaSearch(
        query: String, nextPage: String? = null
    ): Triple<String, List<StreamItem>, String?>? {
        val api = MediaServiceRepository.instance
        var result = withTimeoutOrNull(7_000L) {
            runCatching {
                if (nextPage.isNullOrBlank()) api.getSearchResults(query, "videos")
                else api.getSearchResultsNextPage(query, "videos", nextPage)
            }.getOrNull()
        }
        // Piped instances can return zero/very few hits while the NewPipe
        // extractor still has results. Fall back only when the first source
        // is sparse; never discard successful primary results.
        if (result == null || result.items.size < 4) {
            val backup = withTimeoutOrNull(7_000L) {
                runCatching {
                    val local = com.github.libretube.api.NewPipeMediaServiceRepository()
                    if (nextPage.isNullOrBlank()) local.getSearchResults(query, "videos")
                    else local.getSearchResultsNextPage(query, "videos", nextPage)
                }.getOrNull()
            }
            if (backup != null && backup.items.size > (result?.items?.size ?: 0)) {
                result = backup
            }
        }
        result ?: return null
        val videos = result.items.filter { it.type == StreamItem.TYPE_STREAM }
            .map { it.toStreamItem() }
        return Triple(query, videos, result.nextpage)
    }

    private suspend fun vistaFetchMore() {
        if (vistaBusyDiscovering) return
        vistaBusyDiscovering = true
        val generation = recommendationsGeneration
        try {
            // Consume continuation tokens first, then issue fresh topic searches.
            // This works even when the selected provider has no nextpage token.
            val pages = pendingPages.take(2)
            pendingPages = pendingPages.drop(pages.size).toMutableList()
            val topics = if (pages.isEmpty()) vistaQueryQueue.take(3) else emptyList()
            if (pages.isEmpty()) vistaQueryQueue =
                vistaQueryQueue.drop(topics.size).toMutableList()
            if (pages.isEmpty() && topics.isEmpty()) return
            val responses = withContext(Dispatchers.IO) {
                (pages.map { (q, token) -> q to token } +
                 topics.map { it to null }).map { (q, token) ->
                    async { vistaSearch(q, token) }
                }.awaitAll().filterNotNull()
            }
            if (generation != recommendationsGeneration) return
            for ((query, videos, nextPage) in responses) {
                vistaAdd(vistaExplorationVideos, videos)
                if (!nextPage.isNullOrBlank() &&
                    pendingPages.none { it.first == query && it.second == nextPage }) {
                    pendingPages.add(query to nextPage)
                }
            }
            updateRecommendedVideos()
        } finally {
            if (generation == recommendationsGeneration) vistaBusyDiscovering = false
        }
    }

    private suspend fun loadPersonalizedRecommendations() {
        if (!PreferenceHelper.getBoolean("vistatube_recommendations", true)) {
            recommendations.value = emptyList()
            return
        }
        val generation = recommendationsGeneration
        // First publish cached candidates from the previous session/refresh.
        // This prevents screen blanks or a forced reload to see videos.
        if (recommendedItems.isNotEmpty()) {
            recommendations.value = recommendedItems.take(vistaVisibleCount)
        }

        val (history, searches) = withContext(Dispatchers.IO) {
            DatabaseHelper.getWatchHistoryPage(1, 75) to
                DatabaseHolder.Database.searchHistoryDao().getAll()
                    .asReversed().map { it.query }.take(25)
        }
        if (generation != recommendationsGeneration) return
        recommendationHistory = history
        recommendationSearches = searches

        // Subscriptions first: no waiting for all six discovery queries.
        val subscriptions = VistaSubscriptionVideos.savedChannels()
        if (generation != recommendationsGeneration) return
        recommendationSubscribedChannels = subscriptions
            .map { it.name.lowercase().trim() }.toSet()

        val cachedFeed = withTimeoutOrNull(8_000L) {
            VistaSubscriptionVideos.loadFeedWithFallback(false)
        }.orEmpty()
        if (generation != recommendationsGeneration) return
        vistaAdd(vistaSubscribedVideos, cachedFeed)
        updateRecommendedVideos()

        val channels = subscriptions.map { it.url to it.name } +
            history.mapNotNull { record ->
                record.uploaderUrl?.takeIf { it.isNotBlank() }
                    ?.let { it to record.uploader.orEmpty() }
            }
        // Run related-video and per-channel lookups concurrently with discovery
        // searches. Every completed stage publishes, even if others time out.
        val queries = vistaQueries(history, searches, subscriptions.map { it.name })
        val queryOffset = (refreshIndex - 1).coerceAtLeast(0) %
            (if (queries.isEmpty()) 1 else queries.size)
        val rotatedQueries = queries.drop(queryOffset) + queries.take(queryOffset)
        vistaQueryQueue = rotatedQueries.toMutableList()

        coroutineScope {
            val channelJob = launch(Dispatchers.IO) {
                val videos = withTimeoutOrNull(14_000L) {
                    VistaSubscriptionVideos.videosFromChannels(channels, maxChannels = 18)
                }.orEmpty()
                withContext(Dispatchers.Main) {
                    if (generation == recommendationsGeneration) {
                        vistaAdd(vistaSubscribedVideos, videos)
                        updateRecommendedVideos()
                    }
                }
            }
            val relatedJob = launch(Dispatchers.IO) {
                val related = history.take(5).map { it.videoId }.distinct()
                    .map { id ->
                        async {
                            withTimeoutOrNull(6_000L) {
                                runCatching {
                                    MediaServiceRepository.instance
                                        .getStreams(id).relatedStreams
                                }.getOrDefault(emptyList())
                            }.orEmpty()
                        }
                    }.awaitAll().flatten()
                withContext(Dispatchers.Main) {
                    if (generation == recommendationsGeneration) {
                        vistaAdd(vistaRelatedVideos, related)
                        updateRecommendedVideos()
                    }
                }
            }
            val discoveryJob = launch {
                vistaFetchMore()
                // Aim for at least ten on the initial screen; if one topic
                // returns too few, try additional topic searches progressively.
                var retries = 0
                while (generation == recommendationsGeneration &&
                    recommendedItems.size < 10 &&
                    vistaQueryQueue.isNotEmpty() && retries++ < 3) {
                    vistaFetchMore()
                }
            }
            channelJob.join()
            relatedJob.join()
            discoveryJob.join()
        }
        if (generation == recommendationsGeneration) updateRecommendedVideos()
    }

    fun loadMoreRecommendations() {
        if (!PreferenceHelper.getBoolean("vistatube_recommendations", true)) return
        val now = android.os.SystemClock.elapsedRealtime()
        if (now - vistaLastScrollAt < 750L || vistaBusyDiscovering) return
        vistaLastScrollAt = now
        // Reveal a new ten-video page only after the previous page is full.
        if (recommendedItems.size >= vistaVisibleCount &&
            recommendations.value.orEmpty().size >= vistaVisibleCount) {
            vistaVisibleCount += 10
            updateRecommendedVideos()
        }
        // At the end, automatically fetch another page or a fresh topic.
        if (recommendedItems.size <= vistaVisibleCount + 10) {
            viewModelScope.launch { vistaFetchMore() }
        }
    }

'''
# Kotlin above uses coroutineScope and launch imported in upstream; extension function
# shorthand is deliberate to avoid forcing a large change to imports.

def patch(root):
    base=root/"app/src/main/java/com/github/libretube"
    vm=base/"ui/models/HomeViewModel.kt"
    home=base/"ui/fragments/HomeFragment.kt"
    source=vm.read_text(encoding="utf-8")
    before=source.index("    private fun makeQueries(")
    after=source.index("    private suspend fun loadTrending(context: Context) {",before)
    replaced=source[:before]+DISCOVERY+source[after:]
    # coroutineScope from KotlinX; the other coroutine helpers are imported by
    # earlier VistaTube patches.
    if "import kotlinx.coroutines.coroutineScope" not in replaced:
        replaced=replaced.replace(
            "import kotlinx.coroutines.withContext",
            "import kotlinx.coroutines.coroutineScope\nimport kotlinx.coroutines.withContext")
    # Older app code killed the whole recommendation chain after 24 seconds.
    replaced=replaced.replace(
        "withTimeoutOrNull(24_000L) { loadPersonalizedRecommendations() }",
        "loadPersonalizedRecommendations()")
    vm.write_text(replaced,encoding="utf-8")
    # In v0.4 the scroll listener only fired when already inside a populated
    # RecyclerView. Keep it but use a slightly broader prefetch margin.
    swap(home,
        "scrollY + binding.scroll.height >= binding.recommendedRV.bottom - 550",
        "scrollY + binding.scroll.height >= binding.recommendedRV.bottom - 850")
    print("VistaTube 0.9: blended personalised/discovery sources; 10 videos per scroll; progressive page fetch")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    patch(parser.parse_args().upstream.resolve())
