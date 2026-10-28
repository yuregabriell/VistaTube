#!/usr/bin/env python3
"""VistaTube 0.8: populated discovery, subscription fallback, visible bottom tabs."""
from pathlib import Path
import argparse

PROVIDER = r'''package com.github.libretube.helpers

import android.util.Log
import com.github.libretube.api.MediaServiceRepository
import com.github.libretube.api.SubscriptionHelper
import com.github.libretube.api.obj.StreamItem
import com.github.libretube.api.obj.Subscription
import com.github.libretube.extensions.toID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Subscription feed fallback.
 *
 * The local extractor's RSS/update feed can return empty when the metadata
 * endpoint fails or the user's local channel feed has not been populated yet.
 * This tries the selected media service's channel Videos endpoint instead.
 * No Google account login or private network service is required.
 */
object VistaSubscriptionVideos {
    suspend fun savedChannels(): List<Subscription> =
        withTimeoutOrNull(5_000L) {
            withContext(Dispatchers.IO) {
                runCatching { SubscriptionHelper.getSubscriptions() }.getOrDefault(emptyList())
            }
        }.orEmpty()

    suspend fun videosFromChannels(
        channels: List<Pair<String, String>>,
        maxChannels: Int = 12
    ): List<StreamItem> = coroutineScope {
        val candidates = channels.asSequence()
            .filter { it.first.isNotBlank() }
            .distinctBy { it.first.toID() }
            .take(maxChannels)
            .toList()
        val service = MediaServiceRepository.instance
        val loaded = candidates.map { (channelId, channelName) ->
            async(Dispatchers.IO) {
                val id = channelId.substringAfterLast('/').substringBefore('?')
                val fromChannel = withTimeoutOrNull(5_000L) {
                    runCatching { service.getChannel(id).relatedStreams }.getOrDefault(emptyList())
                }.orEmpty()
                if (fromChannel.isNotEmpty()) fromChannel
                else if (channelName.isNotBlank()) {
                    withTimeoutOrNull(5_000L) {
                        runCatching {
                            service.getSearchResults(channelName, "videos").items
                                .filter { it.type == StreamItem.TYPE_STREAM }
                                .filter { item ->
                                    item.uploaderName?.equals(channelName, ignoreCase = true) == true
                                }
                                .map { it.toStreamItem() }
                        }.getOrDefault(emptyList())
                    }.orEmpty()
                } else emptyList()
            }
        }.awaitAll().flatten()
        loaded.distinctBy { it.url.orEmpty().toID() }
            .sortedByDescending { it.uploaded }
            .take(250)
    }

    suspend fun loadFeedWithFallback(forceRefresh: Boolean): List<StreamItem> {
        // A cached feed is returned quickly and is valuable even when a network
        // refresh fails. Avoid showing a blank feed while refreshing.
        val stored = withTimeoutOrNull(4_000L) {
            withContext(Dispatchers.IO) {
                runCatching { SubscriptionHelper.getFeed(forceRefresh = false) }
                    .getOrDefault(emptyList())
            }
        }.orEmpty()
        val updated = if (forceRefresh) withTimeoutOrNull(14_000L) {
            withContext(Dispatchers.IO) {
                runCatching { SubscriptionHelper.getFeed(forceRefresh = true) }
                    .getOrDefault(emptyList())
            }
        }.orEmpty() else emptyList()

        val direct = if ((stored + updated).distinctBy { it.url }.size < 20) {
            val channels = savedChannels()
            videosFromChannels(channels.map { it.url to it.name })
        } else emptyList()

        val merged = updated + stored + direct
        return merged.distinctBy { it.url.orEmpty().toID() }
            .sortedByDescending { it.uploaded }
            .take(300)
    }
}
'''

def once(path, old, new):
    data=path.read_text(encoding="utf-8")
    count=data.count(old)
    if count!=1:
        raise AssertionError(f"{path} expected once, found {count}: {old[:105]!r}")
    path.write_text(data.replace(old,new),encoding="utf-8")

def patch(root):
    base=root/"app/src/main/java/com/github/libretube"
    vm=base/"ui/models/HomeViewModel.kt"
    subs=base/"ui/models/SubscriptionsViewModel.kt"
    frag=base/"ui/fragments/SubscriptionsFragment.kt"
    engine=base/"helpers/VistaRecommendationEngine.kt"
    activity=base/"ui/activities/MainActivity.kt"
    provider=base/"helpers/VistaSubscriptionVideos.kt"
    provider.write_text(PROVIDER,encoding="utf-8")

    # Personalized discovery: use actual channel videos even when the RSS
    # extraction feed is empty; include channels from recently watched videos.
    once(vm,"import com.github.libretube.helpers.VistaRecommendationEngine",
        "import com.github.libretube.helpers.VistaRecommendationEngine\nimport com.github.libretube.helpers.VistaSubscriptionVideos")
    once(vm,"""        val subscriptionInfo = withTimeoutOrNull(6_000L) {
            withContext(Dispatchers.IO) {
                runCatching { SubscriptionHelper.getSubscriptions() }.getOrDefault(emptyList())
            }
        }.orEmpty()""",
        """        val subscriptionInfo = VistaSubscriptionVideos.savedChannels()""")
    once(vm,"""        val subscriptionsFeed = withTimeoutOrNull(10_000L) {
            withContext(Dispatchers.IO) {
                runCatching { SubscriptionHelper.getFeed(forceRefresh = false) }
                    .getOrDefault(emptyList())
            }
        }.orEmpty()""",
        """        val subscriptionsFeed = withTimeoutOrNull(8_000L) {
            VistaSubscriptionVideos.loadFeedWithFallback(forceRefresh = false)
        }.orEmpty()""")

    # Send progressively useful results without depending on slow search.
    once(vm,"""        val queries = makeQueries(history, searches + subscriptionInfo.map { it.name })
        val api = MediaServiceRepository.instance""",
        """        // Search is supplementary: fetch videos from channels directly.
        // History channel IDs work even without explicit channel subscriptions.
        val knownChannels = subscriptionInfo.map { it.url to it.name } +
            history.mapNotNull { item ->
                item.uploaderUrl?.takeIf { it.isNotBlank() }
                    ?.let { it to item.uploader.orEmpty() }
            }
        val channelVideos = withTimeoutOrNull(9_000L) {
            VistaSubscriptionVideos.videosFromChannels(knownChannels, maxChannels = 14)
        }.orEmpty()
        if (generation != recommendationsGeneration) return
        recommendedItems = (channelVideos + recommendedItems)
            .distinctBy { it.url.orEmpty().toID() }.take(350).toMutableList()
        updateRecommendedVideos()

        val queries = makeQueries(history, searches + subscriptionInfo.map { it.name })
        val api = MediaServiceRepository.instance""")
    once(vm,"""        val pool = fallback + related + older.flatMap { it.second } + discovered + recommendedItems""",
        """        val pool = channelVideos + fallback + related +
            older.flatMap { it.second } + discovered + recommendedItems""")

    # Prevent the ranker from ignoring subscriptions when history is empty.
    once(engine,"""                val score = if (history.isEmpty()) {
                    freshness + 1.0 / (1.0 + index * 0.025)
                } else topical * 2.0 + description + creatorScore + freshness""",
        """                val score = topical * 2.0 + description +
                    creatorScore + freshness +
                    (if (history.isEmpty()) 1.0 / (1.0 + index * 0.025) else 0.0)""")

    # Subscription screen: avoid replacing a populated list with empty data
    # when the feed extraction fails; preserve cached videos.
    once(subs,"import com.github.libretube.api.SubscriptionHelper",
        "import com.github.libretube.api.SubscriptionHelper\nimport com.github.libretube.helpers.VistaSubscriptionVideos")
    once(subs,"""                SubscriptionHelper.getFeed(forceRefresh = forceRefresh) { feedProgress ->
                    this@SubscriptionsViewModel.feedProgress.postValue(feedProgress)
                }""",
        """                VistaSubscriptionVideos.loadFeedWithFallback(forceRefresh = forceRefresh)""")
    once(subs,"""            this@SubscriptionsViewModel.videoFeed.postValue(videoFeed)""",
        """            // Network failures never erase the last usable channel feed.
            if (videoFeed.isNotEmpty() || this@SubscriptionsViewModel.videoFeed.value.isNullOrEmpty()) {
                this@SubscriptionsViewModel.videoFeed.postValue(videoFeed)
            }""")

    # If all items are filtered away, explain the filter instead of displaying
    # an unexplained empty list. Never mark an empty loaded result as "loading".
    once(frag,"""        val notLoaded = viewModel.videoFeed.value.isNullOrEmpty()
        binding.subFeed.isGone = notLoaded
        binding.emptyFeed.isVisible = notLoaded""",
        """        val noVideos = sortedFeed.isEmpty()
        binding.subFeed.isGone = noVideos
        binding.emptyFeed.isVisible = noVideos""")

    # Bottom nav currently sets only system navigation-bar inset, which can be
    # 0 on Android 16 edge-to-edge. Add a persistent, density-aware bottom space.
    once(activity,"""                            paddingTop,
                            paddingRight,
                            systemBarInsets.bottom""",
        """                            (6 * resources.displayMetrics.density).toInt(),
                            paddingRight,
                            systemBarInsets.bottom + (16 * resources.displayMetrics.density).toInt()""")

    print("VistaTube 0.8: per-channel fallback for Home and Subscriptions; bottom nav safe padding")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("upstream",type=Path)
    patch(p.parse_args().upstream.resolve())
