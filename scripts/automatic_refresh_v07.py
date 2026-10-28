#!/usr/bin/env python3
"""VistaTube 0.7: lifecycle-aware automatic refresh across Home and Library."""
from pathlib import Path
import argparse

def exact(path, old, new):
    content=path.read_text(encoding="utf-8")
    count=content.count(old)
    if count!=1: raise AssertionError(f"{path}: expected 1 match but got {count}: {old[:110]!r}")
    path.write_text(content.replace(old,new),encoding="utf-8")

def patch(root):
    base=root/"app/src/main/java/com/github/libretube"
    home=base/"ui/fragments/HomeFragment.kt"
    homevm=base/"ui/models/HomeViewModel.kt"
    subs=base/"ui/fragments/SubscriptionsFragment.kt"
    lib=base/"ui/fragments/LibraryFragment.kt"

    # A single non-overlapping refresh gate shared across fragment recreations.
    # Empty recommendations retry after 45s; nonempty feeds update after 3min.
    exact(homevm, "import android.content.Context", 
        "import android.content.Context\nimport android.os.SystemClock")
    exact(homevm, "    private var loadHomeJob: Job? = null",
        """    private var loadHomeJob: Job? = null
    private var lastAutomaticRefreshElapsed = 0L

    fun shouldRefreshAutomatically(): Boolean {
        val now = SystemClock.elapsedRealtime()
        val hasVideos = !recommendations.value.isNullOrEmpty()
        val minimumGap = if (hasVideos) 180_000L else 45_000L
        if (lastAutomaticRefreshElapsed != 0L &&
            now - lastAutomaticRefreshElapsed < minimumGap) return false
        lastAutomaticRefreshElapsed = now
        return true
    }""")

    # Do not allow subscription lookup to indefinitely delay the first videos.
    exact(homevm, """        val subscriptionInfo = withContext(Dispatchers.IO) {
            runCatching { SubscriptionHelper.getSubscriptions() }.getOrDefault(emptyList())
        }""", """        val subscriptionInfo = withTimeoutOrNull(6_000L) {
            withContext(Dispatchers.IO) {
                runCatching { SubscriptionHelper.getSubscriptions() }.getOrDefault(emptyList())
            }
        }.orEmpty()""")

    # Keep the page usable from initial frame. The observer is connected before
    # onResume, and automatic refresh will trigger without swipes.
    exact(home, "import android.view.View", """import android.view.View
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch""")
    exact(home, """    private var _binding: FragmentHomeBinding? = null""",
        """    private var automaticRefreshJob: Job? = null
    private var _binding: FragmentHomeBinding? = null""")

    # Completely replace old conditional onResume: the first entry always asks
    # for content, re-entry refreshes after a bounded staleness interval, and
    # a visible page refreshes periodically without manual gestures.
    begin="""    override fun onResume() {
        super.onResume()

        // Avoid re-fetching when re-entering the screen if it was loaded successfully, except when
        // the value of trending region has changed
        val isTrendingRegionChanged = homeViewModel.trending.value?.let {
            it.second.region != PreferenceHelper.getTrendingRegion(requireContext())
        } == true

        if (homeViewModel.loadedSuccessfully.value == false || isTrendingRegionChanged) {
            fetchHomeFeed()
        }
    }"""
    replacement="""    override fun onResume() {
        super.onResume()
        automaticRefreshJob?.cancel()
        automaticRefreshJob = viewLifecycleOwner.lifecycleScope.launch {
            // Update immediately on first visit, then every three minutes while
            // visible. Retry empty feeds sooner. This coroutine stops on pause.
            while (isActive) {
                if (homeViewModel.shouldRefreshAutomatically()) {
                    fetchHomeFeed()
                }
                delay(30_000L)
            }
        }
    }

    override fun onPause() {
        automaticRefreshJob?.cancel()
        automaticRefreshJob = null
        super.onPause()
    }"""
    exact(home,begin,replacement)

    # The Home no longer waits until a user pulls to refresh; keep gesture as
    # an optional manual override, not a requirement for displaying videos.
    # The existing refresh listener stays for users who want it.

    # Subscriptions: on-enter refresh already exists since v0.5. Add periodic
    # checks only while this Fragment is foreground, avoid duplicate jobs.
    exact(subs, "import kotlinx.coroutines.Dispatchers",
        """import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive""")
    exact(subs, "    private var _binding: FragmentSubscriptionsBinding? = null",
        """    private var subscriptionsRefreshJob: Job? = null
    private var _binding: FragmentSubscriptionsBinding? = null""")
    exact(subs, """    override fun onResume() {
        super.onResume()
        // New uploads are fetched automatically when opening this tab.
        viewModel.fetchFeed(requireContext(), forceRefresh = true)
        viewModel.fetchSubscriptions(requireContext())
    }""",
        """    override fun onResume() {
        super.onResume()
        subscriptionsRefreshJob?.cancel()
        subscriptionsRefreshJob = viewLifecycleOwner.lifecycleScope.launch {
            // Always refresh on entering Subscriptions. Repeat every 5min
            // while visible; no network polling when the page is paused.
            while (isActive) {
                val ctx = context ?: break
                viewModel.fetchFeed(ctx, forceRefresh = true)
                viewModel.fetchSubscriptions(ctx)
                delay(300_000L)
            }
        }
    }

    override fun onPause() {
        subscriptionsRefreshJob?.cancel()
        subscriptionsRefreshJob = null
        super.onPause()
    }""")

    # Library: original initial load plus onResume history preview introduced
    # in v0.2. Consolidate to onResume so returning from other screens also
    # updates playlists, bookmarks and recent watch history automatically.
    exact(lib, """        fetchPlaylists()
        initBookmarks()

        binding.playlistRefresh.isEnabled""",
        """        binding.playlistRefresh.isEnabled""")
    exact(lib, """    override fun onResume() {
        super.onResume()
        loadHistoryPreview()
    }""",
        """    override fun onResume() {
        super.onResume()
        fetchPlaylists()
        initBookmarks()
        loadHistoryPreview()
    }""")

    print("VistaTube 0.7: automatic Home refresh on enter and foreground intervals, Subscriptions auto polling, Library reload on resume")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    patch(parser.parse_args().upstream.resolve())
