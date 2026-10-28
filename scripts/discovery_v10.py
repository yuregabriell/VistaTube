#!/usr/bin/env python3
"""VistaTube 1.0: fix sparse For You feed + diversify discovery without manual reload."""
from pathlib import Path
import argparse

def once(path, old, new):
    source=path.read_text(encoding="utf-8")
    count=source.count(old)
    if count!=1:
        raise AssertionError(f"{path}: expected 1 match, got {count} for {old[:110]!r}")
    path.write_text(source.replace(old,new),encoding="utf-8")

def patch(root):
    vm=root/"app/src/main/java/com/github/libretube/ui/models/HomeViewModel.kt"

    once(vm, r'''        return ordered.distinctBy { it.lowercase() }.take(32)
    }

    private fun Int?.orEmptyInt(): Int''',
    r'''        val signals = (history.mapNotNull { it.title } +
            searches + channelNames).joinToString(" ").lowercase()
        val topics = mutableListOf<String>()
        if (listOf("jogo", "games", "gaming", "stream", "gameplay", "dressmaker",
                   "minecraft", "roblox", "terror", "live").any { it in signals }) {
            topics += listOf("gameplay jogos em português", "jogos em alta brasil",
                "youtubers jogos e desafios", "jogos independentes gameplay")
        }
        if (listOf("filme", "série", "serie", "cinema", "marvel", "nerd",
                   "dc comics", "super herói", "super heroi").any { it in signals }) {
            topics += listOf("cinema cultura pop teorias", "filmes séries análise",
                "curiosidades filmes e super heróis")
        }
        if (listOf("música", "musica", "cantor", "album", "show", "spotify").any { it in signals }) {
            topics += listOf("música brasileira lançamentos", "música pop artistas")
        }
        if (listOf("tecnologia", "pc", "android", "programação", "iphone",
                   "computador").any { it in signals }) {
            topics += listOf("tecnologia novidades brasil", "reviews tecnologia")
        }
        // No local history on freshly installed apps; use general content
        // discovery ONLY until personalised signals exist.
        if (ordered.isEmpty()) {
            topics += listOf("criadores brasileiros entretenimento",
                "jogos novidades em português", "cinema cultura pop português",
                "ciência e tecnologia curiosidades")
        } else if (topics.isEmpty() && ordered.size < 4) {
            topics += listOf("entretenimento vídeos em português",
                "criadores brasileiros curiosidades")
        }
        return (ordered + topics).distinctBy { it.lowercase() }.take(48)
    }

    private fun Int?.orEmptyInt(): Int''')

    # Critical fix: pending continuation pages kept the algorithm from ever
    # advancing to new topics. Always fetch from both types together.
    once(vm, '''            val topics = if (pages.isEmpty()) vistaQueryQueue.take(3) else emptyList()
            if (pages.isEmpty()) vistaQueryQueue =
                vistaQueryQueue.drop(topics.size).toMutableList()
            if (pages.isEmpty() && topics.isEmpty()) return''',
    '''            val topics = vistaQueryQueue.take(3)
            vistaQueryQueue = vistaQueryQueue.drop(topics.size).toMutableList()
            if (pages.isEmpty() && topics.isEmpty()) return''')

    # Region/category fallback is limited to topics likely to match the user.
    # It activates only when search and subscription feeds return few results.
    marker='''    private suspend fun loadPersonalizedRecommendations() {'''
    helper='''    private suspend fun vistaFillSparseDiscovery() {
        val generation = recommendationsGeneration
        if (recommendedItems.size >= 15) return
        val signals = (recommendationHistory.mapNotNull { it.title } +
            recommendationSearches + recommendationSubscribedChannels)
            .joinToString(" ").lowercase()
        val gaming = listOf("game", "jogo", "stream", "dressmaker",
            "minecraft", "roblox", "live", "terror").any { it in signals }
        val cinema = listOf("filme", "cinema", "nerd", "marvel",
            "série", "serie", "herói").any { it in signals }
        val categories = when {
            gaming && cinema -> listOf(TrendingCategory.GAMING,
                TrendingCategory.TRAILERS)
            gaming -> listOf(TrendingCategory.GAMING, TrendingCategory.LIVE)
            cinema -> listOf(TrendingCategory.TRAILERS,
                TrendingCategory.PODCASTS)
            else -> listOf(TrendingCategory.GAMING,
                TrendingCategory.TRAILERS, TrendingCategory.PODCASTS)
        }
        val results = withContext(Dispatchers.IO) {
            categories.map { category ->
                async {
                    withTimeoutOrNull(8_000L) {
                        runCatching {
                            MediaServiceRepository.instance.getTrending("BR", category)
                        }.getOrDefault(emptyList())
                    }.orEmpty()
                }
            }.awaitAll().flatten()
        }
        if (generation != recommendationsGeneration) return
        vistaAdd(vistaExplorationVideos, results)
        android.util.Log.i("VistaTubeDiscovery",
            "Fallback discoveries: " + results.size + ", candidates: " +
            vistaSubscribedVideos.size + "/" + vistaRelatedVideos.size +
            "/" + vistaExplorationVideos.size)
        updateRecommendedVideos()
    }

'''
    once(vm,marker,helper+marker)

    once(vm,'''                // Aim for at least ten on the initial screen; if one topic
                // returns too few, try additional topic searches progressively.
                var retries = 0
                while (generation == recommendationsGeneration &&
                    recommendedItems.size < 10 &&
                    vistaQueryQueue.isNotEmpty() && retries++ < 3) {
                    vistaFetchMore()
                }''',
    '''                // Search more than one topic, independent of user scrolling.
                var retries = 0
                while (generation == recommendationsGeneration &&
                    recommendedItems.size < 25 &&
                    (vistaQueryQueue.isNotEmpty() || pendingPages.isNotEmpty()) &&
                    retries++ < 5) {
                    vistaFetchMore()
                }
                if (generation == recommendationsGeneration &&
                    recommendedItems.size < 15) {
                    vistaFillSparseDiscovery()
                }''')

    # Allow already prepared videos to be revealed even if async queries run.
    once(vm,'''        if (now - vistaLastScrollAt < 750L || vistaBusyDiscovering) return''',
    '''        if (now - vistaLastScrollAt < 750L) return''')
    once(vm,'''        if (recommendedItems.size <= vistaVisibleCount + 10) {
            viewModelScope.launch { vistaFetchMore() }
        }''',
    '''        if (recommendedItems.size <= vistaVisibleCount + 10 &&
            !vistaBusyDiscovering) {
            viewModelScope.launch {
                vistaFetchMore()
                if (recommendedItems.size <= vistaVisibleCount + 5 &&
                    pendingPages.isEmpty() && vistaQueryQueue.isEmpty()) {
                    vistaFillSparseDiscovery()
                }
            }
        }''')
    once(vm,'''        recommendations.value = combined.take(vistaVisibleCount)''',
    '''        android.util.Log.d("VistaTubeDiscovery",
            "Candidates subs=" + vistaSubscribedVideos.size +
            ", related=" + vistaRelatedVideos.size +
            ", explore=" + vistaExplorationVideos.size +
            ", unique=" + combined.size +
            ", shown=" + minOf(combined.size, vistaVisibleCount))
        recommendations.value = combined.take(vistaVisibleCount)''')
    print("VistaTube 1.0: mixing continuation pages and new topics; trying 5 search waves + interest fallback")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    patch(parser.parse_args().upstream.resolve())
