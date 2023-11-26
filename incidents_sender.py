import datetime
import json
import requests
import logging
import traceback
from requests.adapters import HTTPAdapter, Retry

mpToken = None

def run(target, settings):
    savepoint = None
    has_more = True
    step = 0

    while has_more:
        step += 1

        print('-' * 80)
        print('Step:', step)

        has_more, savepoint = collect(target, settings, savepoint)

        print('Has more:', has_more)
        print('SavePoint:', savepoint)

def collect(target, settings, savepoint):
    logging.info("Collect run started at {}".format(datetime.datetime.now(datetime.timezone.utc)))

    # Disable warnings
    requests.packages.urllib3.disable_warnings()

    # Set savepoint.
    # TODO: More flexible savepoint processing
    if savepoint is None or type(savepoint) is not str:
        savepoint = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=settings["minutes"]))
    else:
        try:
            savepoint = datetime.datetime.strptime(savepoint, '%Y-%m-%dT%H:%M:%S.%f%z')
        except Exception as e:
            logging.error("Error on savepoint processing: {}.".format(e))
            savepoint = datetime.datetime.now(datetime.timezone.utc)

    if (datetime.datetime.now(datetime.timezone.utc) - savepoint).days > 1:
        savepoint = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=settings["minutes"]))

    try:
       # Obtain access token
       token = obtain_token(target, settings["first_credential"]["login"], settings["first_credential"]["password"],settings["client_secret"])
       bearerToken = token["access_token"]

       # Get incidents and enrich them with description
       incidents = get_incidents(bearerToken, target, savepoint)
       incidents["incidents"] = [
        {**incident, "description": get_incident_data(bearerToken, target, incident["id"])["description"]}
        for incident in incidents["incidents"]
       ]

       # Send incidents to Telegram, Mattermost and MS Teams
       if (settings['tg_enabled'] and settings['tg_token'] and settings['chat_id']):
        send_to_telegram(incidents, settings["tg_token"], settings["chat_id"], target, settings["gmt"])

       if (settings['mm_enabled'] and settings['mm_webhook_url']): 
        send_to_mattermost(incidents, settings["mm_webhook_url"], target, settings["gmt"], settings["mm_username"])
    
       if (settings['teams_enabled'] and settings['teams_webhook_url']): 
        send_to_teams(incidents, settings["teams_webhook_url"], target, settings["gmt"])
       
       # Process savepoint
       savepoint = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f%z')

       return False, savepoint

    except Exception as e:
        logging.error("Error while running collect: {}.".format(e))
        logging.error(traceback.format_exc())

    return False, savepoint

# Perform HTTP request
def make_request(method, url, headers=None, data=None):
    with requests.Session() as session:
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504, 401])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        response = session.request(method, url, headers=headers, data=data, verify=False, timeout=360)

    if response.ok or (method == "POST" and response.status_code == 400):
        return response
    else:
        raise Exception(f'Request {method} {url} failed with {response.status_code} - {response.text}')
    
def obtain_token(core_address, login, password, client_secret):
    global mpToken

    if mpToken is None:
        # Make a token request
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        payload = {
            "grant_type": "password",
            "client_id": "mpx",
            "client_secret": client_secret,
            "scope": "offline_access mpx.api ptkb.api",
            "response_type": "code id_token token",
            "username": login,
            "password": password
        }
        logging.info(f"Making token request to https://{core_address}:3334/connect/token")

        response = make_request(
            "POST",
            f"https://{core_address}:3334/connect/token",
            headers=headers,
            data=payload
        )

        # Process the response
        response_data = json.loads(response.text)
        response_data["obtain_time"] = datetime.datetime.now().isoformat()

        mpToken = response_data

        logging.info("Token fetched")

        return mpToken
    else:
        # Check if the token needs to be refreshed
        if (datetime.datetime.now() - datetime.datetime.strptime(mpToken["obtain_time"], '%Y-%m-%dT%H:%M:%S.%f')) > datetime.timedelta(hours=12):
            # Refresh the token
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            payload = {
                "grant_type": "refresh_token",
                "client_id": "mpx",
                "client_secret": client_secret,
                "scope": "offline_access mpx.api ptkb.api",
                "refresh_token": mpToken["refresh_token"],
                "username": login,
                "password": password
            }
            logging.info(f"Refreshing token https://{core_address}:3334/connect/token")

            response = make_request(
                "POST",
                f"https://{core_address}:3334/connect/token",
                headers=headers,
                data=payload
            )

            # Process the response
            response_data = json.loads(response.text)
            response_data["obtain_time"] = datetime.datetime.now().isoformat()

            mpToken = response_data

            logging.info(f"Token refreshed")

            return response_data
        else:
            # Token is still valid
            logging.info(f"Token already obtained and valid")
            return mpToken
        
def get_incidents(access_token, core_address, savepoint):

    # Set the headers for the API request
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + access_token
    }

    # Set the payload for the API request
    payload = {
        "offset": 0,
        "limit": 50,
        "groups": {
            "filterType": "no_filter"
        },
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
                "assigned"
            ],
            "where": "(status != \"Closed\")",
            "orderby": [
                {
                    "field": "created",
                    "sortOrder": "ascending"
                }
            ]
        },
        "queryIds": [
            "all_incidents"
        ]
    }

    # Make the API request
    response = make_request(
        "POST",
        f"https://{core_address}/api/v2/incidents",
        headers=headers,
        data=json.dumps(payload)
    )

    return json.loads(response.text)

def get_incident_data(accessToken, core_address, id):

    # Set the headers for the request
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + accessToken
    }

    # Make the GET request to retrieve the incident data
    response = make_request(
        "GET",
        f"https://{core_address}/api/incidentsReadModel/incidents/{id}",
        headers=headers
    )

    return json.loads(response.text)

def send_to_telegram(incidents, tg_token, chat_id, core_address, gmt):

    # Iterate over incidents and send each one to Telegram
    for incident in incidents["incidents"]:

        # Create the message to send
        message = f'<b>ID</b>: <a href="https://{core_address}/#/incident/incidents/view/{incident["id"]}">{incident["key"]}</a>\n' \
                  f'<b>{incident["name"]}</b>\n' \
                  f'{incident["description"]}\n\n' \
                  f'<b>Опасность</b>: {incident["severity"]}\n' \
                  f'<b>Создан</b>: {(datetime.datetime.strptime(incident["created"][:26], "%Y-%m-%dT%H:%M:%S.%f") + datetime.timedelta(hours=gmt)).strftime("%H:%M:%S %d.%m.%Y")}\n' \
                  f'<a href="https://{core_address}/#/events/view?groupId=-1&incKey={incident["key"]}&incidentId={incident["id"]}&incidentName={incident["name"]}">Перейти к событиям</a>'
        
        # Send the message to Telegram
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }

        make_request("POST",
                     f"https://api.telegram.org/bot{tg_token}/sendMessage",
                     headers=None,
                     data=data)
        
        logging.info(f"{incident['key']} sended to Telegram successfully")

def send_to_mattermost(incidents, mm_webhook_url, core_address, gmt, mm_username):

    # Iterate over incidents and send each one to Mattermost
    for incident in incidents["incidents"]:

        # Create the message to send
        message = f"*ID*: [{incident['key']}](https://{core_address}/#/incident/incidents/view/{incident['id']})\n" \
                  f"*Имя*: {incident['name']}\n" \
                  f"*Опасность*: {incident['severity']}\n" \
                  f"*Создан*: {(datetime.datetime.strptime(incident['created'][:26], '%Y-%m-%dT%H:%M:%S.%f') + datetime.timedelta(hours=gmt)).strftime('%H:%M:%S %d.%m.%Y')}\n" \
                  f"*Описание*: {incident['description']}\n" \
                  f"[Перейти к событиям](https://{core_address}/#/events/view?groupId=-1&incKey={incident['key']}&incidentId={incident['id']}&incidentName={incident['name']})"
        

        # Send the message to Mattermost
        data = {
            "username": mm_username,
            "text": message
        }

        test = make_request("POST",
                     mm_webhook_url,
                     headers=None,
                     data=json.dumps(data))
        logging.info(test.json())
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
                    "size": "Large"
                },
                {
                    "type": "TextBlock",
                    "text": incident['description'],
                    "weight": "Bolder",
                    "size": "Medium",
                    "wrap": True
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {
                            "title": "ID",
                            "value": f"[{incident['key']}](https://{core_address}/#/incident/incidents/view/{incident['id']})"
                        },
                        {
                            "title": "Важность",
                            "value": incident['severity']
                        },
                        {
                            "title": "Создан",
                            "value": (datetime.datetime.strptime(incident['created'][:26], '%Y-%m-%dT%H:%M:%S.%f') + datetime.timedelta(hours=gmt)).strftime('%H:%M:%S %d.%m.%Y')
                        }
                    ]
                }
            ]
        }

        # Send the message to MS Teams
        data = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card
                }
            ]
        }

        make_request("POST",
                     teams_webhook_url,
                     headers=None,
                     data=json.dumps(data))
        
        logging.info(f"{incident['key']} sended to MS Teams successfully")


if __name__ == '__main__':
    target = "127.0.0.1"
    settings = dict(minutes=10,
                    gmt=3,
                    client_secret="",
                    tg_enabled = True,
                    chat_id="",
                    tg_token="",
                    mm_enabled = False,
                    mm_username = "",
                    mm_webhook_url = "",
                    teams_enabled = False,
                    teams_webhook_url = "",
                    first_credential=dict(
                        login="",
                        password=""
                    )
                   )
    run(target, settings)