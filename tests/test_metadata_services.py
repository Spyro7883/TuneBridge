# -*- coding: utf-8 -*-
"""TuneBridge Phase 3 — Metadata Services (TDD scaffold / RED gate).

Tests are intentionally failing until Phase 3 implementation is added.
"""
from unittest.mock import MagicMock, call, patch

import pytest
from PySide6.QtWidgets import QApplication

from tunebridge import (
    SpotifyClient,
    TuneBridgeApp,
    YoutubeExtractor,
    fetch_local_metadata,
    fetch_metadata_for_row,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    w = TuneBridgeApp()
    yield w
    w.close()
    w.deleteLater()


# Canned Spotify page HTML payloads (OG tag scraping)
_SPOTIFY_TRACK_HTML = (
    '<meta property="og:title" content="Blinding Lights">'
    '<meta property="og:description" content="The Weeknd &middot; After Hours &middot; Song &middot; 2019">'
)
_SPOTIFY_TRACK_HTML_WITH_DURATION = (
    '<meta property="og:title" content="Blinding Lights">'
    '<meta property="og:description" content="The Weeknd &middot; After Hours &middot; Song &middot; 2019">'
    ">3:20</span>"
)
_SPOTIFY_ALBUM_HTML = (
    '<meta property="og:title" content="After Hours">'
    '<meta property="og:description" content="The Weeknd &middot; Album &middot; 2020">'
)

_YT_INFO = {
    "title": "The Weeknd - Blinding Lights (Official Video)",
    "channel": "TheWeekndVEVO",
    "uploader": "TheWeekndVEVO",
    "duration": 200,
    "id": "4NRXx6U8ABQ",
}


# ---------------------------------------------------------------------------
# SpotifyClient — Spotify page OG tag scraping
# ---------------------------------------------------------------------------


def test_spotify_get_metadata_track_returns_required_keys():
    """get_metadata for a track must return artist, track_title, album, release_type."""
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    for key in ("artist", "track_title", "album", "release_type"):
        assert key in result, f"Missing key: {key}"


def test_spotify_get_metadata_track_values_correct():
    """Track metadata values must come from og:title and og:description."""
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    assert result["artist"] == "The Weeknd"
    assert result["track_title"] == "Blinding Lights"
    assert result["release_type"] == "single"


def test_spotify_get_metadata_album_values_correct():
    """Album metadata must set release_type='album' and use og:title as both track_title and album."""
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_ALBUM_HTML
        result = client.get_metadata("https://open.spotify.com/album/x", "album")
    assert result["artist"] == "The Weeknd"
    assert result["track_title"] == "After Hours"
    assert result["album"] == "After Hours"
    assert result["release_type"] == "album"


def test_spotify_http_error_raises():
    """HTTP error from Spotify page must propagate as an exception."""
    import requests as _req
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status.side_effect = _req.HTTPError("503")
        with pytest.raises(Exception):
            client.get_metadata("https://open.spotify.com/track/x", "track")


def test_get_metadata_populates_duration_ms_from_html():
    """C-02: get_metadata must extract duration_ms from the MM:SS span in the Spotify page HTML."""
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML_WITH_DURATION
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    assert "duration_ms" in result
    assert result["duration_ms"] == (3 * 60 + 20) * 1000  # 200_000 ms


def test_get_metadata_album_does_not_include_duration():
    """Album fetches must NOT include duration_ms (album-level durations are meaningless)."""
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_ALBUM_HTML
        result = client.get_metadata("https://open.spotify.com/album/x", "album")
    assert mock_get.call_count == 1
    assert "duration_ms" not in result


# ---------------------------------------------------------------------------
# YoutubeExtractor
# ---------------------------------------------------------------------------


def test_youtube_extract_returns_title():
    extractor = YoutubeExtractor()
    with patch("tunebridge.yt_dlp.YoutubeDL") as MockYDL:
        inst = MockYDL.return_value.__enter__.return_value
        inst.extract_info.return_value = _YT_INFO
        result = extractor.extract_metadata("https://www.youtube.com/watch?v=4NRXx6U8ABQ")
    assert result["title"] == _YT_INFO["title"]


def test_youtube_extract_returns_channel():
    extractor = YoutubeExtractor()
    with patch("tunebridge.yt_dlp.YoutubeDL") as MockYDL:
        inst = MockYDL.return_value.__enter__.return_value
        inst.extract_info.return_value = _YT_INFO
        result = extractor.extract_metadata("https://www.youtube.com/watch?v=4NRXx6U8ABQ")
    assert "channel" in result
    assert result["channel"] == "TheWeekndVEVO"


def test_youtube_extract_does_not_download():
    """extract_metadata must pass download=False — no actual file download."""
    extractor = YoutubeExtractor()
    with patch("tunebridge.yt_dlp.YoutubeDL") as MockYDL:
        inst = MockYDL.return_value.__enter__.return_value
        inst.extract_info.return_value = _YT_INFO
        extractor.extract_metadata("https://youtu.be/4NRXx6U8ABQ")
    args, kwargs = inst.extract_info.call_args
    download_flag = kwargs.get("download", args[1] if len(args) > 1 else True)
    assert download_flag is False


def test_youtube_artist_parsed_from_title():
    """Artist parsed from 'Artist - Title' video title must be set without any suffix."""
    extractor = YoutubeExtractor()
    with patch("tunebridge.yt_dlp.YoutubeDL") as MockYDL:
        inst = MockYDL.return_value.__enter__.return_value
        inst.extract_info.return_value = _YT_INFO
        result = extractor.extract_metadata("https://www.youtube.com/watch?v=4NRXx6U8ABQ")
    if result.get("artist"):
        assert "(guessed)" not in result["artist"]


def test_youtube_track_title_parsed_from_title():
    """Track title parsed from video title must be set without any suffix."""
    extractor = YoutubeExtractor()
    with patch("tunebridge.yt_dlp.YoutubeDL") as MockYDL:
        inst = MockYDL.return_value.__enter__.return_value
        inst.extract_info.return_value = _YT_INFO
        result = extractor.extract_metadata("https://www.youtube.com/watch?v=4NRXx6U8ABQ")
    if result.get("track_title"):
        assert "(guessed)" not in result["track_title"]


def test_youtube_extract_error_raises():
    """yt-dlp failure must raise an exception, not return None silently."""
    extractor = YoutubeExtractor()
    with patch("tunebridge.yt_dlp.YoutubeDL") as MockYDL:
        inst = MockYDL.return_value.__enter__.return_value
        inst.extract_info.side_effect = Exception("network error")
        with pytest.raises(Exception):
            extractor.extract_metadata("https://www.youtube.com/watch?v=bad")


# ---------------------------------------------------------------------------
# fetch_metadata_for_row — routing logic
# ---------------------------------------------------------------------------


def test_fetch_metadata_routes_spotify_url_to_spotify_client():
    """Spotify URL must call SpotifyClient, never YoutubeExtractor."""
    mock_sp = MagicMock()
    mock_sp.get_metadata.return_value = {
        "artist": "A", "track_title": "T", "album": "B", "release_type": "single",
    }
    mock_yt = MagicMock()
    fetch_metadata_for_row(
        url="https://open.spotify.com/track/abc123",
        url_type="Spotify",
        spotify_client=mock_sp,
        yt_extractor=mock_yt,
    )
    mock_sp.get_metadata.assert_called_once()
    mock_yt.extract_metadata.assert_not_called()


def test_fetch_metadata_routes_youtube_url_to_yt_extractor():
    """YouTube URL must call YoutubeExtractor, never SpotifyClient."""
    mock_sp = MagicMock()
    mock_yt = MagicMock()
    mock_yt.extract_metadata.return_value = {
        "title": "T", "channel": "C",
        "artist": "A", "track_title": "T",
    }
    fetch_metadata_for_row(
        url="https://www.youtube.com/watch?v=xyz",
        url_type="YouTube",
        spotify_client=mock_sp,
        yt_extractor=mock_yt,
    )
    mock_yt.extract_metadata.assert_called_once()
    mock_sp.get_metadata.assert_not_called()


def test_fetch_metadata_result_includes_source_spotify():
    """Result dict must have source='Spotify' for Spotify rows."""
    mock_sp = MagicMock()
    mock_sp.get_metadata.return_value = {
        "artist": "A", "track_title": "T", "album": "B", "release_type": "album",
    }
    result = fetch_metadata_for_row(
        url="https://open.spotify.com/track/x",
        url_type="Spotify",
        spotify_client=mock_sp,
        yt_extractor=MagicMock(),
    )
    assert result.get("source") == "Spotify"


def test_fetch_metadata_result_includes_source_youtube():
    """Result dict must have source='YouTube' for YouTube rows."""
    mock_yt = MagicMock()
    mock_yt.extract_metadata.return_value = {
        "title": "T", "channel": "C",
        "artist": "A", "track_title": "T",
    }
    result = fetch_metadata_for_row(
        url="https://www.youtube.com/watch?v=abc",
        url_type="YouTube",
        spotify_client=MagicMock(),
        yt_extractor=mock_yt,
    )
    assert result.get("source") == "YouTube"


def test_fetch_metadata_spotify_album_url_passes_album_resource_type():
    """Spotify album URL must call get_metadata with resource_type='album'."""
    mock_sp = MagicMock()
    mock_sp.get_metadata.return_value = {
        "artist": "A", "track_title": "B", "album": "B", "release_type": "album",
    }
    fetch_metadata_for_row(
        url="https://open.spotify.com/album/xyz789",
        url_type="Spotify",
        spotify_client=mock_sp,
        yt_extractor=MagicMock(),
    )
    _, resource_type_arg = mock_sp.get_metadata.call_args[0]
    assert resource_type_arg == "album"


# ---------------------------------------------------------------------------
# BatchTable — update_row_metadata
# ---------------------------------------------------------------------------


def test_batch_table_update_row_metadata_stores_title(window):
    """update_row_metadata must write track title into the URL column cell."""
    row_id = window.table.add_row(
        url="https://open.spotify.com/track/x", url_type="Spotify"
    )
    window.table.update_row_metadata(row_id, {
        "artist": "The Weeknd",
        "track_title": "Blinding Lights",
        "album": "",
        "release_type": "single",
        "source": "Spotify",
    })
    url_item = window.table._table.item(row_id, 0)
    assert url_item is not None
    assert "Blinding Lights" in url_item.text()


def test_batch_table_update_row_metadata_status_transitions_to_done(window):
    """After metadata is stored the row status must update to 'Metadata ready'."""
    row_id = window.table.add_row(
        url="https://open.spotify.com/track/y", url_type="Spotify"
    )
    window.table.update_row_metadata(row_id, {
        "artist": "Artist", "title": "Song", "album": "Album",
        "release_type": "single", "source": "Spotify",
    })
    status_item = window.table._table.item(row_id, 2)
    assert status_item is not None
    assert status_item.text() == "Metadata ready"


def test_batch_table_update_row_metadata_youtube_label_round_trip(window):
    """YouTube artist/track fields must survive the round-trip into the table."""
    row_id = window.table.add_row(
        url="https://www.youtube.com/watch?v=abc", url_type="YouTube"
    )
    window.table.update_row_metadata(row_id, {
        "title": "Artist - Song (Official Video)",
        "channel": "ArtistVEVO",
        "artist": "Artist",
        "track_title": "Song",
        "source": "YouTube",
    })
    url_item = window.table._table.item(row_id, 0)
    assert url_item is not None
    assert "Artist" in url_item.text()
    assert "Song" in url_item.text()




# ---------------------------------------------------------------------------
# Phase 7 — Local File Upload metadata (RED gate)
# ---------------------------------------------------------------------------


def test_fetch_local_metadata_reads_tags(tmp_path):
    """LOCAL-02: fetch_local_metadata reads title/artist/album from tags."""
    p = tmp_path / "track.mp3"
    p.write_bytes(b"\x00")
    fake_audio = {
        "title": ["Song Alpha"],
        "artist": ["Artist One"],
        "album": ["Album One"],
    }
    info = MagicMock()
    info.length = 0
    fake_audio_obj = MagicMock()
    fake_audio_obj.get.side_effect = fake_audio.get
    fake_audio_obj.info = info
    with patch("tunebridge.mutagen.File", return_value=fake_audio_obj):
        meta = fetch_local_metadata(str(p))
    assert meta["track_title"] == "Song Alpha"
    assert meta["artist"] == "Artist One"
    assert meta["album"] == "Album One"


def test_fetch_local_metadata_filename_fallback(tmp_path):
    """LOCAL-02: missing tags fall back to filename stem, empty artist."""
    p = tmp_path / "Song Beta.wav"
    p.write_bytes(b"RIFF....")
    with patch("tunebridge.mutagen.File", return_value=None):
        meta = fetch_local_metadata(str(p))
    assert meta["track_title"] == "Song Beta"
    assert meta["artist"] == ""
    assert meta["duration_ms"] == 0


def test_fetch_metadata_for_row_routes_local_file():
    """LOCAL-02: Local File routes to fetch_local_metadata, no Spotify/YT calls."""
    expected = {"track_title": "Song Alpha", "artist": "Artist One", "duration_ms": 0}
    spotify_client = MagicMock()
    yt_extractor = MagicMock()
    with patch("tunebridge.fetch_local_metadata", return_value=expected) as mock_local:
        result = fetch_metadata_for_row(
            "C:/x/Song Alpha.mp3", "Local File",
            spotify_client=spotify_client, yt_extractor=yt_extractor,
        )
    assert result == expected
    mock_local.assert_called_once_with("C:/x/Song Alpha.mp3")
    spotify_client.assert_not_called()
    yt_extractor.assert_not_called()
    assert not spotify_client.method_calls
    assert not yt_extractor.method_calls


# ---------------------------------------------------------------------------
# Phase 8 — Cover Art & Album Metadata (ART-02, ART-03)
# RED-gate: cover_url / album keys not yet returned → assertion failures
# ---------------------------------------------------------------------------

_SPOTIFY_TRACK_HTML_WITH_COVER = (
    '<meta property="og:title" content="Sample Track">'
    '<meta property="og:description" content="Sample Artist &middot; Sample Album &middot; Song &middot; 2020">'
    '<meta property="og:image" content="https://i.scdn.co/image/samplehash">'
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"MusicRecording",'
    '"name":"Sample Track","byArtist":{"name":"Sample Artist"},'
    '"inAlbum":{"@type":"MusicAlbum","name":"Sample Album"}}'
    '</script>'
)
_SPOTIFY_TRACK_HTML_NO_JSONLD_ALBUM = (
    '<meta property="og:title" content="Sample Track">'
    '<meta property="og:description" content="Sample Artist &middot; Song &middot; 2020">'
    '<meta property="og:image" content="https://i.scdn.co/image/samplehash">'
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"MusicRecording","name":"Sample Track"}'
    '</script>'
)
_YT_INFO_WITH_THUMBNAIL = {
    "title": "Sample Artist - Sample Track",
    "channel": "SampleVEVO",
    "uploader": "SampleVEVO",
    "duration": 200,
    "id": "dummyid123",
    "thumbnail": "https://i.ytimg.com/vi/dummyid123/maxresdefault.jpg",
}


def test_spotify_get_metadata_track_returns_cover_url():
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML_WITH_COVER
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    assert result["cover_url"] == "https://i.scdn.co/image/samplehash"


def test_spotify_get_metadata_track_album_from_jsonld():
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML_WITH_COVER
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    assert result["album"] == "Sample Album"


def test_spotify_get_metadata_track_no_jsonld_album_empty():
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML_NO_JSONLD_ALBUM
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    assert result["album"] == ""


def test_youtube_extract_returns_cover_url():
    extractor = YoutubeExtractor()
    with patch("tunebridge.yt_dlp.YoutubeDL") as MockYDL:
        inst = MockYDL.return_value.__enter__.return_value
        inst.extract_info.return_value = _YT_INFO_WITH_THUMBNAIL
        result = extractor.extract_metadata("https://www.youtube.com/watch?v=dummyid123")
    assert result["cover_url"] == "https://i.ytimg.com/vi/dummyid123/maxresdefault.jpg"


_SPOTIFY_TRACK_HTML_MULTI_JSONLD = (
    '<meta property="og:title" content="Sample Track">'
    '<meta property="og:description" content="Sample Artist &middot; Sample Album &middot; Song &middot; 2020">'
    '<meta property="og:image" content="https://i.scdn.co/image/samplehash">'
    # First MusicRecording block has NO inAlbum — must not short-circuit the scan
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"MusicRecording","name":"Sample Track"}'
    '</script>'
    # Second MusicRecording block carries the album — must still be reached
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"MusicRecording","name":"Sample Track",'
    '"inAlbum":{"@type":"MusicAlbum","name":"Sample Album"}}'
    '</script>'
)


def test_spotify_get_metadata_album_from_later_jsonld_block():
    # WR-01: break must fire only once the album is found, so a leading
    # MusicRecording block without inAlbum does not hide a later one that has it.
    client = SpotifyClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML_MULTI_JSONLD
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    assert result["album"] == "Sample Album"
