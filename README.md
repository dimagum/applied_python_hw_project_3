# API-сервис сокращения ссылок

Данный проект представляет собой RESTful API сервис для сокращения ссылок, написанный на FastAPI. Сервис позволяет генерировать короткие ссылки.

## API (описание)

Сервис предоставляет следующие основные эндпоинты:

### Авторизация
- `POST /register` — регистрация нового пользователя.
- `POST /token` — получение JWT-токена для авторизации.

### Работа со ссылками
- `POST /links/shorten` — создание короткой ссылки (можно передать `custom_alias` и `expires_at`).
- `GET /{short_code}` — перенаправление на оригинальный URL.
- `GET /links/search?original_url={url}` — поиск коротких ссылок по оригинальному URL.
- `GET /links/{short_code}/stats` — получение статистики по короткой ссылке (клики, дата создания и последнего перехода).
- `PUT /links/{short_code}` — изменение оригинального URL у существующей короткой ссылки (требуется авторизация).
- `DELETE /links/{short_code}` — удаление короткой ссылки (требуется авторизация).

### Дополнительные функции (Admin/Extra)
- `DELETE /admin/cleanup` — удаление старых неиспользуемых ссылок (по умолчанию старше 30 дней).
- `GET /links/history/expired` — просмотр списка всех истекших ссылок.

Подробная интерактивная документация (Swagger UI) доступна по адресу `http://localhost:8000/docs` после запуска сервиса.

---

## Примеры запросов

### 1. Создание короткой ссылки
Запрос (cURL):
```bash
curl -X 'POST' \
  'http://localhost:8000/links/shorten' \
  -H 'Content-Type: application/json' \
  -d '{
  "original_url": "https://fastapi.tiangolo.com/ru/",
  "custom_alias": "fastapidocs"
}'
```

```json
{
  "short_code": "fastapidocs",
  "original_url": "https://fastapi.tiangolo.com/ru/",
  "expires_at": null
}
```


### 2. Получение статистики по ссылке
Запрос (cURL):
```bash
curl -X 'GET' \
  'http://localhost:8000/links/fastapidocs/stats' \
  -H 'accept: application/json'

```

```json
{
  "original_url": "https://fastapi.tiangolo.com/ru/",
  "created_at": "2023-10-25T14:30:00.000",
  "clicks": 5,
  "last_clicked": "2023-10-25T15:00:00.000"
}
```


## Инструкция по запуску

### 1. Склонировать репозиторий
```bash
git clone https://github.com/dimagum/applied_python_hw_project_3.git
```

### 2. Запуск docker 
```bash
docker-compose up -d --build
```

### 3. Проверка
Тут надо открыть браузер и открыть: `http://localhost:8000/docs`

### 4. Остановка сервиса 
```bash
docker-compose down
```


## Описание БД

Проект использует две базы данных:

1. Основная база данных (SQLite / PostgreSQL):

    Используется для хранения данных пользователей (таблица users) и ссылок (таблица links).

    По умолчанию в проекте настроен SQLite (shortener.db) для легкого запуска без дополнительных настроек локально.

    В БД хранятся связи между short_code и original_url, статистика переходов и время жизни ссылок.

2. In-Memory база данных (Redis):

    Используется для кэширования частых перенаправлений (GET-запросов к коротким ссылкам).

    Когда пользователь переходит по ссылке, сервис сначала ищет оригинальный URL в Redis. Если его там нет, берет из основной БД и сохраняет в Redis на 5 минут.

    Также настроена очистка кэша Redis при удалении или изменении ссылки владельцем.



