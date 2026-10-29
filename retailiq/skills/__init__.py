"""On-demand business instruction skills, not static product RAG documents."""
from pathlib import Path
from retailiq.observability import log_event

_ALLOWED = {'sales_kpi', 'inventory_availability', 'replenishment_review', 'product_grounding'}


def load_skill(name: str) -> str:
    """Explicit allowlist prevents user-supplied filesystem paths from being loaded."""
    if name not in _ALLOWED:
        raise ValueError(f'Unknown skill: {name}')
    content = (Path(__file__).parent / f'{name}.md').read_text(encoding='utf-8')
    log_event('skill.loaded', skill=name)
    return content


def skill_for(intent: str) -> str:
    return {'revenue': 'sales_kpi', 'top': 'sales_kpi',
            'stock': 'inventory_availability',
            'product': 'product_grounding',
            'decision': 'replenishment_review', 'general': '', 'latest': 'catalog_lookup'}[intent]
