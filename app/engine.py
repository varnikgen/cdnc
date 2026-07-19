import hashlib
from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any

def deep_merge(base: Dict, override: Dict) -> Dict:
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

env = Environment(loader=FileSystemLoader("templates"))

def generate_cfg(mac: str, device: Dict, global_tpl: Dict, model_tpl: Dict, device_overrides: Dict) -> tuple[str, str]:
    merged = deep_merge(global_tpl, model_tpl)
    merged = deep_merge(merged, device_overrides or {})
    
    # Выбираем шаблон по модели
    model_prefix = device.get("model", "").upper()[:3]
    template_name = f"model_{model_prefix}.cfg.j2"
    
    try:
        tpl = env.get_template(template_name)
    except:
        tpl = env.get_template("global.cfg.j2")
    
    rendered = tpl.render(device=device, config=merged, mac=mac)
    cfg_hash = hashlib.sha256(rendered.encode()).hexdigest()
    return rendered, cfg_hash