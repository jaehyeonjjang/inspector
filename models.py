from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any
import uuid
import copy

def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

@dataclass
class BuildingInfo:
    name: str = ""
    address: str = ""
    location: str = ""
    memo: str = ""
    photos: List[str] = field(default_factory=list)


@dataclass
class SubPart:
    id: str
    name: str
    image_path: str
    # key: inspection_id (예: "2024-01", "2024-06")
    inspections: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class Part:
    id: str
    name: str
    subparts: List[SubPart] = field(default_factory=list)


@dataclass
class Project:
    id: str
    building: BuildingInfo = field(default_factory=BuildingInfo)
    parts: List[Part] = field(default_factory=list)

    @staticmethod
    def create_empty() -> "Project":
        return Project(id=new_id("proj"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Project":
        b = d.get("building", {}) or {}
        building = BuildingInfo(
            name=b.get("name", ""),
            address=b.get("address", ""),
            location=b.get("location", ""),
            memo=b.get("memo", ""),
            photos=list(b.get("photos", []) or []),
        )

        parts: List[Part] = []

        for p in (d.get("parts", []) or []):
            subparts: List[SubPart] = []

            # 신규 구조 (subparts 있음)
            if "subparts" in p:
                for sp in p.get("subparts", []):
                    subpart = SubPart(
                        id=sp.get("id", new_id("subpart")),
                        name=sp.get("name", ""),
                        image_path=sp.get("image_path", ""),
                        inspections=dict(sp.get("inspections", {}) or {}),
                    )

                    # 구버전: subpart 안에 defects가 있으면 DEFAULT로 이관
                    legacy_defects = sp.get("defects", None)
                    if legacy_defects is not None and not subpart.inspections:
                        subpart.inspections = {
                            "DEFAULT": {"defects": dict(legacy_defects or {})}
                        }

                    # 혹시 inspections 안에 defects 키가 없는 경우 보정
                    normalize_subpart_inspections(subpart)

                    subparts.append(subpart)
            else:
                # 더 구버전: part 자체가 도면/defects를 들고 있던 경우
                legacy_defects = dict(p.get("defects", {}) or {})
                subpart = SubPart(
                    id=new_id("subpart"),
                    name=p.get("name", ""),
                    image_path=p.get("image_path", ""),
                    inspections={"DEFAULT": {"defects": legacy_defects}},
                )
                normalize_subpart_inspections(subpart)
                subparts.append(subpart)

            parts.append(Part(
                id=p.get("id", new_id("part")),
                name=p.get("name", ""),
                subparts=subparts,
            ))

        return Project(
            id=d.get("id", new_id("proj")),
            building=building,
            parts=parts,
        )


# -----------------------
# Inspection helpers
# -----------------------

def normalize_subpart_inspections(sp: SubPart) -> None:
    """inspections 내부 형태를 최소 보장.
    inspections[key] = {"defects": {...}} 형태 유지
    """
    if sp.inspections is None:
        sp.inspections = {}

    for k, v in list(sp.inspections.items()):
        if v is None:
            sp.inspections[k] = {"defects": {}}
            continue
        if "defects" not in v:
            sp.inspections[k] = {"defects": dict(v or {})}
        else:
            sp.inspections[k]["defects"] = dict(sp.inspections[k].get("defects", {}) or {})


def ensure_inspection(sp: SubPart, key: str) -> None:
    if not sp.inspections:
        sp.inspections = {}
    if key not in sp.inspections:
        sp.inspections[key] = {"defects": {}}
    normalize_subpart_inspections(sp)


def list_inspections(sp: SubPart) -> List[str]:
    if not sp.inspections:
        return []
    return sorted(sp.inspections.keys())


def get_defects(sp: SubPart, key: str) -> Dict[str, Any]:
    ensure_inspection(sp, key)
    return sp.inspections[key]["defects"]


def set_defects(sp: SubPart, key: str, defects: Dict[str, Any]) -> None:
    ensure_inspection(sp, key)
    sp.inspections[key]["defects"] = dict(defects or {})


def copy_inspection(sp: SubPart, src: str, dst: str) -> None:
    ensure_inspection(sp, src)
    if dst in (sp.inspections or {}):
        raise ValueError(f"inspection already exists: {dst}")
    sp.inspections[dst] = copy.deepcopy(sp.inspections[src])
    normalize_subpart_inspections(sp)
