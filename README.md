# 🐾 КУСЬ — Конфигуратор Устройств Сетевой Ь-связи
Внутренний сервис для автоматизации провижининга, централизованного управления конфигурациями и OTA-обновления прошивок IP-телефонов Yealink.
Разработан как модульное API-ядро, готовое к интеграции с FreePBX, встраиванию в админ-панель и масштабированию до 1000+ устройств.
## ✨ Возможности
| Функция | Описание |
| ------- | -------- |
| 🔄 Автопровижининг по HTTPS | Поддержка DHCP Option 166 / Zero Touch. Современные прошивки Yealink требуют TLS
| 🧩 Слоистая конфигурация | Наследование: Global → Model (T3x/T4x) → Device Overrides (JSONB)
| ⚡ Live-применение | config_replace = 0 + Action URI. Обновление параметров без разрыва активных звонков
| 📡 Фоновые задачи | Celery + Redis для отправки команд, проверки статусов, staged rollout прошивок
| 🔐 HTTPS-терминация | Nginx (Alpine) с поддержкой самоподписанных и корпоративных CA-сертификатов
| 🗄️ Гибкое хранение | PostgreSQL 15 + JSONB для динамических параметров. Asyncpg для высокой пропускной способности
| 🐳 Минимальный footprint | Полная контейнеризация (Podman/Docker), Alpine-образы, асинхронный стек
## 🏗 Архитектура
```
[Yealink Phone] ←HTTPS→ [Nginx] ←прокси→ [FastAPI API]
                                                    ↑
[Web UI (Vue/React)] ←REST→ [FastAPI API] ←очереди→ [Celery Worker]
                                                    ↑
[FreePBX Module (PHP)] ←REST→ [FastAPI API] ←→ [PostgreSQL] + [Redis]
```
* Ядро: Python 3.11 + FastAPI + Uvicorn
* БД: PostgreSQL 15 (asyncpg, JSONB)
* Очереди/Кэш: Redis 7 + Celery
* Прокси: Nginx (Alpine, TLS-терминация)
* Шаблоны: Jinja2 (наследуемые .cfg)
## 📦 Быстрый старт
### 1. Требования
* podman или docker + docker-compose / podman-compose
* git
* Сетевая доступность до телефонов (порт 443 для провижининга, порт 80 для Action URI)
### 2. Клонирование и подготовка
```bash
git clone https://github.com/varnikgen/cdnc.git
cd kuss-provisioner

# 1. Создайте .env (параметры подключения)
cp .env.example .env
nano .env

# 2. Сгенерируйте самоподписанные сертификаты
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -keyout certs/provision.key -out certs/provision.crt \
  -days 365 -nodes -subj "/CN=kuss.internal" \
  -addext "subjectAltName=DNS:kuss.internal,DNS:localhost,IP:127.0.0.1"
chmod 600 certs/provision.key
```
### 3. Запуск стека
```bash
podman compose up -d --build
```
### 4. Проверка
```bash
# Health check
curl -k https://localhost/health
# → {"status":"ok"}

# Тест провижининга (устройство не зарегистрировано → 404)
curl -k https://localhost/yealink/001122334455.cfg
```
### 5. Инициализация данных
```bash
podman exec -it kuss_db_1 psql -U prov -d yealand

-- Глобальный шаблон
INSERT INTO templates (id, name, scope, content) VALUES 
  (gen_random_uuid(), 'Global Base', 'global', 
   '{"provision_server_ip":"0.0.0.0/0","server_host":"kuss.internal","sip_server":"10.0.0.10"}');

-- Шаблон модели
INSERT INTO templates (id, name, scope, content) VALUES 
  (gen_random_uuid(), 'T4x Model', 'model:T4x', '{"vlan_enable":1,"vlan_id":100}');

-- Тестовое устройство
INSERT INTO devices (id, mac, model, overrides) VALUES 
  (gen_random_uuid(), '001122334455', 'T46S', 
   '{"extension":"101","display_name":"Test Phone","sip_password":"secure_pass_123","firmware_target":"96.86.0.15"}');
```
## 🌐 Настройка телефона Yealink
1. Откройте веб-интерфейс телефона → Auto Provisioning
2. Укажите:
    - Server URL: https://<IP_СЕРВЕРА_КУСЬ>/yealink/
    - Trust Certificate: Enabled (для самоподписанных сертификатов)
    - Config Replace: Disabled (обеспечивает live-применение)
3. Нажмите Reboot или отправьте команду через API:
```http
 POST /devices/{MAC}/apply
```
## 📂 Структура проекта
```
.
├── .env                # Переменные окружения (не коммитится)
├── .gitignore
├── certs/              # TLS-сертификаты (не коммитятся)
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
├── requirements.txt
├── README.md
├── app/
│   ├── main.py         # FastAPI роуты, инициализация БД
│   ├── db.py           # Async SQLAlchemy engine, session factory
│   ├── models.py       # ORM модели (Device, Template)
│   ├── engine.py       # Jinja2 render + deep_merge логики
│   └── tasks.py        # Celery задачи (Action URI, firmware)
└── templates/
    ├── global.cfg.j2   # Базовый шаблон
    ├── model_T3x.cfg.j2
    └── model_T4x.cfg.j2
```
## ⚙️ Конфигурация
**.env (пример)**
```ini
POSTGRES_USER=prov
POSTGRES_PASSWORD=provpass
POSTGRES_DB=yealink
DATABASE_URL=postgresql+asyncpg://prov:provpass@db:5432/yealand
REDIS_URL=redis://redis:6379/0
TZ=Europe/Moscow
```
### Важные нюансы
| Аспект | Решение в КУСЬ |
| ----- | ----- |
| asyncpg не понимает ?sslmode=disable | URL очищается от sslmode, SSL отключается через connect_args={"ssl": False}
| Наследование конфигов | deep_merge() → Jinja2 рендер → SHA256 ETag для кэширования (304 Not Modified)
| Тип JSON vs JSONB | Все поля overrides/content приведены к JSONB для нативного `
| Nginx upstream | Убран из server {} блока, используется прямой proxy_pass http://api:8000
## 🗺️ Планы
- 🖥️ Веб-интерфейс (Vue 3 / React) с таблицей устройств, редактором шаблонов, логами применения
- 🔄 Интеграция с FreePBX: синхронизация asterisk.pjsip/devices, вебхуки на изменения
- 📦 Firmware Manager: хранение .rom, staged rollout (1% → 5% → 50% → 100%), checksum verification
- 🔐 JWT/OAuth2 аутентификация между UI, FreePBX модулем и API-ядром
- 📊 Мониторинг: Prometheus metrics, Asterisk AMI для live-статуса регистрации SIP
- 🗄️ Alembic миграции вместо create_all(checkfirst=True)
## 🛠️ Разработка
```bash
# Запуск в режиме dev (autowatch)
podman compose -f docker-compose.yml -f docker-compose.dev.yml up

# Запуск тестов
pytest tests/ -v

# Сборка без кэша
podman compose build --no-cache
```
## 📜 Лицензия
Внутренний инструмент организации. Распространение и модификация только с согласия владельца.
> [!NOTE]
> 💡 Контекст для новых участников: проект собран на async-стеке Python, использует Podman для изоляции, Jinja2 для рендера конфигов Yealink и Celery для фоновых команд. Основные боли решены: SSL в asyncpg, ETag кэширование, JSONB мерж, Nginx proxy без upstream-ошибок.
