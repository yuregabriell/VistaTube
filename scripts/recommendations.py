#!/usr/bin/env python3
"""VistaTube 0.3: local, privacy-conscious hybrid video recommendations."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

A="{http://schemas.android.com/apk/res/android}"
APP="{http://schemas.android.com/apk/res-auto}"
ET.register_namespace("android","http://schemas.android.com/apk/res/android")
ET.register_namespace("app","http://schemas.android.com/apk/res-auto")
ET.register_namespace("tools","http://schemas.android.com/tools")

def replace(path, needle, replacement):
    text=path.read_text(encoding="utf-8")
    if text.count(needle)!=1:
        raise AssertionError(f"{path}: {needle[:80]!r} expected once, got {text.count(needle)}")
    path.write_text(text.replace(needle,replacement), encoding="utf-8")

KOTLIN = '''package com.github.libretube.helpers

import com.github.libretube.api.obj.StreamItem
import com.github.libretube.db.obj.WatchHistoryItem
import com.github.libretube.extensions.toID
import java.util.Locale

/**
 * Local content-based recommendation ranker. No external AI API or telemetry.
 *
 * Uses titles, creator names and freshness; inputs are sourced from real
 * recommendations, subscriptions and regional trending. Not a trained LLM.
 */
object VistaRecommendationEngine {
    private val stopwords = setOf(
        "com", "sem", "dos", "das", "que", "para", "uma", "uns", "umas",
        "nos", "nas", "por", "mais", "como", "essa", "esse", "isso",
        "sobre", "pela", "pelo", "voce", "voces", "hoje", "aqui",
        "esta", "este", "ser", "sao", "the", "and", "this", "with",
        "from", "your", "you", "for", "what", "not", "live", "video"
    )
    private fun terms(text: String?): Set<String> =
        text.orEmpty()
            .lowercase(Locale.ROOT)
            .replace(Regex("[^a-z0-9à-ÿ]+"), " ")
            .split(" ")
            .filter { it.length >= 3 && it !in stopwords }
            .toSet()

    fun rank(candidates: List<StreamItem>,
             history: List<WatchHistoryItem>,
             limit: Int = 36): List<StreamItem> {
        val watchedIds = history.map { it.videoId }.toSet()
        val topics = mutableMapOf<String, Double>()
        val creators = mutableMapOf<String, Double>()
        history.take(45).forEachIndexed { index, entry ->
            // Recent watches have more influence, without discarding old interests.
            val importance = 1.0 / (1.0 + index / 8.0)
            terms(entry.title).forEach {
                topics[it] = (topics[it] ?: 0.0) + importance
            }
            val creator = entry.uploader?.lowercase(Locale.ROOT)?.trim().orEmpty()
            if (creator.isNotEmpty()) creators[creator] = (creators[creator] ?: 0.0) + importance
        }
        val now = System.currentTimeMillis()
        val scored = candidates.asSequence()
            .filter { !it.url.isNullOrBlank() && !it.isUpcoming }
            .distinctBy { it.url.orEmpty().toID() }
            .filter { it.url.orEmpty().toID() !in watchedIds }
            .mapIndexed { index, video ->
                val channel = video.uploaderName?.lowercase(Locale.ROOT)?.trim().orEmpty()
                val topical = terms(video.title).sumOf { topics[it] ?: 0.0 }
                val description = terms(video.shortDescription)
                    .take(12).sumOf { topics[it] ?: 0.0 } * 0.12
                val creatorScore = (creators[channel] ?: 0.0) * 2.25
                val ageDays = if (video.uploaded > 0L) {
                    (now - video.uploaded).coerceAtLeast(0L) / 86_400_000.0
                } else 365.0
                val freshness = when {
                    ageDays < 2.0 -> 1.5
                    ageDays < 14.0 -> 1.0
                    ageDays < 60.0 -> 0.5
                    else -> 0.0
                }
                // Without watch history, preserve a balanced regional discovery feed.
                val score = if (history.isEmpty()) {
                    freshness + 1.0 / (1.0 + index * 0.025)
                } else topical + description + creatorScore + freshness
                video to score
            }.sortedByDescending { it.second }.toList()

        val result = mutableListOf<StreamItem>()
        val perChannel = mutableMapOf<String, Int>()
        for ((video, _) in scored) {
            val channel = video.uploaderName?.lowercase(Locale.ROOT)?.trim().orEmpty()
            if (channel.isNotEmpty() && (perChannel[channel] ?: 0) >= 3) continue
            result.add(video)
            if (channel.isNotEmpty()) perChannel[channel] = (perChannel[channel] ?: 0) + 1
            if (result.size >= limit) break
        }
        return result
    }
}
'''

def patch(root):
    src=root/"app/src/main"
    base=src/"java/com/github/libretube"
    helper=base/"helpers/VistaRecommendationEngine.kt"
    helper.write_text(KOTLIN,encoding="utf-8")

    vm=base/"ui/models/HomeViewModel.kt"
    replace(vm,"import com.github.libretube.helpers.PreferenceHelper",
            "import com.github.libretube.helpers.PreferenceHelper\nimport com.github.libretube.helpers.VistaRecommendationEngine")
    replace(vm,"    val trending: MutableLiveData",
            "    val recommendations: MutableLiveData<List<StreamItem>> = MutableLiveData(null)\n    val trending: MutableLiveData")
    replace(vm,"private val sections get() = listOf(trending, feed, bookmarks, playlists, continueWatching)",
            "private val sections get() = listOf(recommendations, trending, feed, bookmarks, playlists, continueWatching)")
    replace(vm,'''                    async { if (visibleItems.contains(WATCHING)) loadVideosToContinueWatching() }
                )
                loadedSuccessfully.value''',
            '''                    async { if (visibleItems.contains(WATCHING)) loadVideosToContinueWatching() }
                )
                loadPersonalizedRecommendations()
                loadedSuccessfully.value''')
    recommendation_function = '''    private suspend fun loadPersonalizedRecommendations() {
        if (!PreferenceHelper.getBoolean("vistatube_recommendations", true)) {
            recommendations.value = emptyList()
            return
        }
        // History remains on device, requests only fetch public related videos.
        val history = withContext(Dispatchers.IO) {
            DatabaseHelper.getWatchHistoryPage(1, 45)
        }
        val related = if (history.isEmpty()) emptyList() else withContext(Dispatchers.IO) {
            history.take(2).map { it.videoId }.distinct().flatMap { id ->
                runCatching {
                    MediaServiceRepository.instance.getStreams(id).relatedStreams
                }.getOrDefault(emptyList())
            }
        }
        val pool = related + feed.value.orEmpty() + trending.value?.second?.streams.orEmpty()
        recommendations.value = VistaRecommendationEngine.rank(pool, history)
    }

'''
    replace(vm,"    private suspend fun loadTrending(context: Context) {",
            recommendation_function+"    private suspend fun loadTrending(context: Context) {")

    home=base/"ui/fragments/HomeFragment.kt"
    replace(home,"    private val trendingAdapter = VideoCardsAdapter()",
            "    private val recommendedAdapter = VideoCardsAdapter()\n    private val trendingAdapter = VideoCardsAdapter()")
    replace(home,"        binding.trendingRV.adapter = trendingAdapter",
            "        binding.recommendedRV.adapter = recommendedAdapter\n        binding.trendingRV.adapter = trendingAdapter")
    replace(home,"            trending.observe(viewLifecycleOwner, ::showTrending)",
            "            trending.observe(viewLifecycleOwner, ::showTrending)\n            recommendations.observe(viewLifecycleOwner, ::showRecommendations)")
    replace(home,"    private fun showTrending(trends: Pair<TrendingCategory, TrendsViewModel.TrendingStreams>?) {",
        '''    private fun showRecommendations(videos: List<StreamItem>?) {
        val hasVideos = !videos.isNullOrEmpty()
        binding.recommendedHeader.isVisible = hasVideos
        binding.recommendedRV.isVisible = hasVideos
        recommendedAdapter.submitList(videos.orEmpty())
    }

    private fun showTrending(trends: Pair<TrendingCategory, TrendsViewModel.TrendingStreams>?) {''')
    layout=src/"res/layout/fragment_home.xml"
    tree=ET.parse(layout)
    scroll=next(x for x in tree.iter() if x.get(A+"id")=="@+id/scroll")
    column=next(x for x in scroll.iter() if x.tag=="LinearLayout" and x.get(A+"orientation")=="vertical")
    header=ET.Element("TextView",{
        A+"id":"@+id/recommended_header",A+"layout_width":"match_parent",
        A+"layout_height":"wrap_content",A+"paddingStart":"16dp",
        A+"paddingTop":"8dp",A+"paddingBottom":"8dp",
        A+"text":"Para ti",A+"textSize":"21sp",A+"textStyle":"bold",A+"visibility":"gone"
    })
    videos=ET.Element("androidx.recyclerview.widget.RecyclerView",{
        A+"id":"@+id/recommendedRV",A+"layout_width":"match_parent",
        A+"layout_height":"wrap_content",A+"nestedScrollingEnabled":"false",
        A+"visibility":"gone",
        APP+"layoutManager":"androidx.recyclerview.widget.LinearLayoutManager"
    })
    column.insert(1,header)
    column.insert(2,videos)
    layout.write_text('<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(tree.getroot(),encoding="unicode"),encoding="utf-8")
    ET.parse(layout)

    general=src/"res/xml/general_settings.xml"
    replace(general,'    <PreferenceCategory app:title="@string/customization">',
        '''    <PreferenceCategory app:title="@string/customization">
        <SwitchPreferenceCompat
            android:icon="@drawable/ic_suggestions"
            android:title="Recomendações personalizadas"
            android:summary="Usa o histórico local para sugerir vídeos semelhantes. Pode desativar quando quiser."
            android:defaultValue="true"
            app:key="vistatube_recommendations" />''')
    ET.parse(general)
    print("VistaTube 0.3: local recommendations, related videos, new home section")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    patch(parser.parse_args().upstream.resolve())
