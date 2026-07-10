"""Tests for publishing tools with mocked YouTube API."""

from unittest.mock import MagicMock, patch

import pytest


class TestUploadVideo:
    @patch("youtube_mcp.tools.publishing.MediaFileUpload")
    @patch("youtube_mcp.tools.publishing.auth")
    @patch("youtube_mcp.tools.publishing.quota")
    @patch("os.path.exists", return_value=True)
    def test_upload_success(self, mock_exists, mock_quota, mock_auth, mock_media):
        from youtube_mcp.tools.publishing import youtube_upload_video

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt
        mock_yt.videos().insert().execute.return_value = {
            "id": "new123",
            "snippet": {"title": "My Video"},
            "status": {"privacyStatus": "private"},
        }

        result = youtube_upload_video(
            file_path="/tmp/video.mp4",
            title="My Video",
            description="A test",
        )
        assert result["id"] == "new123"
        assert result["url"] == "https://www.youtube.com/watch?v=new123"
        assert result["quota_cost"] == 1600
        mock_quota.consume.assert_called_once_with("video_insert")

    @patch("youtube_mcp.tools.publishing.quota")
    def test_upload_file_not_found(self, mock_quota):
        from youtube_mcp.tools.publishing import youtube_upload_video

        result = youtube_upload_video(
            file_path="/nonexistent/video.mp4",
            title="Test",
        )
        assert "error" in result
        mock_quota.consume.assert_not_called()


class TestUpdateVideo:
    @patch("youtube_mcp.tools.publishing.auth")
    @patch("youtube_mcp.tools.publishing.quota")
    def test_update_title(self, mock_quota, mock_auth):
        from youtube_mcp.tools.publishing import youtube_update_video

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt

        # Mock the initial fetch
        mock_yt.videos().list().execute.return_value = {
            "items": [{
                "id": "vid1",
                "snippet": {
                    "title": "Old Title",
                    "description": "Desc",
                    "tags": ["tag1"],
                    "categoryId": "22",
                },
                "status": {"privacyStatus": "public"},
            }]
        }

        # Mock the update
        mock_yt.videos().update().execute.return_value = {
            "id": "vid1",
            "snippet": {"title": "New Title"},
            "status": {"privacyStatus": "public"},
        }

        result = youtube_update_video(video_id="vid1", title="New Title")
        assert result["title"] == "New Title"
        assert result["updated"] is True

    @patch("youtube_mcp.tools.publishing.auth")
    @patch("youtube_mcp.tools.publishing.quota")
    def test_update_not_found(self, mock_quota, mock_auth):
        from youtube_mcp.tools.publishing import youtube_update_video

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt
        mock_yt.videos().list().execute.return_value = {"items": []}

        result = youtube_update_video(video_id="nope", title="X")
        assert "error" in result

    @patch("youtube_mcp.tools.publishing.auth")
    @patch("youtube_mcp.tools.publishing.quota")
    def test_update_without_privacy_status_does_not_raise_keyerror(
        self, mock_quota, mock_auth
    ):
        """Regression: a snippet-only update sends part='snippet', and the
        YouTube API response omits the 'status' block. Parsing the response
        must not raise KeyError even though the update itself succeeded.
        """
        from youtube_mcp.tools.publishing import youtube_update_video

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt
        mock_yt.videos().list().execute.return_value = {
            "items": [{
                "id": "vid1",
                "snippet": {"title": "Old", "description": "D", "tags": [], "categoryId": "22"},
                "status": {"privacyStatus": "public", "embeddable": True},
            }]
        }
        # Realistic part='snippet' response: no 'status' block.
        mock_yt.videos().update().execute.return_value = {
            "id": "vid1",
            "snippet": {"title": "New Title"},
        }

        result = youtube_update_video(video_id="vid1", title="New Title")
        assert result["id"] == "vid1"
        assert result["title"] == "New Title"
        assert result["updated"] is True
        assert result.get("privacy") is None

    @patch("youtube_mcp.tools.publishing.auth")
    @patch("youtube_mcp.tools.publishing.quota")
    def test_update_privacy_preserves_sibling_status_fields(
        self, mock_quota, mock_auth
    ):
        """A privacy_status change must read-modify-write the status block so
        sibling writable fields (embeddable, publicStatsViewable, license,
        selfDeclaredMadeForKids) are preserved instead of reset.
        """
        from youtube_mcp.tools.publishing import youtube_update_video

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt
        mock_yt.videos().list().execute.return_value = {
            "items": [{
                "id": "vid1",
                "snippet": {"title": "T", "description": "D", "tags": [], "categoryId": "22"},
                "status": {
                    "privacyStatus": "public",
                    "embeddable": True,
                    "publicStatsViewable": False,
                    "license": "creativeCommon",
                    "selfDeclaredMadeForKids": False,
                    "uploadStatus": "processed",  # read-only, must not be sent back
                },
            }]
        }
        mock_yt.videos().update().execute.return_value = {
            "id": "vid1",
            "snippet": {"title": "T"},
            "status": {"privacyStatus": "unlisted", "embeddable": True},
        }

        youtube_update_video(video_id="vid1", privacy_status="unlisted")

        sent = mock_yt.videos().update.call_args.kwargs
        status_sent = sent["body"]["status"]
        assert sent["part"] == "snippet,status"
        assert status_sent["privacyStatus"] == "unlisted"
        assert status_sent["embeddable"] is True
        assert status_sent["publicStatsViewable"] is False
        assert status_sent["license"] == "creativeCommon"
        assert status_sent["selfDeclaredMadeForKids"] is False
        # read-only fields must not be echoed back on the write
        assert "uploadStatus" not in status_sent

    @patch("youtube_mcp.tools.publishing.auth")
    @patch("youtube_mcp.tools.publishing.quota")
    def test_update_to_non_private_drops_publish_at(self, mock_quota, mock_auth):
        """publishAt is only valid while privacyStatus='private'. Flipping a
        scheduled-private video to unlisted/public must drop the stale
        publishAt so the API doesn't reject the request (the unlisted-flip
        pattern), while embeddable is still preserved.
        """
        from youtube_mcp.tools.publishing import youtube_update_video

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt
        mock_yt.videos().list().execute.return_value = {
            "items": [{
                "id": "vid1",
                "snippet": {"title": "T", "description": "D", "tags": [], "categoryId": "22"},
                "status": {
                    "privacyStatus": "private",
                    "publishAt": "2026-08-01T15:00:00Z",
                    "embeddable": True,
                },
            }]
        }
        mock_yt.videos().update().execute.return_value = {
            "id": "vid1",
            "snippet": {"title": "T"},
            "status": {"privacyStatus": "unlisted"},
        }

        youtube_update_video(video_id="vid1", privacy_status="unlisted")

        status_sent = mock_yt.videos().update.call_args.kwargs["body"]["status"]
        assert status_sent["privacyStatus"] == "unlisted"
        assert "publishAt" not in status_sent
        assert status_sent["embeddable"] is True


class TestSetThumbnail:
    @patch("youtube_mcp.tools.publishing.MediaFileUpload")
    @patch("youtube_mcp.tools.publishing.auth")
    @patch("youtube_mcp.tools.publishing.quota")
    @patch("os.path.exists", return_value=True)
    def test_set_thumbnail(self, mock_exists, mock_quota, mock_auth, mock_media):
        from youtube_mcp.tools.publishing import youtube_set_thumbnail

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt
        mock_yt.thumbnails().set().execute.return_value = {
            "items": [{"default": {"url": "https://i.ytimg.com/thumb.jpg"}}]
        }

        result = youtube_set_thumbnail("vid1", "/tmp/thumb.jpg")
        assert result["updated"] is True
        mock_quota.consume.assert_called_once_with("thumbnail_set")


class TestDeleteVideo:
    @patch("youtube_mcp.tools.publishing.auth")
    @patch("youtube_mcp.tools.publishing.quota")
    def test_delete(self, mock_quota, mock_auth):
        from youtube_mcp.tools.publishing import youtube_delete_video

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt

        result = youtube_delete_video("vid1")
        assert result["deleted"] is True
        mock_quota.consume.assert_called_once_with("delete")
