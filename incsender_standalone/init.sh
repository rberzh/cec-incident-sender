#!/bin/bash

if [ -f ./config/default.env ]; then
    source ./config/default.env
fi

echo "  ___ _____    ___                          _ _         ";
echo " | _ \_   _|  / __|___ _ __  _ __ _  _ _ _ (_) |_ _  _  ";
echo " |  _/ | |   | (__/ _ \ '  \| '  \ || | ' \| |  _| || | ";
echo " |_|   |_|    \___\___/_|_|_|_|_|_\_,_|_||_|_|\__|\_, | ";
echo "                                                  |__/  ";

echo "Incidints sender service must be configured before use. Params description:"
echo "+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
echo "SCHEDULE: Периодичность запуска в минутах"
echo "MINUTES: Насколько мы смотрим назад при первом запуске, пока не сформирован savepoint"
echo "GMT: Временная поправка, т.к. мы получаем время в GMT+0"
echo "FILTER_TYPE: Режим работы фильтра уведомлений, wl - отправляются только уведомления от инцидентов, которые указаны в табличном списке; bl - уведомления от инцидентов из табличного списка не отправляются. Оставьте пустым для отключения фильтрации. Параметр table_list_name должен быть заполнен, а в системе создан и установлен соответствующий табличный список с колонкой name"
echo "TABLE_LIST_NAME: Название табличного списка, содержащего правила корреляций для работы фильтра (в колонке name)"
echo "TG_ENABLED: Включение отправки в Telegram"
echo "CHAT_ID: ID Telegram-чата куда бот будет высылать сообщения"
echo "TG_TOKEN: Токен бота для отправки в Telegram"
echo "MM_ENABLED: Включение отправки в Mattermost"
echo "MM_USERNAME: Имя с которым будет отправлено сообщение в Mattermost"
echo "MM_WEBHOOK_URL: Адрес вебхука для отправки в Mattermost (генерируется в Mattermost)"
echo "TEAMS_ENABLED: Включение отправки в MS Teams"
echo "TEAMS_WEBHOOK_URL: Адрес вебхука для отправки в MS Teams (генерируется в MS Teams)"
echo "SYSLOG_ENABLED: Включение отправки по Syslog"
echo "SYSLOG_FULL_BODY: Отправка полного тела события по Syslog. Если False, то отправляется сообщение с именем|важностью|описанием и временем сработки. Формат сообщения CEF-like в обоих вариантах"
echo "SYSLOG_SERVER: Адрес принимающего Syslog-сервера"
echo "SYSLOG_PROTO: Протокол отправки Syslog: tcp / udp"
echo "SYSLOG_PORT: Порт, на который будут отправлены Syslog-события"
echo "FIRST_CREDENTIAL_LOGIN: Логин учетной записи MP10"
echo "FIRST_CREDENTIAL_PASSWORD: Пароль учетной записи MP10"
echo "SECOND_CREDENTIAL_PASSWORD: Client Secret для доступа к API"
echo "+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
echo " "

input_with_default() {
  local var_name=$1
  local default_value=$2
  local description=$3
  local input
  local escaped_default_value

  escaped_default_value=$(printf '%q' "$default_value")

  read -p "Enter value for ${var_name} (current: ${escaped_default_value}): " input
  if [[ $input =~ [^a-zA-Z0-9_] ]]; then
    export $var_name="'${input:-$default_value}'"
  else
    export $var_name=${input:-$default_value}
  fi
}

input_with_default "MP10_ADDRESS" "$MP10_ADDRESS"
input_with_default "SCHEDULE" "$SCHEDULE"
input_with_default "MINUTES" "$MINUTES"
input_with_default "GMT" "$GMT"
input_with_default "FILTER_TYPE" "$FILTER_TYPE"
input_with_default "TABLE_LIST_NAME" "$TABLE_LIST_NAME"
input_with_default "TG_ENABLED" "$TG_ENABLED"
input_with_default "CHAT_ID" "$CHAT_ID"
input_with_default "TG_TOKEN" "$TG_TOKEN"
input_with_default "MM_ENABLED" "$MM_ENABLED"
input_with_default "MM_USERNAME" "$MM_USERNAME"
input_with_default "MM_WEBHOOK_URL" "$MM_WEBHOOK_URL"
input_with_default "TEAMS_ENABLED" "$TEAMS_ENABLED"
input_with_default "TEAMS_WEBHOOK_URL" "$TEAMS_WEBHOOK_URL"
input_with_default "SYSLOG_ENABLED" "$SYSLOG_ENABLED"
input_with_default "SYSLOG_FULL_BODY" "$SYSLOG_FULL_BODY"
input_with_default "SYSLOG_SERVER" "$SYSLOG_SERVER"
input_with_default "SYSLOG_PROTO" "$SYSLOG_PROTO"
input_with_default "SYSLOG_PORT" "$SYSLOG_PORT"
input_with_default "FIRST_CREDENTIAL_LOGIN" "$FIRST_CREDENTIAL_LOGIN"
input_with_default "FIRST_CREDENTIAL_PASSWORD" "$FIRST_CREDENTIAL_PASSWORD"
input_with_default "SECOND_CREDENTIAL_PASSWORD" "$SECOND_CREDENTIAL_PASSWORD"

cat <<EOF > ./config/default.env
MP10_ADDRESS=${MP10_ADDRESS}
SCHEDULE=${SCHEDULE}
MINUTES=${MINUTES}
GMT=${GMT}
FILTER_TYPE=${FILTER_TYPE}
TABLE_LIST_NAME=${TABLE_LIST_NAME}
TG_ENABLED=${TG_ENABLED}
CHAT_ID=${CHAT_ID}
TG_TOKEN=${TG_TOKEN}
MM_ENABLED=${MM_ENABLED}
MM_USERNAME=${MM_USERNAME}
MM_WEBHOOK_URL=${MM_WEBHOOK_URL}
TEAMS_ENABLED=${TEAMS_ENABLED}
TEAMS_WEBHOOK_URL=${TEAMS_WEBHOOK_URL}
SYSLOG_ENABLED=${SYSLOG_ENABLED}
SYSLOG_FULL_BODY=${SYSLOG_FULL_BODY}
SYSLOG_SERVER=${SYSLOG_SERVER}
SYSLOG_PROTO=${SYSLOG_PROTO}
SYSLOG_PORT=${SYSLOG_PORT}
FIRST_CREDENTIAL_LOGIN=${FIRST_CREDENTIAL_LOGIN}
FIRST_CREDENTIAL_PASSWORD=${FIRST_CREDENTIAL_PASSWORD}
SECOND_CREDENTIAL_PASSWORD=${SECOND_CREDENTIAL_PASSWORD}
EOF
echo " "
echo "+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
echo " "

if command -v docker-compose &> /dev/null && docker-compose --version &> /dev/null; then
    compose_cmd="docker-compose"
elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
    compose_cmd="docker compose"
else
    echo "Error: Neither 'docker-compose' nor 'docker compose' command found. Please install docker & docker-compose first."
    exit 1
fi

if docker images | grep -q "incsender"; then
    read -p "Image 'incsender' already exists. Do you want to update variables or rebuild? (update/rebuild): " choice
    case $choice in
        update)
            $compose_cmd down
            $compose_cmd up -d
            ;;
        rebuild)
            $compose_cmd down
            docker rmi incsender
            $compose_cmd up -d
            ;;
        *)
            echo "Invalid choice. Please enter 'update' or 'rebuild'."
            ;;
    esac
else
    $compose_cmd up -d
fi
