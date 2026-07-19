from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession  # если нужно типизировать
from celery import Celery
import os
import logging
from datetime import datetime

from app.db import async_session_maker, Base, init_db  # ← ключевая строка
from app.models import Device, Template
from app.engine import generate_cfg

# Celery app (для worker'а)
celery_app = Celery(
    "yealink",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0")
)

app = FastAPI(title="Yealink Provisioner")

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/yealink/{mac}.cfg")
async def provision(mac: str, request: Request):
    logger = logging.getLogger("provisioner")
    
    mac_clean = mac.upper().replace(":", "").replace("-", "")
    if len(mac_clean) != 12 or not mac_clean.isalnum():
        raise HTTPException(400, detail="Invalid MAC format")

    try:
        # ✅ Используем импортированный async_session_maker
        async with async_session_maker() as db:
            result = await db.execute(
                Device.__table__.select().where(Device.mac == mac_clean)
            )
            device_row = result.first()
            
            if not device_row:
                return Response(
                    content=f"# Device {mac_clean} not registered\nauto_provisioning.enabled = 0\n",
                    media_type="text/plain",
                    status_code=404
                )
            
            # Преобразуем row в dict + merge с overrides
            device = dict(device_row._mapping)
            overrides = device.get("overrides") or {}
            device.update(overrides)  # "расплющиваем" overrides в корень устройства
            
            # Загружаем шаблоны
            global_result = await db.execute(
                Template.__table__.select().where(Template.scope == "global")
            )
            global_row = global_result.first()
            global_content = dict(global_row._mapping["content"]) if global_row else {}
            
            model_prefix = device.get("model", "")[:3].upper()
            model_scope = f"model:{model_prefix}x"
            
            model_result = await db.execute(
                Template.__table__.select().where(Template.scope == model_scope)
            )
            model_row = model_result.first()
            model_content = dict(model_row._mapping["content"]) if model_row else {}
            
            # Рендерим конфиг
            cfg_text, cfg_hash = generate_cfg(
                mac_clean, device, global_content, model_content, {}
            )
            
            # Обновляем last_seen
            try:
                await db.execute(
                    Device.__table__.update()
                    .where(Device.mac == mac_clean)
                    .values(last_seen=datetime.utcnow())
                )
                await db.commit()
            except Exception as e:
                logger.warning(f"Failed to update last_seen for {mac_clean}: {e}")
                await db.rollback()
            
            # ETag
            if_none_match = request.headers.get("if-none-match")
            if if_none_match and if_none_match.strip('"') == cfg_hash:
                return Response(status_code=304)
            
            return Response(
                content=cfg_text,
                media_type="text/plain",
                headers={"ETag": f'"{cfg_hash}"'}
            )
            
    except Exception as e:
        import traceback
        logging.error(f"Provisioning error for {mac_clean}: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, detail=f"Internal server error: {str(e)}")

# Заглушка Celery task (можно расширить позже)
@celery_app.task
def send_action_uri(phone_ip: str, action: str):
    import httpx
    try:
        url = f"http://{phone_ip}/servlet?action={action}"
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        return {"status": "success", "url": url}
    except Exception as e:
        return {"status": "error", "error": str(e)}