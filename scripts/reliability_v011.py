#!/usr/bin/env python3
"""VistaTube 0.11: real source recovery and ten-video minimum prefetch."""
from pathlib import Path
import argparse

def once(path,old,new):
    s=path.read_text(encoding="utf-8")
    n=s.count(old)
    if n!=1: raise AssertionError(f"{path}: expected one {old[:88]!r}; got {n}")
    path.write_text(s.replace(old,new),encoding="utf-8")

def patch(root):
    base=root/"app/src/main/java/com/github/libretube"
    vm=base/"ui/models/HomeViewModel.kt"
    provider=base/"helpers/VistaSubscriptionVideos.kt"
    home=base/"ui/fragments/HomeFragment.kt"

    # Actual incomplete discovery must be detectable even if there isn't enough
    # content to make the nested scroll view scrollable.
    once(vm,'''    private var vistaLastScrollAt = 0L''',
        '''    private var vistaLastScrollAt = 0L
    private var vistaLastMinimumFetch = 0L
    private var vistaMinimumFillJob: Job? = null''')
    once(vm,'''    fun loadMoreRecommendations() {''',
        '''    fun ensureRecommendations() {
        if (!PreferenceHelper.getBoolean("vistatube_recommendations", true)) return
        if (recommendations.value.orEmpty().size >= 10 ||
            vistaDiscoveryJob?.isActive == true ||
            vistaMinimumFillJob?.isActive == true ||
            vistaBusyDiscovering) return

        val now = android.os.SystemClock.elapsedRealtime()
        if (vistaLastMinimumFetch > 0L && now - vistaLastMinimumFetch < 18_000L) return
        vistaLastMinimumFetch = now

        vistaMinimumFillJob = viewModelScope.launch {
            val generation = recommendationsGeneration
            try {
                var attempts = 0
                while (generation == recommendationsGeneration &&
                    recommendedItems.size < 12 &&
                    (vistaQueryQueue.isNotEmpty() || pendingPages.isNotEmpty()) &&
                    attempts++ < 4) {
                    vistaFetchMore()
                }
                if (generation == recommendationsGeneration &&
                    recommendedItems.size < 10) {
                    vistaFillSparseDiscovery()
                }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                android.util.Log.w("VistaTubeDiscovery", "Minimum feed refill failed", error)
            }
        }
    }

    fun loadMoreRecommendations() {''')

    # Near-end prefetch should not depend on being able to scroll; the
    # short-feed branch above handles the zero-scroll case.
    once(home,'''scrollY + binding.scroll.height >= binding.recommendedRV.bottom - 850''',
        '''((binding.scroll.getChildAt(0)?.height ?: 0) -
                    scrollY - binding.scroll.height) <= 900''')

    # Server-side sources often expose many related videos from an individual
    # watched YouTube ID even when the selected Piped instance does not.
    # Only retry NewPipe for a sparse result, keeping videos related to what
    # the user actually watched (rather than random trending topics).
    once(vm,'''                                runCatching {
                                    MediaServiceRepository.instance
                                        .getStreams(id).relatedStreams
                                }.getOrDefault(emptyList())''',
        '''                                val main = runCatching {
                                    MediaServiceRepository.instance
                                        .getStreams(id).relatedStreams
                                }.getOrDefault(emptyList())
                                if (main.size >= 10) main else {
                                    val backup = withTimeoutOrNull(7_000L) {
                                        runCatching {
                                            com.github.libretube.api.NewPipeMediaServiceRepository()
                                                .getStreams(id).relatedStreams
                                        }.getOrDefault(emptyList())
                                    }.orEmpty()
                                    (main + backup).distinctBy { it.url.orEmpty().toID() }
                                }''')

    # Channel feeds must also collect enough actual videos. A successful
    # channel lookup with only one stream is NOT a full subscription feed.
    once(provider,'''                if (fromChannel.isNotEmpty()) fromChannel
                else if (channelName.isNotBlank()) {''',
        '''                val expanded = if (fromChannel.size < 10) {
                    withTimeoutOrNull(7_000L) {
                        runCatching {
                            com.github.libretube.api.NewPipeMediaServiceRepository()
                                .getChannel(id).relatedStreams
                        }.getOrDefault(emptyList())
                    }.orEmpty()
                } else emptyList()
                val combined = (fromChannel + expanded)
                    .distinctBy { it.url.orEmpty().toID() }
                if (combined.isNotEmpty()) combined
                else if (channelName.isNotBlank()) {''')

    # A cached-feed request previously included expensive channel lookups,
    # causing all cached videos to be discarded after an eight-second timeout.
    once(vm,'''        val cachedFeed = withTimeoutOrNull(8_000L) {
            VistaSubscriptionVideos.loadFeedWithFallback(false)
        }.orEmpty()''',
        '''        val cachedFeed = withTimeoutOrNull(5_000L) {
            withContext(Dispatchers.IO) {
                runCatching {
                    SubscriptionHelper.getFeed(forceRefresh = false)
                }.getOrDefault(emptyList())
            }
        }.orEmpty()''')
    once(vm,'''                val videos = withTimeoutOrNull(14_000L) {
                    VistaSubscriptionVideos.videosFromChannels(channels, maxChannels = 18)
                }.orEmpty()''',
        '''                val videos = withTimeoutOrNull(27_000L) {
                    VistaSubscriptionVideos.videosFromChannels(channels, maxChannels = 18)
                }.orEmpty()''')
    once(vm,'''                            withTimeoutOrNull(6_000L) {
                                val main = runCatching {''',
        '''                            withTimeoutOrNull(14_000L) {
                                val main = runCatching {''')

    # A channel with two items should still search for more videos; in the old
    # version the name search ran only if zero items were returned.
    once(provider,'''                if (combined.isNotEmpty()) combined
                else if (channelName.isNotBlank()) {''',
        '''                if (combined.size >= 10) combined
                else if (channelName.isNotBlank()) {''')
    # The name-search block is the only one allowed to combine extras here.
    provider_source = provider.read_text(encoding="utf-8")
    anchor = provider_source.index('service.getSearchResults(channelName, "videos")')
    old_suffix = '''                        }.getOrDefault(emptyList())
                    }.orEmpty()
                } else emptyList()'''
    start = provider_source.index(old_suffix, anchor)
    provider.write_text(provider_source[:start] + '''                        }.getOrDefault(emptyList())
                    }.orEmpty().let { extras ->
                        (combined + extras).distinctBy { it.url.orEmpty().toID() }
                    }
                } else combined''' +
                        provider_source[start + len(old_suffix):], encoding="utf-8")

    # Previously, retries from Search/Related produced only two valid
    # candidates, yet onScroll did nothing because there were only two rows.
    # Keep fallback discovery local, but don't introduce unrelated videos
    # from generic country-wide top lists for a personalized user.
    once(vm,'''        vistaAdd(vistaExplorationVideos, results)
        android.util.Log.i("VistaTubeDiscovery",''',
        '''        val interests = (recommendationHistory.mapNotNull { it.title } +
            recommendationSearches + recommendationSubscribedChannels)
            .flatMap { text -> text.lowercase()
                .split(Regex("[^a-z0-9à-ÿ]+")) }
            .filter { it.length >= 4 }.toSet()
        // Trending is discovery, but only include videos with topical
        // overlap with watched/search terms when personal signals exist.
        val relevant = if (interests.isEmpty()) results else {
            results.filter { video ->
                val text = (video.title.orEmpty() + " " +
                    video.uploaderName.orEmpty()).lowercase()
                interests.count { it in text } >= 1
            }
        }
        vistaAdd(vistaExplorationVideos, relevant)
        android.util.Log.i("VistaTubeDiscovery",''')
    print("VistaTube v0.11: minimum-item prefetch, NewPipe channel/related fallback and interest-filtered exploration")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    patch(parser.parse_args().upstream.resolve())
