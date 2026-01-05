from __future__ import annotations
import json
from pathlib import Path
from typing import Dict
from models import Project


def load_project(path: str) -> Project:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    proj = Project.from_dict(data)
    return proj


def save_project(project: Project, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(project.to_dict(), f, ensure_ascii=False, indent=2)


def load_index(index_path: str) -> Dict[str, str]:
    """id -> project_file_path"""
    p = Path(index_path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_index(index: Dict[str, str], index_path: str) -> None:
    p = Path(index_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
