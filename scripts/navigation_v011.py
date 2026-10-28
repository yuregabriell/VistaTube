#!/usr/bin/env python3
"""VistaTube 0.11: Home search exit and independent discovery lifecycle."""
from pathlib import Path
import argparse

def change(file, old, new):
    s=file.read_text(encoding="utf-8")
    n=s.count(old)
    if n!=1: raise AssertionError(f"{file} must contain {old[:80]!r} exactly once; got {n}")
    file.write_text(s.replace(old,new),encoding="utf-8")

def patch(root):
    base=root/"app/src/main/java/com/github/libretube"
    main=base/"ui/activities/MainActivity.kt"
    vm=base/"ui/models/HomeViewModel.kt"
    home=base/"ui/fragments/HomeFragment.kt"

    change(main,"import android.os.Bundle","import android.os.Bundle\nimport android.view.inputmethod.InputMethodManager\nimport android.content.Context")
    change(main,"""    private var shouldOpenSuggestions = true""",
        """    private var shouldOpenSuggestions = true
    private var vistaClosingSearchForBottomNav = false""")
    change(main,"""        binding.bottomNav.setOnItemReselectedListener {
            if (it.itemId != navController.currentDestination?.id) {""",
        """        binding.bottomNav.setOnItemReselectedListener {
            // A tap on Home must close search even when Home is already selected.
            vistaCloseSearchForBottomNav()
            if (it.itemId != navController.currentDestination?.id) {""")

    change(main,"""            override fun onMenuItemActionCollapse(item: MenuItem): Boolean {
                // Handover back press""",
        """            override fun onMenuItemActionCollapse(item: MenuItem): Boolean {
                // Bottom navigation explicitly changes destinations. Do not
                // invoke Back and do not refuse to collapse the search UI.
                if (vistaClosingSearchForBottomNav) return true
                // Handover back press""")
    change(main,"""    private fun navigateToBottomSelectedItem(item: MenuItem): Boolean {""",
        """    private fun vistaCloseSearchForBottomNav() {
        if (!::searchItem.isInitialized || !::searchView.isInitialized) return
        vistaClosingSearchForBottomNav = true
        shouldOpenSuggestions = false
        try {
            searchView.setQuery("", false)
            searchView.clearFocus()
            searchViewModel.setQuery(null)
            if (searchItem.isActionViewExpanded) {
                searchItem.collapseActionView()
            }
            searchView.isIconified = true
            val keyboard = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            keyboard.hideSoftInputFromWindow(searchView.windowToken, 0)
        } finally {
            shouldOpenSuggestions = true
            vistaClosingSearchForBottomNav = false
        }
    }

    private fun navigateToBottomSelectedItem(item: MenuItem): Boolean {""")
    change(main,"""        // Remove focus from search view when navigating to bottom view.
        searchItem.collapseActionView()

        return item.onNavDestinationSelected(navController)""",
        """        // Reset query and keyboard first, then navigate. The collapse
        // listener must not put the user back into Search.
        vistaCloseSearchForBottomNav()
        return item.onNavDestinationSelected(navController)""")

    # Leave recommendations outside loadHomeJob's cancellation scope.
    # Previously: every automatic refresh of an underpopulated Home
    # increments generation (every 45s) and cancels a long-running search.
    # A perpetually sparse feed thus remains perpetually sparse.
    change(vm,"""    private var lastAutomaticRefreshElapsed = 0L""",
        """    private var lastAutomaticRefreshElapsed = 0L
    private var vistaDiscoveryJob: Job? = null""")
    change(vm,"""        refreshIndex++
        recommendationsGeneration++
        recommendationsLoadingMore = false

        loadHomeJob?.cancel()""",
        """        refreshIndex++
        if (vistaDiscoveryJob?.isActive != true) {
            recommendationsGeneration++
            recommendationsLoadingMore = false
        }

        loadHomeJob?.cancel()""")
    change(vm,"""                // Launch search/related recommendations independently.
                // Network failures must never leave the Home screen invisible.
                launch {
                    try {
                        loadPersonalizedRecommendations()
                    } catch (cancel: CancellationException) {
                        throw cancel
                    } catch (error: Exception) {
                        android.util.Log.w("VistaTubeHome", "Recommendation load failed", error)
                        if (recommendations.value.isNullOrEmpty()) {
                            recommendations.value = feed.value.orEmpty()
                        }
                    }
                }""",
        """                // Discovery belongs to ViewModel scope, not to the ten-second
                // Home load job. Do not cancel requests simply because the
                // foreground auto-refresh happened while only 1-2 videos exist.
                if (vistaDiscoveryJob?.isActive != true) {
                    vistaDiscoveryJob = viewModelScope.launch {
                        try {
                            loadPersonalizedRecommendations()
                        } catch (cancel: CancellationException) {
                            throw cancel
                        } catch (error: Exception) {
                            android.util.Log.e("VistaTubeDiscovery", "Feed failed", error)
                            if (recommendations.value.isNullOrEmpty()) {
                                recommendations.value = feed.value.orEmpty()
                            }
                        }
                    }
                }""")
    # Asynchronous feed can expand while the nested ScrollView is too short to
    # emit onScrollChange. Submit + layout observer request more candidates when
    # needed without relying on physical scrolling.
    change(home,"""        recommendedAdapter.submitList(videos.orEmpty())""",
        """        recommendedAdapter.submitList(videos.orEmpty()) {
            val current = _binding ?: return@submitList
            current.scroll.post {
                val visible = current.recommendedRV
                if (!visible.isVisible) return@post
                // If the first batch has fewer than ten entries there may be
                // nothing to scroll. Prefetch independently of touch events.
                if (recommendedAdapter.itemCount < 10) {
                    homeViewModel.ensureRecommendations()
                } else if (!current.scroll.canScrollVertically(1)) {
                    homeViewModel.loadMoreRecommendations()
                }
            }
        }""")
    print("VistaTube v0.11: Home tab closes search; discovery survives automatic refresh; short feed triggers prefetch")

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    patch(parser.parse_args().upstream.resolve())
