# CEC Incidents sender
Скрипт для MaxPatrol 10 Custom Event Collector, отправляющий уведомления об инцидентах в Telegram/Mattermost/MS Teams/на syslog-сервер.

Работа проверена на версиях 26.1 - 27.3

## Список файлов
- incidents_sender.py - сам скрипт (код для добоавления в справочник)
- Incidents Sender.json - профиль для импорта в MaxPatrol 10

## Требования
MP10 Collector, на котором будет запущена задача должен иметь доступ к MaxPatrol 10 Core/MС по IP/FQDN (в зависимости от того как настроен MaxPatrol 10) по портам 443 и 3334, а так же к соответствующим серверам (Telegram, MS Teams, Mattermost).

## Использование
1. Создать справочник incidents_sender с кодом из .py файла
2. Импортировать профиль в систему (.json-файл) и настроить "Параметры запуска сценария", а так же "Интервал опроса модуля" (параметр в секундах, который отвечает за частоту запуска скрипта).
 "table_list_name": "", # Название табличного списка, содержащего правила корреляций для работы фильтра (в колонке name)
3. **Опционально, для фильтрации уведомлений:** Создать, добавить в набор и установить табличный список в SIEM. Табличный список должен иметь колонку name: имена правил корреляции (инцидентов) добавляются отдельными записями. Название табличного списка задается произвольно и должно быть указано в параметре table_list_name. Режим работы фильтра задается в параметре filter_type
4. Создать учетную запись типа Логин-пароль с учетной записью MaxPatrol 10, от имени которой будут запрашиваться инциденты
5. Создать учетную запись типа Пароль, содержащую client_secret [Как получить client_secret](https://help.ptsecurity.com/projects/maxpatrol10/26.1/ru-RU/help/3678991755)
6. Создать задачу на основе созданного профиля, указав в качестве цели FQDN/IP (в зависимости от настройки MaxPatrol 10) сервера Core/MC/KB, в качестве учетной записи созданную в п.3 УЗ, в качестве учетной записи для повышения привилегий УЗ из п.4

## Параметры запуска сценария:
```
{
 "chat_id": "id_of_telegram_chat", # ID Telegram-чата куда бот будет высылать сообщения
 "gmt": 3, # Временная поправка, т.к. мы получаем время в GMT+0
 "minutes": 10, # Насколько мы смотрим "назад" при первом запуске, пока не сформирован savepoint
 "filter_type": "", # Режим работы фильтра уведомлений, "wl" - отправляются только уведомления от инцидентов, которые указаны в табличном списке; "bl" - уведомления от инцидентов из табличного списка не отправляются. Оставьте пустым для отключения фильтрации. Параметр table_list_name должен быть заполнен, а в системе создан и установлен соответствующий табличный список с колонкой name
 "table_list_name": "", # Название табличного списка, содержащего правила корреляций для работы фильтра (в колонке name)
 "mm_enabled": true, # Включение отправки в Mattermost
 "mm_username": "", # Имя с которым будет отправлено сообщение в Mattermost 
 "mm_webhook_url": "mattermost_webhook_url", # Адрес вебхука для отправки в Mattermost (генерируется в Mattermost)
 "teams_enabled": true, # Включение отправки в MS Teams
 "teams_webhook_url": "teams_webhook_url", # Адрес вебхука для отправки в MS Teams (генерируется в MS Teams)
 "tg_enabled": true, # Включение отправки в Telegram
 "tg_token": "telegram_token" # Токен бота для отправки в Telegram
 "syslog_enabled": false, # Включение отправки по Syslog
 "syslog_full_body": true, # Отправка полного тела события по Syslog. Если False, то отправляется сообщение с именем|важностью|описанием и временем сработки. Формат сообщения CEF-like в обоих вариантах
 "syslog_server": "", # Адрес принимающего Syslog-сервера
 "syslog_proto": "tcp", # Протокол отправки Syslog: tcp / udp
 "syslog_port": 514, # Порт, на который будут отправлены Syslog-события
}
```

## Standalone-версия
Так же доступна Standalone-версия для запуска на сервере / в Docker-контейнере. Настройки передаются через переменные окружения. 

## Использование в виде докер контейнера
Для примера представлен набор из Dockerfile, docker-compose манифеста и скрипта по настройке.

Склонировать репозиторий в нужное расположение
```sh
git clone https://github.com/rberzh/cec-incident-sender.git
```
Перейти в директорию incender_standalone
```sh
cd cec-incident-sender/incsender_standalone/
```
Выдать разрешения
```sh
chmod +x init.sh
```
Запустить init.sh
```sh
./init.sh
```

Заполнить предложенные мастером параметры.

Просмотреть журнал выполнения можно при помощи команды:
```sh
docker logs $(docker ps -qf name=incsender)
```
