import asyncio
import re
from typing import Any

import httpx

from config import steam_country, steam_language
from http_utils import append_query, async_fetch_json, async_fetch_text


STEAM_API_BASE = "https://api.steampowered.com"
STEAM_COMMUNITY_BASE = "https://steamcommunity.com"
STEAM_STORE_BASE = "https://store.steampowered.com"
INVALID_STEAM_KEY_MESSAGE = "Steam API Key 无效或没有访问权限，请检查当前用户的 Steam API Key。"
STEAM_USER_NOT_FOUND_MESSAGE = "没有找到这个 Steam 用户，请检查 SteamID64。"

PLAYER_STATUS = {
    0: "离线",
    1: "在线",
    2: "忙碌",
    3: "离开",
    4: "打盹",
    5: "想交易",
    6: "想组队",
}
COMMUNITY_STATUS = {
    "offline": "离线",
    "online": "在线",
    "in-game": "游戏中",
    "away": "离开",
    "busy": "忙碌",
    "snooze": "打盹",
    "looking to trade": "想交易",
    "looking to play": "想组队",
}


def _player_status_label(state: int) -> str:
    return PLAYER_STATUS.get(state, "未知")


def _community_status_label(state: str) -> str:
    return COMMUNITY_STATUS.get((state or "").strip().lower(), state or "未知")


def _game_image(appid: int, image_hash: str, kind: str = "capsule") -> str:
    if not image_hash:
        return ""
    if kind == "icon":
        return f"https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{image_hash}.jpg"
    return f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_616x353.jpg"


def _extract_tag(xml: str, tag_name: str) -> str:
    match = re.search(rf"<{tag_name}>(.*?)</{tag_name}>", xml, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    value = match.group(1).strip()
    cdata_match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.DOTALL)
    return cdata_match.group(1).strip() if cdata_match else value


class SteamService:
    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings or {}
        steam = self.settings.get("steam", {})
        self.api_key = (steam.get("apiKey") or "").strip()
        self.steam_id = (steam.get("steamId") or "").strip()
        self.country = (steam.get("country") or steam_country).strip() or steam_country
        self.language = (steam.get("language") or steam_language).strip() or steam_language
        self.proxy = (steam.get("proxy") or "").strip() or None

    @property
    def has_steam_id(self) -> bool:
        return bool(self.steam_id)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def _friendly_api_error(self, error: Exception) -> str:
        if self.proxy and isinstance(error, httpx.ProxyError):
            return f"无法连接 Steam 代理 {self.proxy}，请检查代理地址、端口和协议。"
        if self.proxy and isinstance(error, httpx.ConnectError):
            return f"Steam 请求已走代理 {self.proxy}，但代理连接失败或上游连接被关闭。请检查代理规则是否允许 api.steampowered.com 和 steamcommunity.com。"
        if isinstance(error, httpx.TimeoutException):
            return "Steam API 请求超时，请检查网络、代理或稍后重试。"
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            body = error.response.text[:300].lower()
            if status == 403 or "forbidden" in body or "verify your" in body:
                return INVALID_STEAM_KEY_MESSAGE
            if status == 404:
                return STEAM_USER_NOT_FOUND_MESSAGE
            return f"Steam API 返回 HTTP {status}，请检查当前网络、代理和 Steam 配置。"

        message = str(error)
        lowered = message.lower()
        if "forbidden" in lowered or "verify your" in lowered or "key=" in lowered:
            return INVALID_STEAM_KEY_MESSAGE
        if "not found" in lowered:
            return STEAM_USER_NOT_FOUND_MESSAGE
        safe_message = re.sub(r"key=[^&\s]+", "key=***", message)
        return safe_message or "Steam API 请求失败，请检查网络、代理和 Steam 配置。"

    async def _async_fetch_public_profile(self) -> dict[str, Any]:
        if not self.has_steam_id:
            raise RuntimeError("请先配置 SteamID64。")

        xml = await async_fetch_text(
            f"{STEAM_COMMUNITY_BASE}/profiles/{self.steam_id}?xml=1", proxy=self.proxy
        )
        steam_id = _extract_tag(xml, "steamID64") or self.steam_id
        persona_name = _extract_tag(xml, "steamID") or steam_id
        avatar_url = _extract_tag(xml, "avatarFull")
        profile_url = _extract_tag(xml, "profileURL") or f"{STEAM_COMMUNITY_BASE}/profiles/{steam_id}"
        online_state = _extract_tag(xml, "onlineState")
        state_message = _extract_tag(xml, "stateMessage")
        current_game = _extract_tag(xml, "inGameInfo")

        return {
            "steamId": steam_id,
            "personaName": persona_name,
            "avatarUrl": avatar_url,
            "profileUrl": profile_url,
            "status": _community_status_label(state_message or online_state),
            "currentGame": current_game,
        }

    async def _async_fetch_private_overview(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Fetch profile summary, owned games, and recent games in parallel."""
        summary_task = async_fetch_json(
            append_query(
                f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v0002/",
                key=self.api_key,
                steamids=self.steam_id,
            ),
            proxy=self.proxy,
        )
        owned_task = async_fetch_json(
            append_query(
                f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v0001/",
                key=self.api_key,
                steamid=self.steam_id,
                include_appinfo="1",
                include_played_free_games="1",
            ),
            proxy=self.proxy,
        )
        recent_task = async_fetch_json(
            append_query(
                f"{STEAM_API_BASE}/IPlayerService/GetRecentlyPlayedGames/v0001/",
                key=self.api_key,
                steamid=self.steam_id,
            ),
            proxy=self.proxy,
        )
        return await asyncio.gather(summary_task, owned_task, recent_task)

    def _recent_game_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        appid = item.get("appid", 0)
        return {
            "appid": appid,
            "name": item.get("name", ""),
            "playtime2WeeksHours": round(item.get("playtime_2weeks", 0) / 60, 1),
            "playtimeForeverHours": round(item.get("playtime_forever", 0) / 60, 1),
            "iconUrl": _game_image(appid, item.get("img_icon_url", ""), "icon"),
            "headerImage": _game_image(appid, item.get("img_logo_url", "")),
        }

    def _player_profile(self, player: dict[str, Any]) -> dict[str, Any]:
        return {
            "steamId": player.get("steamid", ""),
            "personaName": player.get("personaname", ""),
            "avatarUrl": player.get("avatarfull", ""),
            "profileUrl": player.get("profileurl", ""),
            "status": _player_status_label(int(player.get("personastate", 0))),
            "currentGame": player.get("gameextrainfo", ""),
        }

    def _overview_stats(
        self, owned_games: dict[str, Any], recent_games: dict[str, Any]
    ) -> dict[str, Any]:
        recent_items = recent_games.get("games", [])
        return {
            "ownedGamesCount": owned_games.get("game_count", 0),
            "recentGamesCount": recent_games.get("total_count", 0),
            "recentPlaytimeHours": round(
                sum(item.get("playtime_2weeks", 0) for item in recent_items) / 60,
                1,
            ),
        }

    def _deal_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        appid = item.get("id")
        return {
            "appid": appid,
            "name": item.get("name", ""),
            "discountPercent": item.get("discount_percent", 0),
            "finalPrice": round(item.get("final_price", 0) / 100, 2),
            "originalPrice": round(item.get("original_price", 0) / 100, 2),
            "currency": item.get("currency", self.country),
            "headerImage": item.get("header_image", ""),
            "storeUrl": f"{STEAM_STORE_BASE}/app/{appid}/",
        }

    def _overview_payload(
        self,
        *,
        configured: bool,
        message: str,
        profile: dict[str, Any] | None,
        stats: dict[str, Any] | None = None,
        recent_games: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "configured": configured,
            "message": message,
            "profile": profile,
            "stats": stats,
            "recentGames": recent_games or [],
        }

    def _private_overview_payload(
        self,
        summary: dict[str, Any],
        owned_games_raw: dict[str, Any],
        recent_games_raw: dict[str, Any],
    ) -> dict[str, Any]:
        player = (summary.get("response", {}).get("players") or [None])[0]
        if not player:
            raise RuntimeError(STEAM_USER_NOT_FOUND_MESSAGE)

        owned_games = owned_games_raw.get("response", {})
        recent_games = recent_games_raw.get("response", {})
        recent_items = [
            self._recent_game_payload(item)
            for item in (recent_games.get("games") or [])[:4]
        ]

        return self._overview_payload(
            configured=True,
            message="",
            profile=self._player_profile(player),
            stats=self._overview_stats(owned_games, recent_games),
            recent_games=recent_items,
        )

    async def async_get_overview(self) -> dict[str, Any]:
        if not self.has_steam_id:
            return self._overview_payload(
                configured=False,
                message="请先配置当前用户的 SteamID64，才能查询玩家状态。",
                profile=None,
            )

        public_profile = None
        public_error = ""
        try:
            public_profile = await self._async_fetch_public_profile()
        except Exception as exc:
            public_error = f"无法读取公开资料: {self._friendly_api_error(exc)}"

        if not self.has_api_key:
            return self._overview_payload(
                configured=public_profile is not None,
                message=(
                    "当前仅显示公开资料。配置 Steam API Key 后可继续获取拥有游戏数和最近游戏。"
                    if public_profile
                    else public_error or "请配置 Steam API Key 和 SteamID64。"
                ),
                profile=public_profile,
            )

        try:
            summary, owned_games_raw, recent_games_raw = await self._async_fetch_private_overview()
            return self._private_overview_payload(summary, owned_games_raw, recent_games_raw)
        except Exception as exc:
            api_error = self._friendly_api_error(exc)
            return self._overview_payload(
                configured=public_profile is not None,
                message=(
                    f"{api_error} 已切换为公开资料模式。"
                    if public_profile
                    else api_error
                ),
                profile=public_profile,
            )

    async def async_get_deals(self) -> dict[str, Any]:
        try:
            url = append_query(
                f"{STEAM_STORE_BASE}/api/featuredcategories/",
                cc=self.country,
                l=self.language,
            )
            payload = await async_fetch_json(url, proxy=self.proxy)
            specials = payload.get("specials", {}).get("items", [])
            items = [self._deal_payload(item) for item in specials[:6]]
            return {
                "configured": True,
                "message": "",
                "items": items,
            }
        except Exception as exc:
            return {
                "configured": False,
                "message": f"无法获取商店卡片: {exc}",
                "items": [],
            }
