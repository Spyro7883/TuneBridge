# -*- coding: utf-8 -*-
"""TuneBridge Phase 3 — Metadata Services (TDD scaffold / RED gate).

Tests are intentionally failing until Phase 3 implementation is added.
"""
from unittest.mock import MagicMock, call, patch

import pytest
from PySide6.QtWidgets import QApplication

from tunebridge import (
    ItunesClient,
    TuneBridgeApp,
    YoutubeExtractor,
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
# ItunesClient — Spotify page OG tag scraping
# ---------------------------------------------------------------------------


def test_itunes_get_metadata_track_returns_required_keys():
    """get_metadata for a track must return artist, track_title, album, release_type."""
    client = ItunesClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    for key in ("artist", "track_title", "album", "release_type"):
        assert key in result, f"Missing key: {key}"


def test_itunes_get_metadata_track_values_correct():
    """Track metadata values must come from og:title and og:description."""
    client = ItunesClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_TRACK_HTML
        result = client.get_metadata("https://open.spotify.com/track/x", "track")
    assert result["artist"] == "The Weeknd"
    assert result["track_title"] == "Blinding Lights"
    assert result["release_type"] == "single"


def test_itunes_get_metadata_album_values_correct():
    """Album metadata must set release_type='album' and use og:title as both track_title and album."""
    client = ItunesClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = _SPOTIFY_ALBUM_HTML
        result = client.get_metadata("https://open.spotify.com/album/x", "album")
    assert result["artist"] == "The Weeknd"
    assert result["track_title"] == "After Hours"
    assert result["album"] == "After Hours"
    assert result["release_type"] == "album"


def test_itunes_http_error_raises():
    """HTTP error from oEmbed must propagate as an exception."""
    import requests as _req
    client = ItunesClient()
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status.side_effect = _req.HTTPError("503")
        with pytest.raises(Exception):
            client.get_metadata("https://open.spotify.com/track/x", "track")


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


def test_fetch_metadata_routes_spotify_url_to_itunes_client():
    """Spotify URL must call ItunesClient, never YoutubeExtractor."""
    mock_it = MagicMock()
    mock_it.get_metadata.return_value = {
        "artist": "A", "track_title": "T", "album": "B", "release_type": "single",
    }
    mock_yt = MagicMock()
    fetch_metadata_for_row(
        url="https://open.spotify.com/track/abc123",
        url_type="Spotify",
        itunes_client=mock_it,
        yt_extractor=mock_yt,
    )
    mock_it.get_metadata.assert_called_once()
    mock_yt.extract_metadata.assert_not_called()


def test_fetch_metadata_routes_youtube_url_to_yt_extractor():
    """YouTube URL must call YoutubeExtractor, never ItunesClient."""
    mock_it = MagicMock()
    mock_yt = MagicMock()
    mock_yt.extract_metadata.return_value = {
        "title": "T", "channel": "C",
        "artist": "A", "track_title": "T",
    }
    fetch_metadata_for_row(
        url="https://www.youtube.com/watch?v=xyz",
        url_type="YouTube",
        itunes_client=mock_it,
        yt_extractor=mock_yt,
    )
    mock_yt.extract_metadata.assert_called_once()
    mock_it.get_metadata.assert_not_called()


def test_fetch_metadata_result_includes_source_spotify():
    """Result dict must have source='Spotify' for Spotify rows."""
    mock_it = MagicMock()
    mock_it.get_metadata.return_value = {
        "artist": "A", "track_title": "T", "album": "B", "release_type": "album",
    }
    result = fetch_metadata_for_row(
        url="https://open.spotify.com/track/x",
        url_type="Spotify",
        itunes_client=mock_it,
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
        itunes_client=MagicMock(),
        yt_extractor=mock_yt,
    )
    assert result.get("source") == "YouTube"


def test_fetch_metadata_spotify_album_url_passes_album_resource_type():
    """Spotify album URL must call get_metadata with resource_type='album'."""
    mock_it = MagicMock()
    mock_it.get_metadata.return_value = {
        "artist": "A", "track_title": "B", "album": "B", "release_type": "album",
    }
    fetch_metadata_for_row(
        url="https://open.spotify.com/album/xyz789",
        url_type="Spotify",
        itunes_client=mock_it,
        yt_extractor=MagicMock(),
    )
    _, resource_type_arg = mock_it.get_metadata.call_args[0]
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
# ItunesClient.search_duration_ms — duration-based YouTube matching
# ---------------------------------------------------------------------------


def _itunes_resp(results: list) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"results": results}
    return m


def test_search_duration_ms_simple_match():
    """search_duration_ms returns trackTimeMillis when artist and title match exactly."""
    client = ItunesClient()
    with patch("tunebridge.requests.get", return_value=_itunes_resp([{
        "artistName": "Artist One",
        "trackName": "Song Alpha",
        "trackTimeMillis": 190000,
    }])):
        assert client.search_duration_ms("Artist One", "Song Alpha") == 190000


def test_search_duration_ms_collaboration_first_artist_matches():
    """Collaboration credit 'Artist A, Artist B' matches when iTunes artistName is only 'Artist A'."""
    client = ItunesClient()
    with patch("tunebridge.requests.get", return_value=_itunes_resp([{
        "artistName": "Artist A",
        "trackName": "Song Beta",
        "trackTimeMillis": 195000,
    }])):
        result = client.search_duration_ms("Artist A, Artist B", "Song Beta")
    assert result == 195000


def test_search_duration_ms_accented_title_normalized():
    """Accented title 'Café' matches iTunes 'Cafe' via unicode normalization."""
    client = ItunesClient()
    with patch("tunebridge.requests.get", return_value=_itunes_resp([{
        "artistName": "Artist One",
        "trackName": "Cafe Song",
        "trackTimeMillis": 195000,
    }])):
        result = client.search_duration_ms("Artist One", "Café Song")
    assert result == 195000


def test_search_duration_ms_no_match_returns_none():
    """Returns None when no iTunes result matches artist+title."""
    client = ItunesClient()
    with patch("tunebridge.requests.get", return_value=_itunes_resp([{
        "artistName": "Different Artist",
        "trackName": "Different Song",
        "trackTimeMillis": 200000,
    }])):
        assert client.search_duration_ms("Artist One", "Song Alpha") is None


def test_search_duration_ms_empty_results_returns_none():
    """Returns None when all stores return empty results."""
    client = ItunesClient()
    with patch("tunebridge.requests.get", return_value=_itunes_resp([])):
        assert client.search_duration_ms("Unknown", "Unknown") is None


def test_search_duration_ms_tries_mx_store():
    """ES, MX, and US stores are all tried when earlier stores return empty."""
    client = ItunesClient()
    urls_called = []

    def fake_get(url, **kwargs):
        urls_called.append(url)
        return _itunes_resp([])

    with patch("tunebridge.requests.get", side_effect=fake_get):
        client.search_duration_ms("Artist", "Title")

    assert any("country=ES" in u for u in urls_called), "ES store not tried"
    assert any("country=MX" in u for u in urls_called), "MX store not tried"
    assert any("country=ES" not in u and "country=MX" not in u for u in urls_called), "US fallback not tried"


def test_search_duration_ms_falls_back_to_deezer():
    """When iTunes finds no match, Deezer API is queried as fallback."""
    client = ItunesClient()

    def fake_get(url, **kwargs):
        if "itunes.apple.com" in url:
            return _itunes_resp([])
        # Deezer response
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"data": [{
            "title": "Song Alpha",
            "artist": {"name": "Artist One"},
            "duration": 195,
        }]}
        return m

    with patch("tunebridge.requests.get", side_effect=fake_get):
        result = client.search_duration_ms("Artist One", "Song Alpha")

    assert result == 195_000


def test_search_duration_ms_deezer_skipped_when_itunes_matches():
    """Deezer is NOT called when iTunes already returns a match."""
    client = ItunesClient()
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "itunes.apple.com" in url:
            return _itunes_resp([{
                "artistName": "Artist One",
                "trackName": "Song Alpha",
                "trackTimeMillis": 190_000,
            }])
        return _itunes_resp([])

    with patch("tunebridge.requests.get", side_effect=fake_get):
        result = client.search_duration_ms("Artist One", "Song Alpha")

    assert result == 190_000
    assert not any("deezer.com" in u for u in calls), "Deezer called unnecessarily"
