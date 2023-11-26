# CEC Incidents sender
Скрипт для MaxPatrol 10 Custom Event Collector, отправляющий уведомления об инцидентах в Telegram/Mattermost/MS Teams.

## Список файлов
- incidents_sender.py - сам скрипт (код для добоавления в справочник)
- Incidents Sender.json - профиль для импорта в MaxPatrol 10

## Требования
MP10 Collector, на котором будет запущена задача должен иметь доступ к MaxPatrol 10 Core/MС по IP/FQDN (в зависимости от того как настроен MaxPatrol 10) по портам 443 и 3334, а так же к соответствующим серверам (Telegram, MS Teams, Mattermost).

## Использование
1. Создать справочник incidents_sender с кодом из .py файла
2. Импортировать профиль в систему (.json-файл) и настроить "Параметры запуска сценария", а так же "Интервал опроса модуля" (параметр в секундах, который отвечает за частоту запуска скрипта). [Как получить client_secret](https://help.ptsecurity.com/projects/maxpatrol10/26.1/ru-RU/help/3678991755)
3. Создать учетную запись типа Логин-пароль с учетной записью MaxPatrol 10, от имени которой будут запрашиваться инциденты
4. Создать задачу на основе созданного профиля, указав в качестве цели FQDN/IP (в зависимости от настройки MaxPatrol 10) сервера Core/MC/KB, а в качестве учетной записи созданную в п.3 УЗ.

## Параметры запуска сценария:
```
{
 "chat_id": "id_of_telegram_chat", # ID Telegram-чата куда бот будет высылать сообщения
 "client_secret": "mp10_secret", # client_secret MP10 Core.
 "gmt": 3, # Временная поправка, т.к. мы получаем время в GMT+0
 "minutes": 10, # Насколько мы смотрим "назад" при первом запуске, пока не сформирован savepoint
 "mm_enabled": true, # Включение отправки в Mattermost
 "mm_username": "", # Имя с которым будет отправлено сообщение в Mattermost 
 "mm_webhook_url": "mattermost_webhook_url", # Адрес вебхука для отправки в Mattermost (генерируется в Mattermost)
 "teams_enabled": true, # Включение отправки в MS Teams
 "teams_webhook_url": "teams_webhook_url", # Адрес вебхука для отправки в MS Teams (генерируется в MS Teams)
 "tg_enabled": true, # Включение отправки в Telegram
 "tg_token": "telegram_token" # Токен бота для отправки в Telegram
}
```

