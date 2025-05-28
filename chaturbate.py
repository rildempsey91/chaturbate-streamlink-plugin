import re
import uuid
from typing import Optional
from urllib.parse import urlparse

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import validate
from streamlink.stream.hls import HLSStream
from streamlink.exceptions import PluginError
from streamlink.options import Options

API_HLS = "https://chaturbate.com/get_edge_hls_url_ajax/"

@pluginmatcher(re.compile(
    r"https?://(?:\w+\.)?chaturbate\.com/(?P<username>[a-zA-Z0-9_-]+)(?:/.*)?$",
    re.IGNORECASE
))
class Chaturbate(Plugin):
    _post_schema = validate.Schema(
        {
            "url": validate.any(str, None),
            "room_status": validate.any(str, None),
            "success": validate.any(int, bool)
        }
    )

    def __init__(self, session, url: str, options: Optional[Options] = None):
        super().__init__(session, url, options)
        self.author: Optional[str] = None
        self.title: Optional[str] = None

    def get_title(self) -> Optional[str]:
        return self.title or self.match.group("username")

    def get_author(self) -> Optional[str]:
        return self.author or self.match.group("username")

    def get_category(self) -> str:
        return "NSFW LIVE"

    def _get_streams(self):
        username = self.match.group("username")
        if not username:
            raise PluginError("Invalid username in URL")

        # Generate CSRF token
        csrf_token = str(uuid.uuid4().hex.upper()[:32])

        # Set up headers and cookies
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": urlparse(self.url).geturl(),
            "User-Agent": self.session.http.headers.get("User-Agent", "")
        }
        cookies = {"csrftoken": csrf_token}
        post_data = f"room_slug={username}&bandwidth=high"

        try:
            # Make API request
            res = self.session.http.post(API_HLS, headers=headers, cookies=cookies, data=post_data)
            res.raise_for_status()  # Check for HTTP errors
            data = self.session.http.json(res, schema=self._post_schema)

            if not data or not data.get("url"):
                self.logger.error("Invalid API response or no stream URL")
                return

            self.logger.info(f"Stream status: {data['room_status']}")
            self.author = username
            self.title = username  # Chaturbate API doesn't provide a title, so use username

            # Check stream status
            if not data["success"] or data["room_status"] != "public" or not data["url"]:
                self.logger.info(f"Stream offline or private (status: {data['room_status']})")
                return

            # Parse HLS streams
            try:
                streams = HLSStream.parse_variant_playlist(self.session, data["url"], headers={"Referer": self.url})
                if not streams:
                    self.logger.warning("No valid streams found in playlist")
                    stream = HLSStream(self.session, data["url"], headers={"Referer": self.url})
                    yield "default", stream
                else:
                    yield from streams.items()
            except Exception as err:
                self.logger.error(f"Failed to load stream: {err}")
                # Fallback to single stream
                try:
                    stream = HLSStream(self.session, data["url"], headers={"Referer": self.url})
                    yield "default", stream
                except Exception as err:
                    self.logger.error(f"Failed to load fallback stream: {err}")

        except PluginError:
            raise
        except Exception as err:
            self.logger.error(f"Unexpected error: {err}")
            return

__plugin__ = Chaturbate
