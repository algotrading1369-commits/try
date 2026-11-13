import random
import re
import time

import requests
from bs4 import BeautifulSoup

from . import constants as c

LOBBY = "https://lobby.ogame.gameforge.com"
GF_AUTH = "https://gameforge.com/api/v1/auth/thin/sessions"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class OGameError(Exception):
    pass


class LoginError(OGameError):
    pass


class CaptchaRequired(LoginError):
    pass


def _to_int(text):
    if text is None:
        return 0
    text = str(text).strip().replace(".", "").replace(",", "").replace("M", "000000").replace("B", "000000000")
    digits = re.sub(r"[^0-9\-]", "", text)
    return int(digits) if digits else 0


class OGameClient:
    def __init__(self, universe, language, username, password, user_agent=USER_AGENT):
        self.universe = universe
        self.language = language
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.token = None
        self.server_number = None
        self.server_id = None
        self.index_php = None
        self.player = None
        self.player_id = None
        self.server_version = None
        self.universe_speed = 1
        self.fleet_speed = 1
        self.last_request = 0.0

    def _throttle(self, min_gap=0.8):
        gap = time.time() - self.last_request
        if gap < min_gap:
            time.sleep(min_gap - gap + random.uniform(0.05, 0.4))
        self.last_request = time.time()

    def _get(self, url, **kwargs):
        self._throttle()
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, url, **kwargs):
        self._throttle()
        resp = self.session.post(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def login(self):
        self.session.get(LOBBY + "/")
        payload = {
            "identity": self.username,
            "password": self.password,
            "locale": f"{self.language}_{self.language.upper()}",
            "gfLang": self.language,
            "platformGameId": "1dfd8e7e-6e1a-4eb1-8c64-03c3b62efd2f",
            "gameEnvironmentId": "0a31d605-ffaf-43e7-aa02-d06df7116fc8",
            "autoGameAccountCreation": False,
        }
        resp = self.session.post(GF_AUTH, json=payload, timeout=30)
        if resp.status_code == 409:
            raise CaptchaRequired("Gameforge pide captcha; inicia sesión manualmente y usa cookies o reintenta más tarde")
        if resp.status_code in (400, 401, 403):
            raise LoginError(
                "Gameforge rechazó las credenciales: usa el EMAIL de tu cuenta Gameforge "
                "(no el nick del juego) y su contraseña; si tienes verificación en dos pasos no funcionará"
            )
        if resp.status_code != 201:
            raise LoginError(f"Login fallido ({resp.status_code}): Gameforge no aceptó la sesión")
        self.token = resp.json()["token"]
        self.session.headers.update({"authorization": f"Bearer {self.token}"})
        self._resolve_server()
        self._enter_game()

    def _resolve_server(self):
        servers = self.session.get(LOBBY + "/api/servers", timeout=30).json()
        target = None
        for server in servers:
            if str(server.get("name", "")).lower() == self.universe.lower() and server.get("language") == self.language:
                target = server
                break
        if target is None:
            for server in servers:
                if str(server.get("name", "")).lower() == self.universe.lower():
                    target = server
                    self.language = server.get("language", self.language)
                    break
        if target is None:
            raise LoginError(f"Universo '{self.universe}' no encontrado en {self.language}")
        self.server_number = target["number"]

        accounts = self.session.get(LOBBY + "/api/users/me/accounts", timeout=30).json()
        for account in accounts:
            srv = account.get("server", {})
            if srv.get("number") == self.server_number and srv.get("language") == self.language:
                self.server_id = account["id"]
                break
        if self.server_id is None:
            raise LoginError(f"La cuenta no tiene personaje en {self.universe} ({self.language})")

    def _enter_game(self):
        link = self.session.get(
            LOBBY + "/api/users/me/loginLink",
            params={
                "id": self.server_id,
                "server[language]": self.language,
                "server[number]": self.server_number,
                "clickedButton": "account_list",
            },
            timeout=30,
        ).json()
        self.index_php = f"https://s{self.server_number}-{self.language}.ogame.gameforge.com/game/index.php?"
        self._get(link["url"])
        page = self._get(self.index_php + "page=ingame").text
        soup = BeautifulSoup(page, "html.parser")
        self.player = soup.find("meta", {"name": "ogame-player-name"})["content"]
        self.player_id = int(soup.find("meta", {"name": "ogame-player-id"})["content"])
        version = soup.find("meta", {"name": "ogame-version"})
        self.server_version = version["content"] if version else None
        speed = soup.find("meta", {"name": "ogame-universe-speed"})
        fspeed = soup.find("meta", {"name": "ogame-universe-speed-fleet-peaceful"})
        self.universe_speed = int(speed["content"]) if speed else 1
        self.fleet_speed = int(fspeed["content"]) if fspeed else 1

    def is_logged_in(self):
        try:
            page = self._get(self.index_php + "page=ingame").text
            return 'name="ogame-player-id"' in page
        except Exception:
            return False

    def relogin(self):
        try:
            self.logout()
        except Exception:
            pass
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.token = None
        self.login()

    def logout(self):
        try:
            self._get(self.index_php + "page=logout")
        except Exception:
            pass
        self.session.headers.pop("authorization", None)

    def _page(self, params):
        return BeautifulSoup(self._get(self.index_php + params).text, "html.parser")

    def empire(self):
        soup = self._page("page=ingame")
        planets = []
        for div in soup.select("div.smallplanet"):
            link = div.select_one("a.planetlink")
            if link is None:
                continue
            coord = div.select_one(".planet-koords").text.strip("[] ")
            g, s, p = (int(x) for x in coord.split(":"))
            planet = {
                "id": int(re.search(r"cp=(\d+)", link["href"]).group(1)),
                "name": div.select_one(".planet-name").text.strip(),
                "coords": [g, s, p],
                "type": "planet",
            }
            planets.append(planet)
            moon = div.select_one("a.moonlink")
            if moon is not None:
                planets.append(
                    {
                        "id": int(re.search(r"cp=(\d+)", moon["href"]).group(1)),
                        "name": planet["name"] + " (Luna)",
                        "coords": [g, s, p],
                        "type": "moon",
                    }
                )
        return planets

    def resources(self, celestial_id):
        soup = self._page(f"page=resourceSettings&cp={celestial_id}")
        res = {}
        for key in ("metal", "crystal", "deuterium", "darkmatter", "energy"):
            node = soup.find(id=f"resources_{key}")
            res[key] = _to_int(node["data-raw"]) if node is not None else 0
        boxes = soup.select("#storagebar .bar-box")
        storage = []
        for box in boxes[:3]:
            fill = box.select_one(".fillbar .bar")
            storage.append(_to_int(fill["title"]) if fill is not None and fill.has_attr("title") else 0)
        res["storage"] = storage
        return res

    def _parse_tech_list(self, soup, tech_map):
        result = {}
        items = soup.select("li.technology")
        for item in items:
            data = item.get("data-technology")
            if data is None:
                continue
            tech_id = int(data)
            if tech_id not in tech_map:
                continue
            level_node = item.select_one("span.level")
            amount_node = item.select_one("span.amount")
            result[tech_id] = {
                "id": tech_id,
                "name": tech_map[tech_id]["name"],
                "level": _to_int(level_node.get("data-value")) if level_node is not None else 0,
                "amount": _to_int(amount_node.get("data-value")) if amount_node is not None else 0,
                "status": item.get("data-status", "off"),
            }
        return result

    def _queue_from_soup(self, soup):
        queue = []
        for item in soup.select(".construction .queue li, #construction li"):
            cls = " ".join(item.get("class", []))
            if "first" not in cls and "item" not in cls:
                continue
            timer = item.select_one(".timer")
            queue.append(
                {
                    "tech": item.get("data-technology"),
                    "time_left": timer.text.strip() if timer is not None else None,
                }
            )
        return queue

    def buildings(self, celestial_id):
        result = {}
        for component, tech_map in (
            (c.COMPONENT_SUPPLIES, c.BUILDINGS),
            (c.COMPONENT_FACILITIES, c.BUILDINGS),
        ):
            soup = self._page(f"page=ingame&component={component}&cp={celestial_id}")
            for tech_id, info in self._parse_tech_list(soup, tech_map).items():
                if tech_id in result:
                    continue
                result[tech_id] = info
            if component == c.COMPONENT_SUPPLIES:
                result["_queue"] = self._queue_from_soup(soup)
        return result

    def research(self, celestial_id):
        soup = self._page(f"page=ingame&component=research&cp={celestial_id}")
        data = self._parse_tech_list(soup, c.RESEARCHES)
        data["_queue"] = self._queue_from_soup(soup)
        return data

    def ships(self, celestial_id):
        soup = self._page(f"page=ingame&component=shipyard&cp={celestial_id}")
        data = self._parse_tech_list(soup, c.SHIPS)
        data["_queue"] = self._queue_from_soup(soup)
        return data

    def defenses(self, celestial_id):
        soup = self._page(f"page=ingame&component=defenses&cp={celestial_id}")
        data = self._parse_tech_list(soup, c.DEFENSES)
        data["_queue"] = self._queue_from_soup(soup)
        return data

    def build(self, tech_id, celestial_id, amount=1):
        if tech_id in c.BUILDINGS:
            component = c.BUILDINGS[tech_id]["component"]
        elif tech_id in c.RESEARCHES:
            component = c.COMPONENT_RESEARCH
        else:
            raise OGameError(f"Tecnología {tech_id} no construible")
        raw = self._get(self.index_php + f"page=ingame&component={component}&cp={celestial_id}").text
        match = re.search(r"var urlQueueAdd = .*?token=([^'\"&;]+)", raw)
        if match is None:
            raise OGameError("No se encontró token de cola de construcción")
        token = match.group(1)
        self._get(
            self.index_php,
            params={
                "page": "ingame",
                "component": component,
                "modus": 1,
                "token": token,
                "type": tech_id,
                "menge": amount,
            },
        )
        return True

    def start_research(self, tech_id, celestial_id):
        return self.build(tech_id, celestial_id)

    def event_box(self):
        resp = self._get(
            self.index_php
            + "page=componentOnly&component=eventList&action=fetchEventBox&ajax=1&asJson=1",
            headers={"X-Requested-With": "XMLHttpRequest"},
        ).json()
        return {
            "hostile": int(resp.get("hostile", 0)),
            "neutral": int(resp.get("neutral", 0)),
            "friendly": int(resp.get("friendly", 0)),
        }

    def fleets(self):
        soup = self._page("page=ingame&component=movement")
        fleets = []
        for detail in soup.select(".fleetDetails"):
            fleets.append(
                {
                    "id": int(re.search(r"fleet(\d+)", detail.get("id", "fleet0")).group(1)),
                    "mission": int(detail.get("data-mission-type", 0)),
                    "return_flight": detail.get("data-return-flight") == "true",
                    "arrival": int(detail.get("data-arrival-time", 0)),
                    "origin": self._coords_of(detail, "originCoords"),
                    "destination": self._coords_of(detail, "destinationCoords"),
                }
            )
        return fleets

    @staticmethod
    def _coords_of(detail, cls):
        node = detail.select_one(f".{cls}")
        if node is None:
            return None
        match = re.search(r"\[(\d+):(\d+):(\d+)", node.text)
        return [int(match.group(i)) for i in (1, 2, 3)] if match else None

    def fleet_slots(self):
        soup = self._page("page=ingame&component=fleetdispatch")
        text = soup.select_one("#slots")
        if text is None:
            return {"fleet": {"used": 0, "total": 0}, "expedition": {"used": 0, "total": 0}}
        text = text.get_text(" ", strip=True)
        fm = re.search(r":\s*(\d+)\s*/\s*(\d+)", text)
        em = re.search(r"(\d+)\s*/\s*(\d+)", text.split(":")[-1] if ":" in text else text)
        used, total = (int(fm.group(1)), int(fm.group(2))) if fm else (0, 0)
        eu, et = (int(em.group(1)), int(em.group(2))) if em else (0, 0)
        return {
            "fleet": {"used": used, "total": total},
            "expedition": {"used": eu, "total": et},
        }

    def galaxy(self, galaxy, system):
        resp = self._post(
            self.index_php + "page=ingame&component=galaxyContent&ajax=1",
            data={"galaxy": galaxy, "system": system},
            headers={"X-Requested-With": "XMLHttpRequest"},
        ).json()
        soup = BeautifulSoup(resp.get("galaxy", ""), "html.parser")
        player_ranks = {}
        for node in soup.select("[id^=player]"):
            try:
                pid = int(re.search(r"\d+", node.get("id", "")).group())
                rank_node = node.select_one("a")
                if rank_node is not None and rank_node.text.strip().isdigit():
                    player_ranks[pid] = int(rank_node.text.strip())
            except (AttributeError, ValueError):
                continue
        rows = []
        for row in soup.select("#galaxytable .row"):
            classes = [c_ for c_ in row.get("class", []) if c_ != "row"]
            if "empty_filter" in classes:
                position = row.select_one(".position")
                rows.append(
                    {
                        "position": int(position.text) if position else 0,
                        "empty": True,
                    }
                )
                continue
            position = row.select_one(".position")
            name_node = row.select_one("[id^=planet] h1 span")
            player_node = row.find(rel=re.compile(r"player\d+"))
            moon = row.find(rel=re.compile(r"moon\d*")) is not None
            debris = row.find(rel=re.compile(r"debris\d*")) is not None
            statuses = re.findall(r"(\w+)_filter", " ".join(classes))
            activity = None
            act_node = row.select_one(".activity")
            if act_node is not None:
                if "minute" in (act_node.get("class") or []):
                    minutes = re.search(r"\d+", act_node.get("title", ""))
                    activity = int(minutes.group()) if minutes else 0
                else:
                    activity = "active"
            rows.append(
                {
                    "position": int(position.text) if position else 0,
                    "empty": False,
                    "name": name_node.text.strip() if name_node else "",
                    "player": player_node["title"] if player_node and player_node.has_attr("title") else None,
                    "player_id": int(re.search(r"\d+", player_node["rel"][0]).group()) if player_node else None,
                    "rank": player_ranks.get(int(re.search(r"\d+", player_node["rel"][0]).group())) if player_node else None,
                    "moon": moon,
                    "debris": debris,
                    "status": [s for s in statuses if s not in ("planet", "moon", "debris")],
                    "activity": activity,
                }
            )
        return rows

    def send_fleet(self, origin_id, mission, destination, ships, resources=(0, 0, 0), speed=10, holding_time=0):
        page = self._get(self.index_php + f"page=ingame&component=fleetdispatch&cp={origin_id}").text
        token_match = re.search(r'var fleetSendingToken = "([^"]+)"', page) or re.search(r'var token = "([^"]+)"', page)
        if token_match is None:
            raise OGameError("No se encontró token de envío de flota")
        form = {
            "token": token_match.group(1),
            "galaxy": destination[0],
            "system": destination[1],
            "position": destination[2],
            "type": destination[3] if len(destination) > 3 else c.DEST_PLANET,
            "metal": resources[0],
            "crystal": resources[1],
            "deuterium": resources[2],
            "prioMetal": 1,
            "prioCrystal": 2,
            "prioDeuterium": 3,
            "mission": mission,
            "speed": speed,
            "retreatAfterDefenderRetreat": 0,
            "union": 0,
            "holdingtime": holding_time,
        }
        for ship_id, amount in ships.items():
            if amount > 0:
                form[f"am{ship_id}"] = amount
        resp = self._post(
            self.index_php + "page=ingame&component=fleetdispatch&action=sendFleet&ajax=1&asJson=1",
            data=form,
            headers={"X-Requested-With": "XMLHttpRequest"},
        ).json()
        if not resp.get("success", False):
            raise OGameError(f"Envío de flota rechazado: {resp}")
        return resp

    def return_fleet(self, fleet_id):
        page = self._get(self.index_php + "page=ingame&component=movement").text
        match = re.search(rf'return={fleet_id}&amp;token=([^"&]+)', page)
        if match is None:
            return False
        self._get(
            self.index_php + f"page=ingame&component=movement&return={fleet_id}&token={match.group(1)}"
        )
        return True

    def spy_reports(self, max_pages=3):
        reports = []
        for page_num in range(1, max_pages + 1):
            soup = self._page(f"page=messages&tabid=1&subTab=0&page={page_num}")
            for note in soup.select(".msg.espionage, li.msg"):
                body = note.decode_contents()
                coords = re.search(r"\[(\d+):(\d+):(\d+)\]", body)
                if coords is None:
                    continue
                metal = re.search(r"Metal[^0-9]{0,40}([\d.,]+)", body)
                crystal = re.search(r"Cristal[^0-9]{0,40}([\d.,]+)", body)
                deuterium = re.search(r"Deuterio[^0-9]{0,40}([\d.,]+)", body)
                reports.append(
                    {
                        "coords": [int(coords.group(i)) for i in (1, 2, 3)],
                        "metal": _to_int(metal.group(1)) if metal else 0,
                        "crystal": _to_int(crystal.group(1)) if crystal else 0,
                        "deuterium": _to_int(deuterium.group(1)) if deuterium else 0,
                    }
                )
            if len(soup.select(".msg.espionage, li.msg")) == 0:
                break
        return reports

    def server_info(self):
        resp = self._get(f"https://s{self.server_number}-{self.language}.ogame.gameforge.com/api/serverData.xml")
        match = re.search(r"<name>([^<]*)</name>", resp.text)
        speed = re.search(r"<speed>(\d+)</speed>", resp.text)
        return {
            "name": match.group(1) if match else self.universe,
            "speed": int(speed.group(1)) if speed else self.universe_speed,
            "version": self.server_version,
        }
