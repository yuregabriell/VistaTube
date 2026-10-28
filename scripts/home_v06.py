#!/usr/bin/env python3
"""VistaTube 0.6 hotfix: never block Home on recommendation network requests."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

A="{http://schemas.android.com/apk/res/android}"
ET.register_namespace("android","http://schemas.android.com/apk/res/android")
ET.register_namespace("app","http://schemas.android.com/apk/res-auto")
ET.register_namespace("tools","http://schemas.android.com/tools")

def replace(path, old, new):
    c=path.read_text(encoding="utf-8")
    n=c.count(old)
    if n!=1: raise AssertionError(f"{path}: expected one match of {old[:100]!r}, found {n}")
    path.write_text(c.replace(old,new),encoding="utf-8")

def patch(root):
    base=root/"app/src/main/java/com/github/libretube"
    vm=base/"ui/models/HomeViewModel.kt"
    home=base/"ui/fragments/HomeFragment.kt"
    layout=root/"app/src/main/res/layout/fragment_home.xml"

    replace(vm,"""import kotlinx.coroutines.withContext""",
        """import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.CancellationException""")
    # Critical: Home must not remain hidden while remote recommendation/search
    # calls are pending. Show the screen and a loading/empty prompt immediately.
    replace(vm,"""        isLoading.value = true
        refreshIndex++""",
        """        isLoading.value = false
        loadedSuccessfully.value = true
        refreshIndex++""")
    replace(vm,"""                loadPersonalizedRecommendations()
                loadedSuccessfully.value = sections.any { it.value != null }
                isLoading.value = false""",
        """                // Launch search/related recommendations independently.
                // Network failures must never leave the Home screen invisible.
                launch {
                    try {
                        withTimeoutOrNull(24_000L) { loadPersonalizedRecommendations() }
                    } catch (cancel: CancellationException) {
                        throw cancel
                    } catch (error: Exception) {
                        android.util.Log.w("VistaTubeHome", "Recommendation load failed", error)
                        if (recommendations.value.isNullOrEmpty()) {
                            recommendations.value = feed.value.orEmpty()
                        }
                    }
                }
                loadedSuccessfully.value = true
                isLoading.value = false""")
    # The old widgets are hidden in VistaTube. Waiting for trending,
    # bookmarks, playlists and their network calls unnecessarily delayed
    # recommendations (or could block them forever).
    replace(vm,"""                awaitAll(
                    async { if (visibleItems.contains(TRENDING)) loadTrending(context) },
                    async { if (visibleItems.contains(FEATURED)) loadFeed(subscriptionsViewModel) },
                    async { if (visibleItems.contains(BOOKMARKS)) loadBookmarks() },
                    async { if (visibleItems.contains(PLAYLISTS)) loadPlaylists() },
                    async { if (visibleItems.contains(WATCHING)) loadVideosToContinueWatching() }
                )
                // Launch search/related recommendations independently.""",
        """                // Launch search/related recommendations independently.""")
    replace(vm,"""                loadedSuccessfully.value = true
                isLoading.value = false
            }

            withContext(Dispatchers.IO)""",
        """                try {
                    if (visibleItems.contains(WATCHING)) loadVideosToContinueWatching()
                } catch (error: Exception) {
                    android.util.Log.w("VistaTubeHome", "Continue watching unavailable", error)
                }
                loadedSuccessfully.value = true
                isLoading.value = false
            }

            withContext(Dispatchers.IO)""")
    # Display subscription videos immediately instead of blocking on 6+
    # searches, related videos, and pagination. Preserve ranking later.
    replace(vm,"""        val subscriptionsFeed = withContext(Dispatchers.IO) {
            runCatching { SubscriptionHelper.getFeed(forceRefresh = refreshIndex > 1) }
                .getOrDefault(emptyList())
        }
        if (generation != recommendationsGeneration) return
        val queries = makeQueries(history, searches + subscriptionInfo.map { it.name })""",
        """        val subscriptionsFeed = withTimeoutOrNull(10_000L) {
            withContext(Dispatchers.IO) {
                runCatching { SubscriptionHelper.getFeed(forceRefresh = false) }
                    .getOrDefault(emptyList())
            }
        }.orEmpty()
        if (generation != recommendationsGeneration) return

        // Emit the subscribed feed before any slow video search. Even if search
        // subsequently fails, the user still has useful videos on the Home.
        recommendedItems = (subscriptionsFeed + feed.value.orEmpty() + recommendedItems)
            .distinctBy { it.url.orEmpty().toID() }
            .take(350).toMutableList()
        updateRecommendedVideos()

        val queries = makeQueries(history, searches + subscriptionInfo.map { it.name })""")
    replace(vm,"""                        val result = api.getSearchResults(query, "videos")""",
        """                        val result = withTimeoutOrNull(8_000L) {
                            api.getSearchResults(query, "videos")
                        } ?: return@runCatching null""")
    replace(vm,"""            }.awaitAll().filterNotNull()
        }
        if (generation != recommendationsGeneration) return
        val newPages""",
        """            }.awaitAll().filterNotNull()
        }
        if (generation != recommendationsGeneration) return
        val newPages""")
    # Per-video related recommendations shouldn't hold the entire page hostage.
    replace(vm,"""                    runCatching { api.getStreams(id).relatedStreams }.getOrDefault(emptyList())""",
        """                    withTimeoutOrNull(5_000L) {
                        runCatching { api.getStreams(id).relatedStreams }.getOrDefault(emptyList())
                    }.orEmpty()""")
    # Home receives results as soon as the first subscription feed arrives.
    # The status message is visible until recommendations are available.
    replace(home,"""        binding.recommendedHeader.isVisible = hasVideos
        binding.recommendedRV.isVisible = hasVideos""",
        """        binding.recommendedHeader.isVisible = true
        binding.recommendedRV.isVisible = hasVideos
        binding.recommendationStatus.isVisible = !hasVideos
        binding.recommendationStatus.text = if (videos == null) {
            "A procurar vídeos dos teus canais e interesses…"
        } else {
            "Ainda não há vídeos para mostrar. Experimenta atualizar ou ver as Subscrições."
        }""")

    xml=ET.parse(layout)
    col=next(x for x in xml.iter() if x.tag=="LinearLayout" and
        any(v.get(A+"id")=="@+id/recommendedRV" for v in x.iter()))
    header=next(x for x in col if x.get(A+"id")=="@+id/recommended_header")
    ind=list(col).index(header)
    text=ET.Element("TextView",{
        A+"id":"@+id/recommendation_status",A+"layout_width":"match_parent",
        A+"layout_height":"wrap_content",A+"padding":"24dp",
        A+"text":"A procurar vídeos dos teus canais e interesses…",
        A+"textSize":"15sp",A+"visibility":"visible"
    })
    col.insert(ind+1,text)
    xml.write_text('<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(xml.getroot(),encoding="unicode"),encoding="utf-8")
    ET.parse(layout)
    print("VistaTube 0.6: nonblocking Home, progressive subscription feed, timeout fallbacks")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("upstream",type=Path)
    patch(p.parse_args().upstream.resolve())
