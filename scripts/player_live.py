#!/usr/bin/env python3
"""VistaTube 0.3: video surface and livestream playback."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

def exact(path, before, after):
    content=path.read_text(encoding="utf-8")
    if content.count(before)!=1:
        raise AssertionError(f"{path}: expected exactly one match: {before[:90]!r}; found {content.count(before)}")
    path.write_text(content.replace(before,after),encoding="utf-8")

def patch(path):
    res=path/"app/src/main/res"
    player_layout=res/"layout/fragment_player.xml"
    # TextureView stays synchronized with MotionLayout. SurfaceView can retain
    # the miniplayer's 100dp surface size on some Android devices.
    exact(player_layout,'app:surface_type="surface_view" />',
          'app:surface_type="texture_view"\n        app:resize_mode="fit" />')
    ET.parse(player_layout)

    service=path/"app/src/main/java/com/github/libretube/services/OnlinePlayerService.kt"
    needle="""        when {
            // SABR"""
    replacement="""        when {
            // Native live HLS preferred. Do not build static DASH for live segments.
            streams.isLive && !streams.hls.isNullOrBlank() -> {
                val item = createMediaItem(
                    ProxyHelper.rewriteUrlUsingProxyPreference(streams.hls).toUri(),
                    MimeTypes.APPLICATION_M3U8, streams
                )
                val source = HlsMediaSource.Factory(DefaultDataSource.Factory(this))
                    .setPlaylistParserFactory(YoutubeHlsPlaylistParser.Factory())
                    .createMediaSource(item)
                exoPlayer?.setMediaSource(source)
                return
            }
            // When live HLS is not exposed, use YouTube's actual live DASH.
            streams.isLive && !streams.dash.isNullOrBlank() -> {
                val item = createMediaItem(
                    ProxyHelper.rewriteUrlUsingProxyPreference(streams.dash).toUri(),
                    MimeTypes.APPLICATION_MPD, streams
                )
                exoPlayer?.setMediaItem(item)
                return
            }
            // SABR"""
    exact(service,needle,replacement)
    print("VistaTube 0.3: TextureView, live HLS/DASH routing")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("upstream", type=Path)
    patch(p.parse_args().upstream.resolve())
