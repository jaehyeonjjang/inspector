"""
report_exporter.py (HWP -> HWPX)

기존 버전은 win32com 으로 한글(HWP) 자동화를 사용했지만,
요구사항상 "한글 실행 없이" HWPX(=zip+XML)로 내보내도록 변경한다.

⚠️ 중요
- HWPX 스펙(OWPML)은 복잡하고, "최소 구성"을 직접 생성하면
  한글/한컴오피스에서 열리지 않을 수 있다.
- 따라서 **템플릿 기반**으로 생성하는 방식을 기본으로 한다.
  (한번만 한컴오피스에서 템플릿 .hwpx를 만들어 두면, 이후는 파이썬만으로 출력 가능)

템플릿 준비:
- 같은 폴더에 templates/visual_inspection_template.hwpx
- 같은 폴더에 templates/defect_drawing_template.hwpx

템플릿 안에는 아래 플레이스홀더 텍스트가 포함되어 있어야 한다.
(한컴오피스에서 임의 텍스트로 넣어두면 됨)

[visual_inspection_template.hwpx]
- __TITLE__                      : 문서 제목 자리
- __SUB_HEADER__                 : [901동 25층] 같은 헤더 자리
- __TABLE_JSON__                 : 표 데이터 자리(문서에서 보이지 않아도 됨)

[defect_drawing_template.hwpx]
- __TITLE__                      : 문서 제목 자리
- __SUB_HEADER__                 : 위치/층 정보 자리
- __IMAGE_PATH__                 : 삽입할 이미지 경로 자리(문서에서 보이지 않아도 됨)
  (실제 이미지는 본 코드가 "BinData"로 넣는 것이 아니라,
   템플릿의 그림 개체를 '링크 이미지'로 두고, 경로만 치환하는 방식으로 권장)

현재 구현은:
- 템플릿 zip(hwpx) 열기
- Contents/section0.xml 내부의 텍스트 노드에서 플레이스홀더를 찾아 치환
- 새 hwpx로 저장

다음 단계(원하시면 이어서 구현):
- 표를 템플릿의 "행 1개"를 복제해서 실제 표로 렌더링 (OWPML table 구조 파싱/복제)
- 도면 페이지에 다중 이미지/범례/페이지번호 스타일 반영
"""

from __future__ import annotations

import os
import json
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from models import SubPart, Part, Project  # fileciteturn0file1L1-L38


# -------------------------
# DTO helpers
# -------------------------

@dataclass
class DefectRow:
    no: int
    location: str
    member: str
    defect_type: str
    width_mm: float
    length_m: float
    count: int
    progress: str  # "O" / "X"
    note: str


def _pick_inspection_key(sub: SubPart) -> Optional[str]:
    """export_reports()가 inspection을 넘겨주지 않으므로,
    가장 최신(정렬상 마지막) inspection을 임의로 선택.
    - start_date가 있다면 start_date 기준 내림차순
    - 없으면 key 정렬
    """
    if not sub.inspections:
        return None

    items = list(sub.inspections.items())

    def sort_key(kv):
        _k, v = kv
        # 날짜 문자열 "yyyy-mm-dd" 형태면 그대로 비교 가능
        return v.get("start_date") or "", _k

    items.sort(key=sort_key)
    return items[-1][0]


def _extract_defect_rows(defects: Dict[str, Any]) -> List[DefectRow]:
    rows: List[DefectRow] = []

    # defects 는 {id: {...}} 형태를 기대 (FaultEditorDialog가 저장)
    # 키 이름은 프로젝트마다 다를 수 있으므로 최대한 유연하게 매핑
    i = 1
    for _id, d in (defects or {}).items():
        location = str(d.get("location", "") or d.get("부위", "") or "")
        member = str(d.get("member", "") or d.get("부재", "") or "")
        defect_type = str(d.get("type", "") or d.get("유형", "") or d.get("유형 및 형상", "") or "")
        width_mm = float(d.get("width_mm", d.get("폭(mm)", d.get("폭", 0.0))) or 0.0)
        length_m = float(d.get("length_m", d.get("길이(m)", d.get("길이", 0.0))) or 0.0)
        count = int(d.get("count", d.get("개소(EA)", d.get("개수", 1))) or 1)
        cause = str(d.get("cause", d.get("비고", "")) or "")
        progress = str(d.get("progress", d.get("진행", "X")) or "X")

        rows.append(
            DefectRow(
                no=i,
                location=location,
                member=member,
                defect_type=defect_type,
                width_mm=width_mm,
                length_m=length_m,
                count=count,
                progress=progress if progress in ("O", "X") else "X",
                note=cause,
            )
        )
        i += 1

    return rows


# -------------------------
# HWPX template engine
# -------------------------

class HwpxTemplateEngine:
    """HWPX(=zip) 템플릿을 열어 section0.xml의 텍스트 노드를 치환한다."""

    def __init__(self, template_path: str):
        self.template_path = template_path

    def render(self, out_path: str, replacements: Dict[str, str]) -> None:
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(
                f"HWPX 템플릿을 찾을 수 없습니다: {self.template_path}\n"
                "templates 폴더에 템플릿 hwpx를 준비하세요."
            )

        with zipfile.ZipFile(self.template_path, "r") as zin:
            with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)

                    if item.filename.lower().endswith("contents/section0.xml"):
                        data = self._replace_text_in_section0(data, replacements)

                    zout.writestr(item, data)

    def _replace_text_in_section0(self, xml_bytes: bytes, replacements: Dict[str, str]) -> bytes:
        # HWPX는 보통 UTF-8 XML
        root = ET.fromstring(xml_bytes)

        # 모든 텍스트 노드 순회하며 플레이스홀더 치환
        for elem in root.iter():
            if elem.text:
                for k, v in replacements.items():
                    if k in elem.text:
                        elem.text = elem.text.replace(k, v)
            if elem.tail:
                for k, v in replacements.items():
                    if k in elem.tail:
                        elem.tail = elem.tail.replace(k, v)

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# -------------------------
# Public API (keeps old name)
# -------------------------

class ReportExporter:
    """기존 HWP 기반 ReportExporter 대체.
    - export_visual_inspection(): "-육안조사결함현황.hwpx" 생성
    - export_defect_drawing(): "-하자도면.hwpx" 생성

    사용처: PartManagerDialog.export_reports() fileciteturn0file0L521-L556
    """

    def __init__(self, project: Project, part: Part, subpart: SubPart, project_path: str):
        self.project = project
        self.part = part
        self.sub = subpart
        self.base_path = project_path

        # 템플릿 기본 위치: report_exporter.py 기준 상대경로
        here = os.path.dirname(os.path.abspath(__file__))
        self.visual_template = os.path.join(here, "templates", "visual_inspection_template.hwpx")
        self.drawing_template = os.path.join(here, "templates", "defect_drawing_template.hwpx")

    def _base_filename(self) -> str:
        project_name = self.project.building.name or "프로젝트"
        part_name = self.part.name or "대분류"
        sub_name = self.sub.name or "소분류"
        return f"{project_name}-{part_name}-{sub_name}"

    # -------- exports --------

    def export_visual_inspection(self) -> str:
        insp_key = _pick_inspection_key(self.sub)
        defects = {}
        insp_name = ""
        if insp_key:
            info = self.sub.inspections.get(insp_key, {}) or {}
            defects = info.get("defects", {}) or {}
            insp_name = info.get("name", "") or insp_key

        rows = _extract_defect_rows(defects)

        # 표 렌더링(현재는 JSON 문자열로 템플릿에 매립 → 다음 단계에서 실제 표로 확장)
        table_payload = {
            "columns": ["번호", "부위", "부재", "유형 및 형상", "폭(mm)", "길이(m)", "개소(EA)", "진행(O/X)", "비고"],
            "rows": [
                {
                    "번호": r.no,
                    "부위": r.location,
                    "부재": r.member,
                    "유형 및 형상": r.defect_type,
                    "폭(mm)": r.width_mm,
                    "길이(m)": r.length_m,
                    "개소(EA)": r.count,
                    "진행(O/X)": r.progress,
                    "비고": r.note,
                }
                for r in rows
            ],
        }

        out_path = os.path.join(self.base_path, self._base_filename() + "-육안조사결함현황.hwpx")

        engine = HwpxTemplateEngine(self.visual_template)
        engine.render(
            out_path=out_path,
            replacements={
                "__TITLE__": "3.1.7 육안조사 결함 현황",
                "__SUB_HEADER__": f"[{self.part.name} {self.sub.name}] ({insp_name})",
                "__TABLE_JSON__": json.dumps(table_payload, ensure_ascii=False, indent=2),
            },
        )
        return out_path

    def export_defect_drawing(self) -> str:
        out_path = os.path.join(self.base_path, self._base_filename() + "-하자도면.hwpx")

        engine = HwpxTemplateEngine(self.drawing_template)
        engine.render(
            out_path=out_path,
            replacements={
                "__TITLE__": "하자도면",
                "__SUB_HEADER__": f"[{self.part.name} {self.sub.name}]",
                "__IMAGE_PATH__": self.sub.image_path or "",
            },
        )
        return out_path
