#!/usr/bin/env python3
"""VistaTube 0.5: Google Cast sender beta for directly playable HLS/DASH/MP4."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

def replace_once(path, old, new):
    c=path.read_text(encoding="utf-8")
    n=c.count(old)
    if n!=1: raise AssertionError(f"{path}: expected one match {old[:75]!r}; got {n}")
    path.write_text(c.replace(old,new),encoding="utf-8")

OPTIONS='''package com.github.libretube.cast

import android.content.Context
import com.google.android.gms.cast.CastMediaControlIntent
import com.google.android.gms.cast.framework.CastOptions
import com.google.android.gms.cast.framework.OptionsProvider
import com.google.android.gms.cast.framework.SessionProvider

/** Default Media Receiver; Cast is supported for direct, TV-accessible URLs. */
class VistaCastOptionsProvider : OptionsProvider {
    override fun getCastOptions(context: Context): CastOptions =
        CastOptions.Builder()
            .setReceiverApplicationId(CastMediaControlIntent.DEFAULT_MEDIA_RECEIVER_APPLICATION_ID)
            .build()

    override fun getAdditionalSessionProviders(context: Context): List<SessionProvider>? = null
}
'''

HELPER='''package com.github.libretube.cast

import android.net.Uri
import com.github.libretube.api.obj.Streams
import com.google.android.gms.cast.MediaInfo
import com.google.android.gms.cast.MediaMetadata
import com.google.android.gms.common.images.WebImage

/**
 * Google Cast plays a URL from the TV, NOT from the phone. For regular
 * YouTube SABR or separate video-only/audio-only tracks the app cannot just
 * forward the handset's ExoPlayer source to the Default Receiver.
 */
object VistaCastMedia {
    fun mediaInfo(streams: Streams): MediaInfo? {
        val source = when {
            !streams.hls.isNullOrBlank() ->
                streams.hls to "application/x-mpegURL"
            !streams.dash.isNullOrBlank() ->
                streams.dash to "application/dash+xml"
            else -> streams.videoStreams.firstOrNull {
                it.videoOnly != true &&
                it.url?.startsWith("https://") == true &&
                (it.mimeType?.startsWith("video/") == true)
            }?.let { it.url.orEmpty() to (it.mimeType ?: "video/mp4") }
        } ?: return null

        val (url, mime) = source
        if (!url.startsWith("https://") && !url.startsWith("http://")) return null

        val metadata = MediaMetadata(MediaMetadata.MEDIA_TYPE_MOVIE).apply {
            putString(MediaMetadata.KEY_TITLE, streams.title)
            putString(MediaMetadata.KEY_SUBTITLE, streams.uploader)
            if (streams.thumbnailUrl.startsWith("https://")) {
                addImage(WebImage(Uri.parse(streams.thumbnailUrl)))
            }
        }
        return MediaInfo.Builder(url)
            .setContentType(mime)
            .setStreamType(if (streams.isLive)
                MediaInfo.STREAM_TYPE_LIVE else MediaInfo.STREAM_TYPE_BUFFERED)
            .setMetadata(metadata)
            .build()
    }
}
'''

def apply(root):
    base=root/"app/src/main"
    gradle=root/"app/build.gradle.kts"
    replace_once(gradle,
        '''dependencies {
''',
        '''dependencies {
    // Android Sender Cast SDK; TV must fetch media URL independently.
    implementation("com.google.android.gms:play-services-cast-framework:22.3.1")
''')
    manifest=base/"AndroidManifest.xml"
    replace_once(manifest,
        '''    <application
''',
        '''    <application
''')
    replace_once(manifest,
        '''        tools:targetApi="tiramisu">''',
        '''        tools:targetApi="tiramisu">
        <meta-data
            android:name="com.google.android.gms.cast.framework.OPTIONS_PROVIDER_CLASS_NAME"
            android:value="com.github.libretube.cast.VistaCastOptionsProvider" />''')
    ET.parse(manifest)

    dest=base/"java/com/github/libretube/cast"
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"VistaCastOptionsProvider.kt").write_text(OPTIONS,encoding="utf-8")
    (dest/"VistaCastMedia.kt").write_text(HELPER,encoding="utf-8")

    toolbar=base/"res/menu/action_bar.xml"
    replace_once(toolbar,
        '''    <item
        android:id="@+id/action_settings"''',
        '''    <item
        android:id="@+id/action_cast"
        android:title="Transmitir para TV"
        app:actionProviderClass="androidx.mediarouter.app.MediaRouteActionProvider"
        app:showAsAction="always" />

    <item
        android:id="@+id/action_settings"''')
    ET.parse(toolbar)

    activity=base/"java/com/github/libretube/ui/activities/MainActivity.kt"
    replace_once(activity,
        '''import com.google.android.material.dialog.MaterialAlertDialogBuilder''',
        '''import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.gms.cast.framework.CastButtonFactory''')
    replace_once(activity,
        '''        menuInflater.inflate(R.menu.action_bar, menu)

        // stuff for the search in the topBar''',
        '''        menuInflater.inflate(R.menu.action_bar, menu)
        // Device discovery and connection/disconnection are handled by Cast SDK.
        runCatching {
            CastButtonFactory.setUpMediaRouteButton(
                applicationContext, menu, R.id.action_cast
            )
        }

        // stuff for the search in the topBar''')

    player=base/"java/com/github/libretube/ui/fragments/PlayerFragment.kt"
    replace_once(player,
        '''import com.google.android.material.snackbar.Snackbar''',
        '''import com.google.android.material.snackbar.Snackbar
import com.github.libretube.cast.VistaCastMedia
import com.google.android.gms.cast.framework.CastContext
import com.google.android.gms.cast.framework.CastSession
import com.google.android.gms.cast.framework.SessionManagerListener
import com.google.android.gms.cast.MediaLoadRequestData
import android.widget.Toast''')
    replace_once(player,
        '''    private lateinit var streams: Streams''',
        '''    private lateinit var streams: Streams
    private var lastCastVideoId: String? = null

    // Attach only while the player screen is resumed, avoiding leaks.
    private val vistaCastSessionListener = object : SessionManagerListener<CastSession> {
        override fun onSessionStarting(session: CastSession) = Unit
        override fun onSessionStarted(session: CastSession, sessionId: String) {
            sendCurrentVideoToCast()
        }
        override fun onSessionStartFailed(session: CastSession, error: Int) = Unit
        override fun onSessionEnding(session: CastSession) = Unit
        override fun onSessionEnded(session: CastSession, error: Int) {
            lastCastVideoId = null
        }
        override fun onSessionResuming(session: CastSession, sessionId: String) = Unit
        override fun onSessionResumed(session: CastSession, wasSuspended: Boolean) {
            sendCurrentVideoToCast()
        }
        override fun onSessionResumeFailed(session: CastSession, error: Int) = Unit
        override fun onSessionSuspended(session: CastSession, reason: Int) = Unit
    }

    private fun sendCurrentVideoToCast() {
        if (isOffline || !::streams.isInitialized || !isAdded) return
        val castSession = runCatching {
            CastContext.getSharedInstance(requireContext()).sessionManager.currentCastSession
        }.getOrNull() ?: return
        if (!castSession.isConnected || lastCastVideoId == videoId) return
        val mediaInfo = VistaCastMedia.mediaInfo(streams)
        if (mediaInfo == null) {
            Toast.makeText(requireContext(),
                "Este vídeo usa formatos separados/SABR que o Chromecast ainda não consegue abrir.",
                Toast.LENGTH_LONG).show()
            return
        }
        val remote = castSession.remoteMediaClient ?: return
        val request = MediaLoadRequestData.Builder()
            .setMediaInfo(mediaInfo)
            .setAutoplay(true)
            .build()
        remote.load(request).setResultCallback { result ->
            if (!isAdded) return@setResultCallback
            if (result.status.isSuccess) {
                lastCastVideoId = videoId
                if (::playerController.isInitialized) playerController.pause()
            } else {
                Toast.makeText(requireContext(),
                    "A TV não conseguiu abrir esta fonte. Verifica a ligação/compatibilidade.",
                    Toast.LENGTH_LONG).show()
            }
        }
    }
''')
    replace_once(player,
        '''    override fun onResume() {
        super.onResume()''',
        '''    override fun onResume() {
        super.onResume()
        runCatching {
            CastContext.getSharedInstance(requireContext()).sessionManager
                .addSessionManagerListener(vistaCastSessionListener, CastSession::class.java)
        }''')
    replace_once(player,
        '''    override fun onPause() {
''',
        '''    override fun onPause() {
        runCatching {
            CastContext.getSharedInstance(requireContext()).sessionManager
                .removeSessionManagerListener(vistaCastSessionListener, CastSession::class.java)
        }
''')
    replace_once(player,
        '''    private fun updatePlayerView() {
        dismissCommentsSheet()''',
        '''    private fun updatePlayerView() {
        lastCastVideoId = null
        if (isAdded) sendCurrentVideoToCast()
        dismissCommentsSheet()''')
    print("VistaTube Cast beta: sender discovery, session loading for direct HLS/DASH/MP4")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    apply(parser.parse_args().upstream.resolve())
