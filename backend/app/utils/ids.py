from __future__ import annotations


def normalize_parent_id(parent_id: str | None) -> str | None:
    if not parent_id:
        return None
    if parent_id.startswith('t1_') or parent_id.startswith('t3_'):
        return parent_id.split('_', 1)[1]
    return parent_id
