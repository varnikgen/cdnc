from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os
from urllib.parse import urlparse, parse_qs, urlunparse

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://prov:provpass@db:5432/yealink")

# Парсим URL, чтобы убрать sslmode из query string (asyncpg его не понимает)
parsed = urlparse(DATABASE_URL)
query = parse_qs(parsed.query)
# Удаляем sslmode и ssl, если есть — будем задавать явно через connect_args
query.pop("sslmode", None)
query.pop("ssl", None)
# Собираем URL обратно без этих параметров
clean_url = urlunparse((
    parsed.scheme, parsed.netloc, parsed.path,
    parsed.params, "&".join(f"{k}={v[0]}" for k, v in query.items()), parsed.fragment
))

engine = create_async_engine(
    clean_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": False}  # Явно отключаем SSL для asyncpg
)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        # checkfirst=True проверяет существование таблиц перед созданием
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)