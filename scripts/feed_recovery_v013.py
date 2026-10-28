#!/usr/bin/env python3
"""VistaTube 0.13: repair exhausted discovery queue and three-item feed."""
from pathlib import Path
import argparse

def patch(root):
    vm=root/"app/src/main/java/com/github/libretube/ui/models/HomeViewModel.kt"
    s=vm.read_text(encoding="utf-8")
    a=s.index("    private suspend fun vistaFetchMore() {")
    b=s.index("    private suspend fun loadPersonalizedRecommendations() {",a)
    replacement=r'''    private var vistaSeedRound = 0
    private var vistaConsecutiveEmpty = 0

    private fun vistaReplenishQueries() {
        if (vistaQueryQueue.isNotEmpty() || pendingPages.isNotEmpty()) return
        val base = vistaQueries(
            recommendationHistory, recommendationSearches,
            recommendationSubscribedChannels.toList()
        ).ifEmpty { listOf(
            "gameplay jogos brasil", "cultura pop cinema brasil",
            "ciência tecnologia canais brasileiros", "entretenimento em português"
        ) }
        val round = vistaSeedRound++
        val suffix = when (round % 6) {
            0 -> ""
            1 -> " novidades"
            2 -> " vídeos recentes"
            3 -> " em português"
            4 -> " análises"
            else -> " melhores vídeos"
        }
        val offset = (round * 5) % base.size
        val rotated = base.drop(offset) + base.take(offset)
        vistaQueryQueue.addAll(rotated.take(12).map { (it + suffix).trim() })
    }

    private suspend fun vistaFetchMore() {
        if (vistaBusyDiscovering) return
        vistaBusyDiscovering = true
        val generation = recommendationsGeneration
        try {
            vistaReplenishQueries()
            // Always mix next pages with NEW topics. The previous queue was
            // consumed permanently, leaving three videos with no next page.
            val pages = pendingPages.take(2)
            pendingPages = pendingPages.drop(pages.size).toMutableList()
            val topics = vistaQueryQueue.take(4)
            vistaQueryQueue = vistaQueryQueue.drop(topics.size).toMutableList()
            val requests: List<Pair<String, String?>> =
                pages.map { it.first to it.second } +
                topics.map { it to null }
            if (requests.isEmpty()) return
            val replies = withContext(Dispatchers.IO) {
                requests.map { (query, token) ->
                    async { vistaSearch(query, token) }
                }.awaitAll().filterNotNull()
            }
            if (generation != recommendationsGeneration) return
            val old = vistaExplorationVideos.size
            for ((query, videos, next) in replies) {
                vistaAdd(vistaExplorationVideos, videos)
                if (!next.isNullOrBlank() &&
                    pendingPages.none { it.first == query && it.second == next }) {
                    pendingPages.add(query to next)
                }
            }
            val added = vistaExplorationVideos.size - old
            vistaConsecutiveEmpty = if (added == 0) vistaConsecutiveEmpty + 1 else 0
            updateRecommendedVideos()
            android.util.Log.i("VistaTubeDiscovery", "Search requests=" +
                requests.size + " added=" + added +
                " pool=" + recommendedItems.size + " empty=" + vistaConsecutiveEmpty)
        } finally {
            vistaBusyDiscovering = false
        }
    }

    private suspend fun vistaFillSparseDiscovery() {
        val generation = recommendationsGeneration
        if (recommendedItems.size >= 30) return
        val interests = (recommendationHistory.mapNotNull { it.title } +
            recommendationSearches + recommendationSubscribedChannels)
            .joinToString(" ").lowercase()
        val gaming = listOf("jogo", "game", "felps", "minecraft",
            "mario", "live", "stream", "switch").any { it in interests }
        val cinema = listOf("nerd", "filme", "cinema", "série", "serie",
            "anime", "marvel", "dc", "cultura pop").any { it in interests }
        val categories = when {
            gaming && cinema -> listOf(TrendingCategory.GAMING,
                TrendingCategory.TRAILERS, TrendingCategory.PODCASTS)
            gaming -> listOf(TrendingCategory.GAMING,
                TrendingCategory.LIVE, TrendingCategory.PODCASTS)
            cinema -> listOf(TrendingCategory.TRAILERS,
                TrendingCategory.PODCASTS, TrendingCategory.GAMING)
            else -> listOf(TrendingCategory.GAMING,
                TrendingCategory.PODCASTS, TrendingCategory.TRAILERS)
        }
        val videos = withContext(Dispatchers.IO) {
            categories.map { category ->
                async {
                    val primary = withTimeoutOrNull(8_000L) {
                        runCatching {
                            MediaServiceRepository.instance.getTrending("BR", category)
                        }.getOrDefault(emptyList())
                    }.orEmpty()
                    val backup = if (primary.size < 15) {
                        withTimeoutOrNull(8_000L) {
                            runCatching {
                                com.github.libretube.api.NewPipeMediaServiceRepository()
                                    .getTrending("BR", category)
                            }.getOrDefault(emptyList())
                        }.orEmpty()
                    } else emptyList()
                    (primary + backup)
                        .distinctBy { it.url.orEmpty().toID() }.take(60)
                }
            }.awaitAll().flatten()
        }
        if (generation != recommendationsGeneration) return
        // Chosen categories already correspond to user interests. The old
        // exact word overlap filter rejected practically everything returned.
        vistaAdd(vistaExplorationVideos, videos)
        updateRecommendedVideos()
        android.util.Log.i("VistaTubeDiscovery", "Category recovery=" +
            videos.size + " candidates=" + recommendedItems.size)
    }

'''
    s=s[:a]+replacement+s[b:]
    def replace_once(old,new):
        nonlocal s
        if s.count(old)!=1: raise AssertionError("Expected once: "+old[:130]+" found "+str(s.count(old)))
        s=s.replace(old,new)
    replace_once('''                while (generation == recommendationsGeneration &&
                    recommendedItems.size < 25 &&
                    (vistaQueryQueue.isNotEmpty() || pendingPages.isNotEmpty()) &&
                    retries++ < 5) {
                    vistaFetchMore()
                }''','''                while (generation == recommendationsGeneration &&
                    recommendedItems.size < 30 && retries++ < 6) {
                    vistaFetchMore()
                }''')
    replace_once('''                if (generation == recommendationsGeneration &&
                    recommendedItems.size < 15) {
                    vistaFillSparseDiscovery()
                }''','''                if (generation == recommendationsGeneration &&
                    recommendedItems.size < 30) {
                    vistaFillSparseDiscovery()
                }''')
    replace_once('''                while (generation == recommendationsGeneration &&
                    recommendedItems.size < 12 &&
                    (vistaQueryQueue.isNotEmpty() || pendingPages.isNotEmpty()) &&
                    attempts++ < 4) {
                    vistaFetchMore()
                }''','''                while (generation == recommendationsGeneration &&
                    recommendedItems.size < 20 && attempts++ < 3) {
                    vistaFetchMore()
                }''')
    replace_once('''                if (recommendedItems.size <= vistaVisibleCount + 5 &&
                    pendingPages.isEmpty() && vistaQueryQueue.isEmpty()) {
                    vistaFillSparseDiscovery()
                }''','''                if (recommendedItems.size <= vistaVisibleCount + 5) {
                    vistaFillSparseDiscovery()
                }''')
    replace_once('''                    if (id.isBlank() || !seen.add(id)) continue
                    combined.add(item)
                    picked = true''','''                    if (id.isBlank() || id in seen) continue
                    val creator = item.uploaderName.orEmpty().lowercase().trim()
                    val recent = combined.takeLast(8).count {
                        it.uploaderName.orEmpty().lowercase().trim() == creator
                    }
                    val otherSourcesHaveVideos = buckets.indices.any { other ->
                        other != bucket && positions[other] < buckets[other].size
                    }
                    if (creator.isNotEmpty() && recent >= 2 &&
                        otherSourcesHaveVideos) continue
                    seen.add(id)
                    combined.add(item)
                    picked = true''')
    # Start category recovery while searches execute, not after six slow waves.
    replace_once('''            val discoveryJob = launch {
                vistaFetchMore()''',
        '''            val categoryJob = launch {
                delay(2_500L)
                if (generation == recommendationsGeneration &&
                    recommendedItems.size < 10) {
                    vistaFillSparseDiscovery()
                }
            }
            val discoveryJob = launch {
                vistaFetchMore()''')
    replace_once('''            discoveryJob.join()
        }''',
        '''            discoveryJob.join()
            categoryJob.join()
        }''')
    vm.write_text(s,encoding="utf-8")
    print("VistaTube 0.13: refreshed query queue, multiprovider recovery, short feed auto retry")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("upstream", type=Path)
    patch(p.parse_args().upstream.resolve())
