import difflib
import random
import re
import time

import requests
from bs4 import BeautifulSoup

from . import constants as c
from .blackbox import generate_blackbox, random_user_agent

LOBBY = "https://lobby.ogame.gameforge.com"
GF_AUTH = "https://spark-web.gameforge.com/api/v2/authProviders/mauth/sessions"

PLATFORM_GAME_ID = "1dfd8e7e-6e1a-4eb1-8c64-03c3b62efd2f"
GAME_ENVIRONMENT_ID = "0a31d605-ffaf-43e7-aa02-d06df7116fc8"

LOCALES = {
    "es": "es-ES", "en": "en-GB", "de": "de-DE", "fr": "fr-FR", "pl": "pl-PL",
    "it": "it-IT", "ru": "ru-RU", "tr": "tr-TR", "pt": "pt-PT", "nl": "nl-NL",
    "hu": "hu-HU", "cs": "cs-CZ", "ro": "ro-RO", "sk": "sk-SK", "bg": "bg-BG",
    "el": "el-GR", "da": "da-DK", "fi": "fi-FI", "sv": "sv-SE", "no": "nb-NO",
    "ar": "ar-AE", "hr": "hr-HR", "sl": "sl-SI", "sr": "sr-RS", "uk": "uk-UA",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
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
    def __init__(self, universe, language, username, password, user_agent=None, session_token=None, game_cookies=None):
        self.universe = universe
        self.language = language
        self.username = username
        self.password = password
        self.session_token = session_token
        self.game_cookies = game_cookies
        self.user_agent = user_agent or random_user_agent()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
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

    def _throttle(self, min_gap=1.3):
        gap = time.time() - self.last_request
        if gap < min_gap:
            time.sleep(min_gap - gap + random.uniform(0.05, 0.6))
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
        if self.game_cookies:
            try:
                self._enter_game_direct()
                return
            except LoginError:
                if not self.session_token:
                    raise
        self.session.get(LOBBY + "/")
        if self.session_token:
            token = self.session_token.strip().strip('"').strip("'")
            if token.lower().startswith("gf-token-production="):
                token = token.split("=", 1)[1].strip().strip('"').strip("'")
            self.token = token
            self.session.headers.update({"authorization": f"Bearer {self.token}"})
            check = self.session.get(LOBBY + "/api/users/me", timeout=30, headers={"Referer": LOBBY + "/", "Accept": "application/json"})
            if check.status_code in (401, 403):
                raise LoginError("La cookie de sesión ya no es válida (caducó o entraste de nuevo en el lobby y se rotó): copia una nueva y guárdala")
            if check.status_code != 200:
                raise LoginError(f"La cookie de sesión no es válida ({check.status_code})")
            self._resolve_server()
            self._enter_game()
            return
        payload = {
            "identity": self.username,
            "password": self.password,
            "locale": LOCALES.get(self.language, f"{self.language}-{self.language.upper()}"),
            "gfLang": self.language,
            "gameId": PLATFORM_GAME_ID,
            "gameEnvironmentId": GAME_ENVIRONMENT_ID,
            "blackbox": generate_blackbox(self.session, self.user_agent),
        }
        resp = self.session.post(
            GF_AUTH,
            json=payload,
            timeout=30,
            headers={
                "Origin": "https://lobby.ogame.gameforge.com",
                "Referer": "https://lobby.ogame.gameforge.com/",
                "TNT-Installation-Id": "",
            },
        )
        if resp.status_code == 201:
            try:
                data = resp.json()
            except ValueError:
                raise LoginError("Gameforge devolvió una respuesta ilegible al iniciar sesión")
            if not isinstance(data, dict):
                raise LoginError(f"Gameforge devolvió una respuesta inesperada: {str(data)[:200]}")
            self.token = data.get("token")
            if not self.token:
                raise LoginError("Gameforge no devolvió token de sesión")
        else:
            error_types = ""
            try:
                error_types = ",".join(resp.json().get("errorTypes", []))
            except Exception:
                pass
            if "OTP_REQUIRED" in error_types or "OTP_INVALID" in error_types:
                raise LoginError(
                    "Tu cuenta tiene verificación en dos pasos: desactívala en "
                    "gameforge.com o no podrás usar el bot"
                )
            if "CREDENTIALS_INVALID" in error_types or resp.status_code in (400, 401, 403):
                raise LoginError(
                    "Gameforge rechazó las credenciales: usa el EMAIL de tu cuenta Gameforge "
                    "(no el nick del juego) y su contraseña"
                )
            if resp.status_code == 409:
                raise CaptchaRequired("Gameforge pide captcha; reintenta en unos minutos")
            raise LoginError(f"Login fallido ({resp.status_code}): Gameforge no aceptó la sesión")
        self.session.headers.update({"authorization": f"Bearer {self.token}"})
        self._resolve_server()
        self._enter_game()

    def _apply_game_cookies(self, raw):
        raw = raw.strip()
        if raw.lower().startswith("cookie:"):
            raw = raw.split(":", 1)[1].strip()
        pairs = {}
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                pairs[key.strip()] = value.strip().strip('"').strip("'")
        if not pairs:
            pairs = {"PHPSESSID": raw.strip().strip('"').strip("'")}
        domain = f"s{self.server_number}-{self.language}.ogame.gameforge.com"
        for key, value in pairs.items():
            self.session.cookies.set(key, value, domain=domain, path="/")
        return pairs

    def _enter_game_direct(self):
        if self.server_number is None:
            try:
                servers = self.session.get(LOBBY + "/api/servers", timeout=30).json()
                for server in servers:
                    if str(server.get("name", "")).lower() == self.universe.lower() and server.get("language") == self.language:
                        self.server_number = server["number"]
                        break
            except Exception:
                pass
            if self.server_number is None:
                raise LoginError(f"No encontré el universo {self.universe} ({self.language}) en la lista de servidores")
        self._apply_game_cookies(self.game_cookies)
        self.index_php = f"https://s{self.server_number}-{self.language}.ogame.gameforge.com/game/index.php?"
        try:
            page = self._get(self.index_php + "page=ingame").text
        except requests.RequestException as exc:
            raise LoginError(f"El servidor del juego no respondió: {exc}")
        if not self._parse_ingame(page):
            raise LoginError(
                "La sesión de juego no es válida (el servidor manda al lobby): entra al juego manualmente en el navegador, "
                "copia la cookie PHPSESSID de s277-es.ogame.gameforge.com mientras estás DENTRO, y guárdala de nuevo"
            )

    def _parse_ingame(self, page):
        soup = BeautifulSoup(page, "html.parser")
        player_name = soup.find("meta", {"name": "ogame-player-name"})
        player_id = soup.find("meta", {"name": "ogame-player-id"})
        if player_name is None or player_id is None:
            return False
        self.player = player_name["content"]
        self.player_id = int(player_id["content"])
        version = soup.find("meta", {"name": "ogame-version"})
        self.server_version = version["content"] if version else None
        speed = soup.find("meta", {"name": "ogame-universe-speed"})
        fspeed = soup.find("meta", {"name": "ogame-universe-speed-fleet-peaceful"})
        self.universe_speed = int(speed["content"]) if speed else 1
        self.fleet_speed = int(fspeed["content"]) if fspeed else 1
        return True

    def _resolve_server(self):
        try:
            servers = self.session.get(LOBBY + "/api/servers", timeout=30, headers={"Referer": LOBBY + "/", "Accept": "application/json"}).json()
        except ValueError:
            raise LoginError("El lobby no respondió con la lista de servidores (respuesta no JSON)")
        if not isinstance(servers, list):
            raise LoginError(f"El lobby no devolvió la lista de servidores: {str(servers)[:200]}")
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
            suggestion = difflib.get_close_matches(
                self.universe, [str(s.get("name", "")) for s in servers], n=1, cutoff=0.6
            )
            hint = f" ¿Quisiste decir '{suggestion[0]}'?" if suggestion else " Usa el botón 'Ver universos disponibles' para copiar el nombre exacto"
            raise LoginError(f"Universo '{self.universe}' no encontrado en {self.language}.{hint}")
        self.server_number = target["number"]

        try:
            accounts = self.session.get(LOBBY + "/api/users/me/accounts", timeout=30, headers={"Referer": LOBBY + "/", "Accept": "application/json"}).json()
        except ValueError:
            raise LoginError("El lobby no respondió con la lista de cuentas (respuesta no JSON)")
        if not isinstance(accounts, list):
            raise LoginError(f"El lobby no devolvió la lista de cuentas: {str(accounts)[:200]}")
        blocked_match = False
        for account in accounts:
            srv = account.get("server", {}) or {}
            if srv.get("number") == self.server_number and srv.get("language") == self.language:
                if account.get("blocked"):
                    blocked_match = True
                    continue
                self.server_id = account["id"]
                break
        if self.server_id is None:
            if blocked_match:
                raise LoginError(f"Tu cuenta en {self.universe} está bloqueada o en modo vacaciones: revisa tu correo de Gameforge")
            raise LoginError(f"La cuenta no tiene personaje en {self.universe} ({self.language})")

    def _enter_game(self):
        variants = [
            {},
            {"blackbox": ""},
            {"ageVerificationIgnored": "1"},
        ]
        resp = None
        link = None
        for extra in variants:
            body = {
                "id": self.server_id,
                "server": {"language": self.language, "number": self.server_number},
                "clickedButton": "account_list",
                "blackbox": generate_blackbox(self.session, self.user_agent),
            }
            body.update(extra)
            try:
                resp = self.session.post(
                    LOBBY + "/api/users/me/loginLink",
                    json=body,
                    timeout=30,
                    headers={
                        "Origin": LOBBY,
                        "Referer": LOBBY + "/",
                        "Accept": "application/json",
                    },
                )
            except requests.RequestException as exc:
                raise LoginError(f"No se pudo contactar con el lobby para entrar al juego: {exc}")
            try:
                link = resp.json()
            except ValueError:
                link = None
            if isinstance(link, dict) and "url" in link:
                break
        if not isinstance(link, dict) or "url" not in link:
            if resp is not None and resp.status_code in (401, 403) and "not logged in" in str(link):
                raise LoginError("El lobby dice que la sesión ya no está activa: la cookie se rotó o caducó. Vuelve a copiarla del navegador y guárdala otra vez")
            raise LoginError(
                f"El lobby rechazó la entrada ({resp.status_code if resp is not None else '?'}): {str(link)[:200]}. "
                "Si puedes entrar al juego manualmente en tu navegador, usa abajo el método 'Sesión de juego directa'"
            )
        self.index_php = f"https://s{self.server_number}-{self.language}.ogame.gameforge.com/game/index.php?"
        try:
            self._get(link["url"])
            page = self._get(self.index_php + "page=ingame").text
        except requests.RequestException as exc:
            raise LoginError(f"El servidor del juego no cargó la página: {exc}")
        if not self._parse_ingame(page):
            raise LoginError("Entramos al juego pero la página no cargó la cuenta (posible mantenimiento del universo o sesión rechazada)")

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
        if not self.user_agent:
            self.user_agent = random_user_agent()
        self.session.headers.update({"User-Agent": self.user_agent})
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
        found = False
        for key in ("metal", "crystal", "deuterium", "darkmatter", "energy"):
            node = soup.find(id=f"resources_{key}")
            if node is not None:
                found = True
            res[key] = _to_int(node["data-raw"]) if node is not None else 0
        if not found:
            data = self._get(
                self.index_php + "page=componentOnly&component=resourcesbar&action=fetchResources&asJson=1",
                headers={"X-Requested-With": "XMLHttpRequest"},
            ).json()
            raw = data.get("result", data) if isinstance(data, dict) else {}
            if isinstance(raw, dict):
                res["metal"] = _to_int(raw.get("metal", 0))
                res["crystal"] = _to_int(raw.get("crystal", 0))
                res["deuterium"] = _to_int(raw.get("deuterium", 0))
                res["darkmatter"] = _to_int(raw.get("darkmatter", 0))
                res["energy"] = _to_int(raw.get("energy", 0))
            res["storage"] = []
            return res
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

    @staticmethod
    def _timer_seconds(text):
        if not text:
            return None
        total = 0
        found = False
        for value, unit in re.findall(r"(\d+)\s*([dhms])", str(text).lower()):
            found = True
            total += int(value) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
        return total if found else None

    def _queue_from_soup(self, soup):
        queue = []
        for item in soup.select(".construction .queue li, #construction li"):
            cls = " ".join(item.get("class", []))
            if "first" not in cls and "item" not in cls:
                continue
            timer = item.select_one(".timer")
            left = self._timer_seconds(timer.text.strip()) if timer is not None else None
            queue.append(
                {
                    "tech": item.get("data-technology"),
                    "time_left": left,
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
        elif tech_id in c.SHIPS:
            component = c.COMPONENT_SHIPYARD
        elif tech_id in c.DEFENSES:
            component = c.COMPONENT_DEFENSES
        else:
            raise OGameError(f"Tecnología {tech_id} no construible")
        raw = self._get(self.index_php + f"page=ingame&component={component}&cp={celestial_id}").text
        match = re.search(r'var token = "([0-9a-f]+)"', raw)
        if match is None:
            match = re.search(r"window\.token = '([0-9a-f]+)'", raw)
        if match is None:
            match = re.search(r"var urlQueueAdd = .*?token=([^'\"&;]+)", raw)
        if match is None:
            raise OGameError("No se encontró token de cola de construcción")
        resp = self._post(
            self.index_php + "page=componentOnly&component=buildlistactions&action=scheduleEntry&asJson=1",
            data={
                "technologyId": tech_id,
                "amount": amount,
                "mode": 1,
                "token": match.group(1),
                "planetId": celestial_id,
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        ).json()
        if resp.get("status") == "failure":
            errors = resp.get("errors") or []
            message = errors[0].get("message", "") if errors and isinstance(errors[0], dict) else str(resp)[:200]
            raise OGameError(f"El juego rechazó la construcción: {message}")
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
        try:
            resp = self._post(
                self.index_php + "page=ingame&component=galaxy&action=fetchSolarSystemData&asJson=1",
                data={"galaxy": galaxy, "system": system},
                headers={"X-Requested-With": "XMLHttpRequest"},
            ).json()
        except Exception:
            resp = self._post(
                self.index_php + "page=ingame&component=galaxyContent&ajax=1",
                data={"galaxy": galaxy, "system": system},
                headers={"X-Requested-With": "XMLHttpRequest"},
            ).json()
        if not resp.get("galaxy"):
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
        if not resp.get("success", False) and resp.get("status") != "success":
            errors = resp.get("errors") or []
            message = errors[0].get("message", "") if errors and isinstance(errors[0], dict) else str(resp)[:200]
            raise OGameError(f"Envío de flota rechazado: {message}")
        return resp

    def return_fleet(self, fleet_id):
        page = self._get(self.index_php + "page=ingame&component=movement").text
        if "action=recallFleet" in page:
            match = re.search(r'var token\s*=\s*"([0-9a-f]+)"', page)
            if match is None:
                return False
            resp = self._post(
                self.index_php + "page=ingame&component=movement&action=recallFleet&fleetId={}&asJson=1".format(fleet_id),
                data={"token": match.group(1)},
                headers={"X-Requested-With": "XMLHttpRequest"},
            ).json()
            return resp.get("status") == "success"
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

    def expedition_messages(self, max_pages=2):
        results = []
        for page_num in range(1, max_pages + 1):
            try:
                soup = self._page(f"page=messages&tabid=3&subTab=0&page={page_num}")
            except Exception:
                break
            notes = soup.select(".msg, li.msg, .message")
            if not notes:
                break
            for note in notes:
                body = note.decode_contents()
                coords = re.search(r"\[(\d+):(\d+):16\]", body)
                if coords is None:
                    continue
                ext_id = note.get("data-msg-id") or note.get("id") or ""
                if not ext_id:
                    m = re.search(r"msg_id=(\w+)|messageId=(\w+)", body)
                    ext_id = (m.group(1) or m.group(2)) if m else f"hash-{abs(hash(body[:300]))}"
                metal = re.search(r"Metal[^0-9]{0,40}([\d.,]+)", body)
                crystal = re.search(r"Cristal[^0-9]{0,40}([\d.,]+)", body)
                deuterium = re.search(r"Deuterio[^0-9]{0,40}([\d.,]+)", body)
                dark = re.search(r"ateria oscura[^0-9]{0,40}([\d.,]+)", body)
                lower = body.lower()
                if dark:
                    outcome = "darkmatter"
                elif "objeto" in lower or "item" in lower:
                    outcome = "item"
                elif "naves" in lower and ("encontr" in lower):
                    outcome = "ships"
                elif metal or crystal or deuterium:
                    outcome = "resources"
                elif "pirata" in lower or "alien" in lower:
                    outcome = "battle"
                else:
                    outcome = "nothing"
                ships_text = ""
                ships_count = 0
                if outcome == "ships":
                    sm = re.search(r"(\d+)\s+naves?[^<>]{0,80}", body)
                    ships_text = sm.group(0).strip()[:120] if sm else "naves encontradas"
                    ships_count = int(sm.group(1)) if sm else 0
                item = ""
                if outcome == "item":
                    im = re.search(r"(?:objeto|item)[^<>]{0,80}", body)
                    item = im.group(0).strip()[:120] if im else "objeto encontrado"
                results.append(
                    {
                        "ext_id": f"v13-{ext_id}",
                        "galaxy": int(coords.group(1)),
                        "system": int(coords.group(2)),
                        "outcome": outcome,
                        "metal": _to_int(metal.group(1)) if metal else 0,
                        "crystal": _to_int(crystal.group(1)) if crystal else 0,
                        "deuterium": _to_int(deuterium.group(1)) if deuterium else 0,
                        "darkmatter": _to_int(dark.group(1)) if dark else 0,
                        "ships_count": ships_count,
                        "ships": ships_text,
                        "item": item,
                        "detail": re.sub(r"<[^>]+>", " ", body)[:200],
                    }
                )
        return results

    def server_info(self):
        resp = self._get(f"https://s{self.server_number}-{self.language}.ogame.gameforge.com/api/serverData.xml")
        match = re.search(r"<name>([^<]*)</name>", resp.text)
        speed = re.search(r"<speed>(\d+)</speed>", resp.text)
        return {
            "name": match.group(1) if match else self.universe,
            "speed": int(speed.group(1)) if speed else self.universe_speed,
            "version": self.server_version,
        }
