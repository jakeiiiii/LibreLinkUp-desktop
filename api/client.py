import hashlib
import logging
import requests
from typing import Optional

from api.models import Connection, GraphData, LogbookEntry

logger = logging.getLogger(__name__)

REGIONS = {
    "US": "api-us.libreview.io",
    "Canada": "api-ca.libreview.io",
    "EU": "api-eu.libreview.io",
    "Germany": "api-de.libreview.io",
    "France": "api-fr.libreview.io",
    "Australia": "api-au.libreview.io",
    "Japan": "api-jp.libreview.io",
    "Global": "api.libreview.io",
}

DEFAULT_HEADERS = {
    "product": "llu.android",
    "version": "4.16.0",
    "accept-encoding": "gzip",
    "cache-control": "no-cache",
    "connection": "Keep-Alive",
    "content-type": "application/json",
}


class LibreLinkUpError(Exception):
    pass


class AuthenticationError(LibreLinkUpError):
    pass


class LibreLinkUpClient:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._base_url: str = ""
        self._token: Optional[str] = None
        self._user_id: Optional[str] = None

    def _url(self, path: str) -> str:
        return f"https://{self._base_url}{path}"

    def _auth_headers(self) -> dict:
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._user_id:
            account_id = hashlib.sha256(self._user_id.encode()).hexdigest()
            headers["Account-Id"] = account_id
        return headers

    def login(self, email: str, password: str, region: str = "Canada") -> dict:
        self._base_url = REGIONS.get(region, REGIONS["Canada"])
        self._token = None
        self._user_id = None

        payload = {"email": email, "password": password}
        resp = self._session.post(self._url("/llu/auth/login"), json=payload)
        resp.raise_for_status()
        body = resp.json()

        status = body.get("status", -1)

        # Handle region redirect
        if body.get("data", {}).get("redirect", False):
            new_region = body["data"].get("region", "")
            if new_region:
                self._base_url = f"api-{new_region}.libreview.io"
                logger.info(f"Redirected to region: {new_region}")
                # Retry login on the correct region
                resp = self._session.post(self._url("/llu/auth/login"), json=payload)
                resp.raise_for_status()
                body = resp.json()
                status = body.get("status", -1)

        if status == 4:
            raise AuthenticationError(
                "Account requires accepting terms of use. Please log in via the LibreLinkUp app first."
            )

        if status != 0:
            msg = body.get("error", {}).get("message", "Login failed")
            raise AuthenticationError(msg)

        auth_ticket = body.get("data", {}).get("authTicket", {})
        self._token = auth_ticket.get("token")
        self._user_id = body.get("data", {}).get("user", {}).get("id")

        if not self._token:
            raise AuthenticationError("No authentication token received")

        return body.get("data", {}).get("user", {})

    def get_connections(self) -> list[Connection]:
        resp = self._session.get(
            self._url("/llu/connections"),
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("status") != 0:
            raise LibreLinkUpError("Failed to fetch connections")

        connections = []
        for item in body.get("data", []):
            connections.append(Connection.from_api(item))
        return connections

    def get_graph(self, patient_id: str) -> GraphData:
        resp = self._session.get(
            self._url(f"/llu/connections/{patient_id}/graph"),
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("status") != 0:
            raise LibreLinkUpError("Failed to fetch graph data")

        return GraphData.from_api(body.get("data", {}))

    def get_logbook(self, patient_id: str) -> list[LogbookEntry]:
        resp = self._session.get(
            self._url(f"/llu/connections/{patient_id}/logbook"),
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("status") != 0:
            raise LibreLinkUpError("Failed to fetch logbook")

        entries = []
        for item in body.get("data", []):
            entries.append(LogbookEntry.from_api(item))
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None
