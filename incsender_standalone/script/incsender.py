import os
import datetime
import json
import requests
import logging
import socket
import traceback
from requests.adapters import HTTPAdapter, Retry
import logging.handlers
import time

mpToken = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/var/log/incsender.log"),
        logging.handlers.RotatingFileHandler("/var/log/incsender.log", maxBytes=10000000, backupCount=1),
        logging.StreamHandler()
    ]
)

def run(target, settings):
    savepoint = None
    has_more = True

    while has_more:
        
        if os.path.exists("./savepoint"):
          with open("savepoint", "r") as file:
            savepoint = file.read()
        else:
            savepoint = None

        has_more, savepoint = collect(target, settings, savepoint)

        with open("savepoint", "w") as file:
            file.write(str(savepoint))

        time.sleep(int(settings["schedule"])*60)


def collect(target, settings, savepoint):
    logging.info(
        "Collect run started at {}".format(datetime.datetime.now(datetime.timezone.utc))
    )

    # Disable warnings
    requests.packages.urllib3.disable_warnings()

    # Set savepoint.
    # TODO: More flexible savepoint processing
    if savepoint is None or not isinstance(savepoint, str):
        savepoint = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=settings["minutes"]
        )
    else:
        try:
            savepoint = datetime.datetime.strptime(savepoint, "%Y-%m-%dT%H:%M:%S.%f%z")
        except Exception as e:
            logging.info("Error on savepoint processing: {}.".format(e))
            savepoint = datetime.datetime.now(datetime.timezone.utc)

    if (datetime.datetime.now(datetime.timezone.utc) - savepoint).days > 1:
        savepoint = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=settings["minutes"]
        )

    try:
        # Obtain access token
        token = obtain_token(
            target,
            settings["first_credential"]["login"],
            settings["first_credential"]["password"],
            settings["second_credential"]["password"],
        )
        bearerToken = token["access_token"]

        # Get incidents
        incidents = get_incidents(bearerToken, target, savepoint)

        # Get incidents filter from table list and filter incidents
        if (
            settings["filter_type"].lower() not in ["bl", "wl"]
            or settings["table_list_name"] == ""
        ):
            logging.info(
                "Skip filtering due to invalid filter type or empty table list name"
            )
        else:
            filter = get_table_blacklist(
                bearerToken, target, settings["table_list_name"]
            )
            if settings["filter_type"].lower() == "bl":
                incidents["incidents"] = [
                    incident
                    for incident in incidents["incidents"]
                    if not any(
                        incident["name"] == item["name"]
                        for item in filter.get("items", [])
                    )
                ]
            elif settings["filter_type"].lower() == "wl":
                incidents["incidents"] = [
                    incident
                    for incident in incidents["incidents"]
                    if any(
                        incident["name"] == item["name"]
                        for item in filter.get("items", [])
                    )
                ]

        # Enrich incidents with description
        incidents["incidents"] = [
            {
                **incident,
                "description": get_incident_data(bearerToken, target, incident["id"])[
                    "description"
                ],
            }
            for incident in incidents["incidents"]
        ]

        # Send incidents to outputs
        if settings["tg_enabled"] and settings["tg_token"] and settings["chat_id"]:
            send_to_telegram(
                incidents,
                settings["tg_token"],
                settings["chat_id"],
                target,
                settings["gmt"],
            )

        if settings["mm_enabled"] and settings["mm_webhook_url"]:
            send_to_mattermost(
                incidents,
                settings["mm_webhook_url"],
                target,
                settings["gmt"],
                settings["mm_username"],
            )

        if settings["syslog_enabled"] and settings["syslog_server"]:
            if settings["syslog_full_body"]:
                full_incidents = [
                    json.dumps(
                        get_incident_data(bearerToken, target, incident["id"]),
                        ensure_ascii=False,
                    )
                    for incident in incidents["incidents"]
                ]
                send_to_syslog(
                    full_incidents,
                    settings["gmt"],
                    settings["syslog_server"],
                    target,
                    settings["syslog_proto"],
                    settings["syslog_port"],
                    settings["syslog_full_body"],
                )
            else:
                send_to_syslog(
                    incidents,
                    settings["gmt"],
                    settings["syslog_server"],
                    target,
                    settings["syslog_proto"],
                    settings["syslog_port"],
                    settings["syslog_full_body"],
                )

        if settings["teams_enabled"] and settings["teams_webhook_url"]:
            send_to_teams(
                incidents, settings["teams_webhook_url"], target, settings["gmt"]
            )

        # Process savepoint
        savepoint = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f%z")

        return True, savepoint

    except Exception as e:
        logging.error("Error while running collect: {}.".format(e))
        logging.error(traceback.format_exc())

        return True, savepoint


# Perform HTTP request
def make_request(method, url, headers=None, data=None):
    with requests.Session() as session:
        retries = Retry(
            total=5, backoff_factor=1, status_forcelist=[502, 503, 504, 401]
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        response = session.request(
            method, url, headers=headers, data=data, verify=False, timeout=360
        )

    if response.ok or (method == "POST" and response.status_code == 400):
        return response
    else:
        raise Exception(
            f"Request {method} {url} failed with {response.status_code} - {response.text}"
        )


def obtain_token(core_address, login, password, client_secret):
    global mpToken

    if mpToken is None:
        # Make a token request
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "grant_type": "password",
            "client_id": "mpx",
            "client_secret": client_secret,
            "scope": "offline_access mpx.api ptkb.api",
            "response_type": "code id_token token",
            "username": login,
            "password": password,
        }
        logging.info(
            f"Making token request to https://{core_address}:3334/connect/token"
        )

        response = make_request(
            "POST",
            f"https://{core_address}:3334/connect/token",
            headers=headers,
            data=payload,
        )

        # Process the response
        response_data = json.loads(response.text)
        response_data["obtain_time"] = datetime.datetime.now().isoformat()

        mpToken = response_data

        logging.info("Token fetched")

        return mpToken
    else:
        # Check if the token needs to be refreshed
        if (
            datetime.datetime.now()
            - datetime.datetime.strptime(mpToken["obtain_time"], "%Y-%m-%dT%H:%M:%S.%f")
        ) > datetime.timedelta(hours=12):
            # Refresh the token
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            payload = {
                "grant_type": "refresh_token",
                "client_id": "mpx",
                "client_secret": client_secret,
                "scope": "offline_access mpx.api ptkb.api",
                "refresh_token": mpToken["refresh_token"],
                "username": login,
                "password": password,
            }
            logging.info(f"Refreshing token https://{core_address}:3334/connect/token")

            response = make_request(
                "POST",
                f"https://{core_address}:3334/connect/token",
                headers=headers,
                data=payload,
            )

            # Process the response
            response_data = json.loads(response.text)
            response_data["obtain_time"] = datetime.datetime.now().isoformat()

            mpToken = response_data

            logging.info("Token refreshed")

            return response_data
        else:
            # Token is still valid
            logging.info("Token already obtained and valid")
            return mpToken


def get_incidents(access_token, core_address, savepoint):
    # Set the headers for the API request
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + access_token,
    }

    # Set the payload for the API request
    payload = {
        "offset": 0,
        "limit": 50,
        "groups": {"filterType": "no_filter"},
        "timeFrom": savepoint.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "timeTo": None,
        "filterTimeType": "creation",
        "filter": {
            "select": [
                "key",
                "name",
                "category",
                "type",
                "status",
                "created",
                "assigned",
            ],
            "where": '(status != "Closed")',
            "orderby": [{"field": "created", "sortOrder": "ascending"}],
        },
        "queryIds": ["all_incidents"],
    }

    # Make the API request
    response = make_request(
        "POST",
        f"https://{core_address}/api/v2/incidents",
        headers=headers,
        data=json.dumps(payload),
    )

    return json.loads(response.text)


def get_table_blacklist(access_token, core_address, table_list_name):
    # Set the headers for the API request
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + access_token,
    }

    table_lists = json.loads(
        make_request(
            "GET",
            f"https://{core_address}/api/events/v2/table_lists?kind=registry",
            headers=headers,
        ).text
    )

    filter_list_token = [
        table_list["token"]
        for table_list in table_lists
        if table_list["name"] == table_list_name
    ][0]

    # Set the payload for the API request
    payload = {
        "offset": 0,
        "limit": 100,
        "filter": {
            "select": ["_last_changed", "name"],
            "where": "",
            "orderBy": [{"field": "_last_changed", "sortOrder": "descending"}],
            "timeZone": 180,
        },
    }

    # Make the API request
    response = make_request(
        "POST",
        f"https://{core_address}/api/events/v2/table_lists/{filter_list_token}/content/search",
        headers=headers,
        data=json.dumps(payload),
    )

    return json.loads(response.text)


def get_incident_data(accessToken, core_address, id):
    # Set the headers for the request
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + accessToken,
    }

    # Make the GET request to retrieve the incident data
    response = make_request(
        "GET",
        f"https://{core_address}/api/incidentsReadModel/incidents/{id}",
        headers=headers,
    )

    return json.loads(response.text)


def send_to_telegram(incidents, tg_token, chat_id, core_address, gmt):
    # Iterate over incidents and send each one to Telegram
    for incident in incidents["incidents"]:
        # Create the message to send
        message = (
            f'<b>ID</b>: <a href="https://{core_address}/#/incident/incidents/view/{incident["id"]}">{incident["key"]}</a>\n'
            f'<b>{incident["name"]}</b>\n'
            f'{incident["description"]}\n\n'
            f'<b>Опасность</b>: {incident["severity"]}\n'
            f'<b>Создан</b>: {(datetime.datetime.strptime(incident["created"][:26], "%Y-%m-%dT%H:%M:%S.%f") + datetime.timedelta(hours=gmt)).strftime("%H:%M:%S %d.%m.%Y")}\n'
            f'<a href="https://{core_address}/#/events/view?groupId=-1&incKey={incident["key"]}&incidentId={incident["id"]}&incidentName={incident["name"]}">Перейти к событиям</a>'
        )

        # Send the message to Telegram
        data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}

        make_request(
            "POST",
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            headers=None,
            data=data,
        )

        logging.info(f"{incident['key']} sended to Telegram successfully")


def send_to_mattermost(incidents, mm_webhook_url, core_address, gmt, mm_username):
    # Iterate over incidents and send each one to Mattermost
    for incident in incidents["incidents"]:
        # Create the message to send
        message = (
            f"*ID*: [{incident['key']}](https://{core_address}/#/incident/incidents/view/{incident['id']})\n"
            f"*Имя*: {incident['name']}\n"
            f"*Опасность*: {incident['severity']}\n"
            f"*Создан*: {(datetime.datetime.strptime(incident['created'][:26], '%Y-%m-%dT%H:%M:%S.%f') + datetime.timedelta(hours=gmt)).strftime('%H:%M:%S %d.%m.%Y')}\n"
            f"*Описание*: {incident['description']}\n"
            f"[Перейти к событиям](https://{core_address}/#/events/view?groupId=-1&incKey={incident['key']}&incidentId={incident['id']}&incidentName={incident['name']})"
        )

        # Send the message to Mattermost
        data = {"username": mm_username, "text": message}

        make_request("POST", mm_webhook_url, headers=None, data=json.dumps(data))

        logging.info(f"{incident['key']} sended to Mattermost successfully")


def send_to_teams(incidents, teams_webhook_url, core_address, gmt):
    # Iterate over incidents and send each one to MS Teams
    for incident in incidents["incidents"]:
        # Build Adaptive Card for Teams message
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f'{incident["name"]}',
                    "weight": "Bolder",
                    "size": "Large",
                },
                {
                    "type": "TextBlock",
                    "text": incident["description"],
                    "weight": "Bolder",
                    "size": "Medium",
                    "wrap": True,
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {
                            "title": "ID",
                            "value": f"[{incident['key']}](https://{core_address}/#/incident/incidents/view/{incident['id']})",
                        },
                        {"title": "Важность", "value": incident["severity"]},
                        {
                            "title": "Создан",
                            "value": (
                                datetime.datetime.strptime(
                                    incident["created"][:26], "%Y-%m-%dT%H:%M:%S.%f"
                                )
                                + datetime.timedelta(hours=gmt)
                            ).strftime("%H:%M:%S %d.%m.%Y"),
                        },
                    ],
                },
            ],
        }

        # Send the message to MS Teams
        data = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }

        make_request("POST", teams_webhook_url, headers=None, data=json.dumps(data))

        logging.info(f"{incident['key']} sended to MS Teams successfully")


def send_to_syslog(incidents, gmt, syslog_server, core_address, protocol, port, isFullBody):
    # Create a socket for sending messages
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM if protocol.lower() == "tcp" else socket.SOCK_DGRAM)

    # Connect to the syslog server
    sock.connect((syslog_server, port))

    # Iterate over incidents and send each one to the syslog server
    if isFullBody:
        for incident in incidents:
            # Format the incident data in CEF (or like CEF) format
            full_body_kv = convert_json_to_plain_text(json.loads(incident))
            inc = json.loads(incident)
            message = f"CEF:0|PT|SIEM|8.0|{inc['name']}|{inc['severity']}|{full_body_kv}\n"

            # Send the message to the syslog server
            sock.send(message.encode("utf-8"))
            
            logging.info(f"Incident {json.loads(incident)['key']} sent to syslog server successfully")
    else:
        for incident in incidents["incidents"]:
            link = f"https://{core_address}/#/incident/incidents/view/{incident['id']}"

            message = f"CEF:0|PT|SIEM|8.0|{incident['name']}|{incident['severity']}|description={incident['description']} link={link} time={(datetime.datetime.strptime(incident['created'][:26], '%Y-%m-%dT%H:%M:%S.%f') + datetime.timedelta(hours=gmt)).strftime('%H:%M:%S %d.%m.%Y')}\n"

            # Send the message to the syslog server
            sock.send(message.encode("utf-8"))
            
            logging.info(f"Incident {incident['key']} sent to syslog server successfully")

    # Close the socket connection
    sock.close()

def convert_json_to_plain_text(data, prefix=""):
    plain_text = ""
    if isinstance(data, dict):
        for key, value in data.items():
            if prefix:
                new_prefix = f"{prefix}.{key}"
            else:
                new_prefix = key
            plain_text += convert_json_to_plain_text(value, new_prefix) + " "
    elif isinstance(data, list):
        for index, value in enumerate(data):
            new_prefix = f"{prefix}[{index}]"
            plain_text += convert_json_to_plain_text(value, new_prefix) + " "
    else:
        plain_text = f"{prefix}={data}"
    return plain_text.strip()
    
if __name__ == "__main__":
    target = os.getenv('MP10_ADDRESS', '')
    settings = dict(
     schedule = os.environ.get('SCHEDULE', '5'),
     minutes=int(os.getenv('MINUTES', '10')),
     gmt=int(os.getenv('GMT', '3')),
     filter_type=os.getenv('FILTER_TYPE', ''),
     table_list_name=os.getenv('TABLE_LIST_NAME', ''),
     tg_enabled=bool(os.getenv('TG_ENABLED', 'False')),
     chat_id=os.getenv('CHAT_ID', ''),
     tg_token=os.getenv('TG_TOKEN', ''),
     mm_enabled=bool(os.getenv('MM_ENABLED', 'False')),
     mm_username=os.getenv('MM_USERNAME', ''),
     mm_webhook_url=os.getenv('MM_WEBHOOK_URL', ''),
     teams_enabled=bool(os.getenv('TEAMS_ENABLED', 'False')),
     teams_webhook_url=os.getenv('TEAMS_WEBHOOK_URL', ''),
     syslog_enabled=bool(os.getenv('SYSLOG_ENABLED', 'True')),
     syslog_full_body=bool(os.getenv('SYSLOG_FULL_BODY', 'True')),
     syslog_server=os.getenv('SYSLOG_SERVER', ''),
     syslog_proto=os.getenv('SYSLOG_PROTO', 'tcp'),
     syslog_port=int(os.getenv('SYSLOG_PORT', '1468')),
     first_credential=dict(login=os.getenv('FIRST_CREDENTIAL_LOGIN', ''), password=os.getenv('FIRST_CREDENTIAL_PASSWORD', '')),
     second_credential=dict(password=os.getenv('SECOND_CREDENTIAL_PASSWORD', ''))
)
    run(target, settings)
