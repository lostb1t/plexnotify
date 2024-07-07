import sys
import os
import asyncio
from typing import Any
from fastapi import Form, Body, FastAPI, APIRouter, HTTPException, Request
import httpx
import logging
#from loguru import logger as log
from aiocache import cached, Cache
from pydantic import Json
from gql import gql, Client
from gql.transport.httpx import HTTPXAsyncTransport, HTTPXTransport

PLEX_TOKEN = os.environ.get('PLEX_TOKEN')
LOG_LEVEL = os.environ.get('LOG_LEVEL', "INFO")

log = logging.getLogger(__name__)
logging.basicConfig(level=LOG_LEVEL)
logging.getLogger('httpx').setLevel(logging.CRITICAL)

app = FastAPI()


client = httpx.AsyncClient(
    headers={
        "X-Plex-Token": PLEX_TOKEN,
        "Accept": "application/json",
        "X-Plex-Client-Identifier": "plexnotify",
        "Content-Type": "application/json",
    }
)

transport = HTTPXAsyncTransport(
    url="https://community.plex.tv/api",
    headers={"x-plex-token": PLEX_TOKEN, "X-plex-client-identifier": "plexnotify"},
)
gql_client = Client(transport=transport, fetch_schema_from_transport=False)


@app.on_event("startup")
async def startup_event():
    log.debug("Connecting to GraphQL backend")
    await gql_client.connect_async(reconnecting=True)
    log.debug("End of startup")


@app.on_event("shutdown")
async def shutdown_event():
    log.debug("Shutting down GraphQL permanent connection...")
    await gql_client.close_async()
    log.debug("Shutting down GraphQL permanent connection... done")


@app.post("/webhooks/plex")
async def get_items(payload: Json = Form(None)):
    log.debug("received webhook: {}".format(payload["event"]))
    if payload["event"] != "library.new":
        return {
            "success": True,
        }
    log.info(
        "New media webook received for {} {}".format(
            payload["Metadata"]["librarySectionType"], payload["Metadata"]["title"]
        )
    )

    log.debug(payload)
    user_id_raw = payload["Account"]["id"]
    user_id = payload["Account"]["thumb"].split("/")[4]
    guid = payload["Metadata"]["guid"]
    server_uuid = payload["Server"]["uuid"]
    server_title = payload["Server"]["title"]
    library_id = payload["Metadata"]["librarySectionID"]
    r = await get_user(user_id, friends=100)
    friends = r["user"]["friends"]["nodes"]
    servers = await shared_servers()

    handles = [handle_user(user_id, user_id_raw, guid, server_title, server_uuid)]
    for f in friends:
        if f["idRaw"] not in servers[server_uuid][library_id]:
            continue

        handles.append(handle_user(f["id"], f["idRaw"], guid, server_title, server_uuid))
    
    await asyncio.gather(*handles)

    return {
        "success": True,
    }


@app.get("/test")
async def test():
    pass


async def handle_user(user_id, user_id_raw, guid, server_title, server_uuid):
    u = await get_user(user_id, watchlist_first=100)
    for w in u["user"]["watchlist"]["nodes"]:
        if guid == w["guid"]:
            log.info(
                "notifying {} for {} {}".format(
                    u["user"]["username"],
                    w["type"].lower(),
                    w["title"],
                )
            )
            r = await notify(
                [str(user_id_raw)],
                w["title"],
                w["type"].lower(),
                server_title,
                server_uuid,
                "https://watch.plex.tv/{}/{}".format(
                    w["type"].lower(), guid.split("/")[3]
                ),
            )
            if r.status_code != httpx.codes.CREATED:
                log.error(r)


async def get_user(id, watchlist_first=2, watchlist_after="", friends=2):
    query = gql(
        """
query UserFriendList($id: ID!, $friends_first: PaginationInt!, $first: PaginationInt!, $after: String) {
  user(id: $id) {
    id
    username
    friends(first: $friends_first) {
      nodes {
        id
        idRaw
      }
    }
    watchlist(first: $first, after: $after) {
      nodes {
        id
        title
        guid
        type
      }
    }
  }
}
  """
    )

    result = await gql_client.session.execute(
        query,
        variable_values={
            "id": id,
            "first": watchlist_first,
            "after": watchlist_after,
            "friends_first": friends,
        },
    )
    return result


async def notify(users, title, type, server_title, server_uuid, uri=None):
    return await client.post(
        "https://notifications.plex.tv/api/v1/notifications",
        json={
            "group": "media",
            "identifier": "tv.plex.notification.library.new",
            "to": users,
            "play": False,
            "data": {
                "provider": {
                    "identifier": server_uuid,
                    "title": server_title,
                },
            },
            "metadata": {
                "type": type,
                "title": title,
            },
            "uri": uri,
        },
    )

@cached(ttl=60*60*24, key="shared", cache=Cache.MEMORY)
async def shared_servers():
    r = await client.get(
        "https://clients.plex.tv/api/v2/shared_servers/owned/accepted",
    )
    data = r.json()
    o = {}
    for k in data:

        # print(k)
        if not k["machineIdentifier"] in o.keys():
            o[k["machineIdentifier"]] = {}
        for l in k["libraries"]:
            if not l["key"] in o[k["machineIdentifier"]].keys():
                o[k["machineIdentifier"]][l["key"]] = []
                # o[k['machineIdentifier']][l['key']].append(USER_RAW_ID)
            if not k["invited"]["id"] in o[k["machineIdentifier"]][l["key"]]:
                o[k["machineIdentifier"]][l["key"]].append(k["invited"]["id"])
                # print(type(k['invited']['id']))

            # if not k['invited']['id'] in o:

            # o[k['machineIdentifier']] = k
    return o
