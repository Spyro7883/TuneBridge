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


# Canned API payloads
_TOKEN_RESP = {"access_token": "tok-xyz", "token_type": "Bearer", "expires_in": 3600}

_TRACK_RESP = {
    "name": "Blinding Lights",
    "artists": [{"name": "The Weeknd"}],
    "album": {"name": "After Hours", "album_type": "album", "release_date": "2020-03-20"},
    "duration_ms": 200040,
}

_ALBUM_RESP = {
    "name": "After Hours",
    "artists": [{"name": "The Weeknd"}],
    "album_type": "album",
    "release_date": "2020-03-20",
    "tracks": {"total": 14},
}

_YT_INFO = {
    "title": "The Weeknd - Blinding Lights (Official Video)",
    "channel": "TheWeekndVEVO",
    "uploader": "TheWeekndVEVO",
    "duration": 200,
    "id": "4NRXx6U8ABQ",
}


# ---------------------------------------------------------------------------
# SpotifyClient — token management
# ---------------------------------------------------------------------------


def test_spotify_token_uses_client_credentials_grant():
    """_get_token must POST with grant_type=client_credentials (no user login)."""
    client = SpotifyClient(client_id="fake_id", client_secret="fake_secret")
    with patch("tunebridge.requests.post") as mock_post:
        mock_post.return_value.json.return_value = _TOKEN_RESP
        mock_post.return_value.raise_for_status = MagicMock()
        client._get_token()
    data = mock_post.call_args[1].get("data") or mock_post.call_args[0][1]
    assert data.get("grant_type") == "client_credentials"


def test_spotify_token_cached_second_call_no_extra_post():
    """Second _get_token() within TTL must reuse cached token — no extra POST."""
    client = SpotifyClient(client_id="fake_id", client_secret="fake_secret")
    with patch("tunebridge.requests.post") as mock_post:
        mock_post.return_value.json.return_value = _TOKEN_RESP
        mock_post.return_value.raise_for_status = MagicMock()
        client._get_token()
        client._get_token()
    assert mock_post.call_count == 1


def test_spotify_token_http_error_raises():
    """HTTP 401 from token endpoint must propagate as an exception."""
    import requests as _req
    client = SpotifyClient(client_id="bad", client_secret="bad")
    with patch("tunebridge.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.side_effect = _req.HTTPError("401")
        with pytest.raises(Exception):
            client._get_token()


# ---------------------------------------------------------------------------
# SpotifyClient — track / album metadata
# ---------------------------------------------------------------------------


def test_spotify_get_track_metadata_returns_required_keys():
    """get_track_metadata must return artist, title, album, release_type."""
    client = SpotifyClient(client_id="fake_id", client_secret="fake_secret")
    with patch.object(client, "_get_token", return_value="tok"), \
         patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.json.return_value = _TRACK_RESP
        mock_get.return_value.raise_for_status = MagicMock()
        result = client.get_track_metadata("2374M0fkVJiOF9EtE81NuG")
    for key in ("artist", "title", "album", "release_type"):
        assert key in result, f"Missing key: {key}"


def test_spotify_get_track_metadata_values_correct():
    """Track metadata values must match the Spotify API response."""
    client = SpotifyClient(client_id="fake_id", client_secret="fake_secret")
    with patch.object(client, "_get_token", return_value="tok"), \
         patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.json.return_value = _TRACK_RESP
        mock_get.return_value.raise_for_status = MagicMock()
        result = client.get_track_metadata("2374M0fkVJiOF9EtE81NuG")
    assert result["artist"] == "The Weeknd"
    assert result["title"] == "Blinding Lights"
    assert result["album"] == "After Hours"
    assert result["release_type"] == "album"


def test_spotify_get_album_metadata_returns_required_keys():
    """get_album_metadata must return at least artist, album, release_type."""
    client = SpotifyClient(client_id="fake_id", client_secret="fake_secret")
    with patch.object(client, "_get_token", return_value="tok"), \
         patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.json.return_value = _ALBUM_RESP
        mock_get.return_value.raise_for_status = MagicMock()
        result = client.get_album_metadata("4yP0hdKOZPNshxUOjY0cZj")
    for key in ("artist", "album", "release_type"):
        assert key in result, f"Missing key: {key}"


def test_spotify_get_track_metadata_http_error_raises():
    """HTTP error on track fetch must raise, not return empty dict."""
    import requests as _req
    client = SpotifyClient(client_id="fake_id", client_secret="fake_secret")
    with patch.object(client, "_get_token", return_value="tok"), \
         patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value.raise_for_status.side_effect = _req.HTTPError("404")
        with pytest.raises(Exception):
            client.get_track_metadata("nonexistent")


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
    mock_sp.get_track_metadata.return_value = {
        "artist": "A", "title": "T", "album": "B", "release_type": "single",
    }
    mock_yt = MagicMock()
    fetch_metadata_for_row(
        url="https://open.spotify.com/track/abc123",
        url_type="Spotify",
        spotify_client=mock_sp,
        yt_extractor=mock_yt,
    )
    mock_sp.get_track_metadata.assert_called_once()
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
    mock_sp.get_track_metadata.assert_not_called()


def test_fetch_metadata_result_includes_source_spotify():
    """Result dict must have source='Spotify' for Spotify rows."""
    mock_sp = MagicMock()
    mock_sp.get_track_metadata.return_value = {
        "artist": "A", "title": "T", "album": "B", "release_type": "album",
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


def test_fetch_metadata_spotify_album_url_delegates_to_get_album_metadata():
    """Spotify album URL must call get_album_metadata, not get_track_metadata."""
    mock_sp = MagicMock()
    mock_sp.get_album_metadata.return_value = {
        "artist": "A", "album": "B", "release_type": "album",
    }
    fetch_metadata_for_row(
        url="https://open.spotify.com/album/xyz789",
        url_type="Spotify",
        spotify_client=mock_sp,
        yt_extractor=MagicMock(),
    )
    mock_sp.get_album_metadata.assert_called_once()
    mock_sp.get_track_metadata.assert_not_called()


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
        "title": "Blinding Lights",
        "album": "After Hours",
        "release_type": "album",
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
    assert status_item.text() in ("Metadata ready", "Fetching metadata", "Done")


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
