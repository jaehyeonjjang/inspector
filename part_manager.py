from __future__ import annotations

from PyQt6.QtCore import Qt, QDate, QTimer
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QFileDialog, QMessageBox, QInputDialog,
    QDateEdit, QFormLayout, QLineEdit, QCheckBox,
    QSizePolicy
)

from models import Project, Part, SubPart, new_id
from models import get_defects, set_defects
import storage

from fault_editor import FaultEditorDialog

class InspectionCreateDialog(QDialog):
    def __init__(self, parent=None, title="점검 생성", default_name=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(360, 230)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setText(default_name)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate())

        self.end_enabled = QCheckBox("종료일 입력")
        self.end_enabled.setChecked(False)

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setEnabled(False)

        self.end_enabled.toggled.connect(self.end_date.setEnabled)

        form.addRow("검진 이름*", self.name_edit)
        form.addRow("검진 시작일*", self.start_date)
        form.addRow("검진 종료일", self.end_enabled)
        form.addRow("", self.end_date)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("확인")
        btn_cancel = QPushButton("취소")
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

    def get_data(self):
        name = self.name_edit.text().strip()
        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd") if self.end_enabled.isChecked() else None
        return {"name": name, "start_date": start, "end_date": end}

class PartManagerDialog(QDialog):
    TITLE_LABEL_STYLE = """
    QLabel {
        font-size: 14px;
        font-weight: 600;
        color: #333333;
    }
    """    
    TEXT_ONLY_STYLE = """
    QLabel {
        border: none;
        background: transparent;
        padding: 0px;
    }
    """
    def __init__(self, parent, project: Project, project_path: str):
        super().__init__(parent)
        self.setWindowTitle("파트 관리")
        self.resize(900, 600)

        self.project = project
        self.project_path = project_path

        root = QHBoxLayout(self)

        # -------- Left: Part list --------
        left = QVBoxLayout()

        self.part_list = QListWidget()  # 대분류

        # 타이틀 + 프린터 아이콘 (한 번만 생성)
        self.lbl_major_title = QLabel("대분류(동) 목록")
        self.lbl_major_title.setStyleSheet(self.TITLE_LABEL_STYLE)
        self.lbl_major_title.setFixedHeight(28)

        self.btn_print_report = QPushButton("🖨")
        self.btn_print_report.setToolTip("보고서 출력")
        self.btn_print_report.setFixedSize(28, 28)
        self.btn_print_report.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_print_report.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        major_title_row = QHBoxLayout()
        major_title_row.setContentsMargins(0, 0, 0, 0)
        major_title_row.setSpacing(6)
        major_title_row.addWidget(self.lbl_major_title, alignment=Qt.AlignmentFlag.AlignVCenter)
        major_title_row.addStretch(1)
        major_title_row.addWidget(self.btn_print_report, alignment=Qt.AlignmentFlag.AlignVCenter)

        left.addLayout(major_title_row)
        left.addWidget(self.part_list, 1)   # 리스트는 여기 1번만
        
        self.subpart_list = QListWidget()  # 소분류
        mid = QVBoxLayout()
        self.lbl_sub_title = QLabel("소분류(층/구간) 목록")
        self.lbl_sub_title.setStyleSheet(self.TITLE_LABEL_STYLE)
        self.lbl_sub_title.setFixedHeight(28)
        mid.addWidget(self.lbl_sub_title)
        mid.addWidget(self.subpart_list, 1)

        sub_btn_row = QHBoxLayout()
        self.btn_add_sub = QPushButton("소분류 추가")
        self.btn_rename_sub = QPushButton("이름 변경")
        self.btn_delete_sub = QPushButton("삭제")
        sub_btn_row.addWidget(self.btn_add_sub)
        sub_btn_row.addWidget(self.btn_rename_sub)
        sub_btn_row.addWidget(self.btn_delete_sub)
        mid.addLayout(sub_btn_row)

        root.addLayout(left, 2)
        root.addLayout(mid, 2)      
        
        self.inspection_list = QListWidget()
        self.lbl_insp_title = QLabel("점검(inspection) 목록")
        self.lbl_insp_title.setStyleSheet(self.TITLE_LABEL_STYLE)

        self.btn_add_insp = QPushButton("점검 생성")
        self.btn_copy_insp = QPushButton("점검 복사")
        self.btn_edit_insp = QPushButton("점검 수정")
        self.btn_delete_insp = QPushButton("점검 삭제")     
        
        insp_btn_row = QHBoxLayout()
        insp_btn_row.addWidget(self.btn_add_insp)
        insp_btn_row.addWidget(self.btn_copy_insp)
        insp_btn_row.addWidget(self.btn_edit_insp)
        insp_btn_row.addWidget(self.btn_delete_insp)
        
        mid.addWidget(self.lbl_insp_title)
        mid.addWidget(self.inspection_list, 1)
        mid.addLayout(insp_btn_row)
        
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("파트 추가")
        self.btn_rename = QPushButton("이름 변경")
        self.btn_delete = QPushButton("삭제")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_rename)
        btn_row.addWidget(self.btn_delete)
        left.addLayout(btn_row)

        # -------- Right: Part info --------
        right = QVBoxLayout()

        self.lbl_part_title = QLabel("선택 파트 정보")
        self.lbl_part_title.setStyleSheet(self.TITLE_LABEL_STYLE)
        right.addWidget(self.lbl_part_title)

        # ===== 기본정보 섹션 =====
        self.part_info_widget = QWidget()
        part_info_outer = QVBoxLayout(self.part_info_widget)
        part_info_outer.setContentsMargins(0, 0, 0, 0)
        part_info_outer.setSpacing(6)

        self.lbl_basic_title = QLabel("기본정보")
        self.lbl_basic_title.setStyleSheet("font-weight: 700;")

        # 네모 박스
        self.part_info_box = QWidget()
        self.part_info_box.setStyleSheet("""
        QWidget {
            border: 1px solid #C8C8C8;
            border-radius: 4px;
            background-color: #FAFAFA;
        }
        """)

        box_layout = QVBoxLayout(self.part_info_box)
        box_layout.setContentsMargins(8, 8, 8, 8)
        box_layout.setSpacing(6)

        self.lbl_part_major = QLabel("")
        self.lbl_part_minor = QLabel("")
        self.lbl_part_image = QLabel("")

        self.lbl_part_major.setStyleSheet(self.TEXT_ONLY_STYLE)
        self.lbl_part_minor.setStyleSheet(self.TEXT_ONLY_STYLE)
        self.lbl_part_image.setStyleSheet(self.TEXT_ONLY_STYLE)

        box_layout.addWidget(self.lbl_part_major)
        box_layout.addWidget(self.lbl_part_minor)
        box_layout.addWidget(self.lbl_part_image)

        part_info_outer.addWidget(self.lbl_basic_title)
        part_info_outer.addWidget(self.part_info_box)

        right.addWidget(self.part_info_widget)
        
        # ===== 점검정보 섹션 =====
        self.insp_info_widget = QWidget()
        insp_outer = QVBoxLayout(self.insp_info_widget)
        insp_outer.setContentsMargins(0, 0, 0, 0)
        insp_outer.setSpacing(6)

        self.lbl_insp_info_title = QLabel("점검정보")
        self.lbl_insp_info_title.setStyleSheet("font-weight: 700;")

        self.insp_info_box = QWidget()
        self.insp_info_box.setStyleSheet("""
        QWidget {
            border: 1px solid #C8C8C8;
            border-radius: 4px;
            background-color: #FAFAFA;
        }
        """)
        insp_box_layout = QVBoxLayout(self.insp_info_box)
        insp_box_layout.setContentsMargins(8, 8, 8, 8)
        insp_box_layout.setSpacing(6)

        self.lbl_insp_name = QLabel("")
        self.lbl_insp_start = QLabel("")
        self.lbl_insp_end = QLabel("")

        for w in (self.lbl_insp_name, self.lbl_insp_start, self.lbl_insp_end):
            w.setStyleSheet(self.TEXT_ONLY_STYLE)
            insp_box_layout.addWidget(w)

        insp_outer.addWidget(self.lbl_insp_info_title)
        insp_outer.addWidget(self.insp_info_box)
        right.addWidget(self.insp_info_widget)

        self.insp_info_widget.hide()        

        right.addStretch(1)

        self.btn_edit_defects = QPushButton("하자 편집")
        self.btn_edit_defects.setEnabled(False)
        right.addWidget(self.btn_edit_defects)

        root.addLayout(right, 3)

        # 초기에는 숨김
        self.part_info_widget.hide()

        # signals
        self.btn_add.clicked.connect(self.add_part)
        self.btn_rename.clicked.connect(self.rename_part)
        self.btn_delete.clicked.connect(self.delete_part)
        self.btn_edit_defects.clicked.connect(self.edit_defects)
        self.btn_print_report.clicked.connect(self.export_reports)
        self.part_list.itemSelectionChanged.connect(self._on_part_selected)
        self.subpart_list.itemSelectionChanged.connect(self._on_subpart_selected)

        self.btn_add_sub.clicked.connect(self.add_subpart)
        self.btn_rename_sub.clicked.connect(self.rename_subpart)
        self.btn_delete_sub.clicked.connect(self.delete_subpart)
        
        self.inspection_list.itemSelectionChanged.connect(self._on_inspection_selected)
        self.btn_add_insp.clicked.connect(self.add_inspection)
        self.btn_copy_insp.clicked.connect(self.copy_inspection)
        self.btn_edit_insp.clicked.connect(self.edit_inspection)
        self.btn_delete_insp.clicked.connect(self.delete_inspection)
                
        self._refresh_part_list()
        self._set_buttons()
        
        ACTION_BTNS = [
            self.btn_add,
            self.btn_rename,
            self.btn_delete,
            self.btn_add_sub,
            self.btn_rename_sub,
            self.btn_delete_sub,
            self.btn_add_insp,
            self.btn_copy_insp,
            self.btn_edit_insp,
            self.btn_delete_insp,
            self.btn_edit_defects,
        ]

        for btn in ACTION_BTNS:
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
        QTimer.singleShot(0, self._init_focus)

    def _init_focus(self):
        if self.part_list.count() > 0:
            self.part_list.setCurrentRow(0)   # ⭐ 핵심
            self.part_list.setFocus()
        else:
            self.btn_add.setFocus()
        
    # ---------- helpers ----------
    def _selected_part(self) -> Part | None:
        items = self.part_list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _selected_subpart(self) -> SubPart | None:
        items = self.subpart_list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)
    
    def _refresh_part_list(self):
        self.part_list.clear()
        for p in self.project.parts:
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.part_list.addItem(item)

    def _on_part_selected(self):
        part = self._selected_part()
        self.subpart_list.clear()

        # 파트 바뀌면 점검 UI도 먼저 초기화
        self.inspection_list.clear()
        self.insp_info_widget.hide()
        self.btn_edit_defects.setEnabled(False)

        if not part:
            self._set_buttons()
            return

        for sp in part.subparts:
            item = QListWidgetItem(sp.name)
            item.setData(Qt.ItemDataRole.UserRole, sp)
            self.subpart_list.addItem(item)

        self._set_buttons()
            
    def _on_subpart_selected(self):
        part = self._selected_part()
        sub = self._selected_subpart()

        if part and sub:
            self._update_part_info(part, sub)
        else:
            self.part_info_widget.hide()

        if sub:
            self._refresh_inspection_list(sub)
            self.insp_info_widget.hide()
        else:
            self.inspection_list.clear()
            self.insp_info_widget.hide()

        self._set_buttons()
           
    def _on_inspection_selected(self):
        sp = self._selected_subpart()
        insp_id = self._selected_inspection()

        if not sp or not insp_id:
            self.insp_info_widget.hide()
            self._set_buttons()
            return

        info = sp.inspections.get(insp_id)
        if not info:
            self.insp_info_widget.hide()
            self._set_buttons()
            return

        self.lbl_insp_name.setText(f"검진명: {info.get('name','')}")
        self.lbl_insp_start.setText(f"시작일: {info.get('start_date','')}")
        self.lbl_insp_end.setText(f"종료일: {info.get('end_date') or '-'}")

        self.insp_info_widget.show()
        self._set_buttons()
           
    def _set_buttons(self):
        has_part = self._selected_part() is not None
        has_sub = self._selected_subpart() is not None
        has_insp = self._selected_inspection() is not None

        self.btn_rename.setEnabled(has_part)
        self.btn_delete.setEnabled(has_part)

        self.btn_rename_sub.setEnabled(has_sub)
        self.btn_delete_sub.setEnabled(has_sub)

        self.btn_add_insp.setEnabled(has_sub)
        self.btn_copy_insp.setEnabled(has_sub and has_insp)
        self.btn_edit_insp.setEnabled(has_sub and has_insp)
        self.btn_delete_insp.setEnabled(has_sub and has_insp)
        
        self.btn_edit_defects.setEnabled(has_sub and has_insp)

    def _save_project(self):
        storage.save_project(self.project, self.project_path)

    # ---------- actions ----------
    def add_part(self):
        name, ok = QInputDialog.getText(self, "대분류 추가", "대분류 이름")
        if not ok or not name.strip():
            return

        part = Part(
            id=new_id("part"),
            name=name.strip(),
            subparts=[]
        )
        self.project.parts.append(part)
        self._save_project()
        self._refresh_part_list()

    def rename_part(self):
        p = self._selected_part()
        if not p:
            return

        name, ok = QInputDialog.getText(
            self, "이름 변경", "새 파트 이름", text=p.name
        )
        if not ok or not name.strip():
            return

        p.name = name.strip()
        self._save_project()
        self._refresh_part_list()

    def delete_part(self):
        p = self._selected_part()
        if not p:
            return

        ok = QMessageBox.question(
            self, "삭제 확인",
            f"파트 '{p.name}' 를 삭제할까요?\n(하자 정보도 함께 삭제됩니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ok != QMessageBox.StandardButton.Yes:
            return

        self.project.parts = [x for x in self.project.parts if x.id != p.id]
        self._save_project()
        self._refresh_part_list()
        self.subpart_list.clear()
        self.btn_edit_defects.setEnabled(False)

    def add_subpart(self):
        part = self._selected_part()
        if not part:
            QMessageBox.warning(self, "알림", "대분류를 먼저 선택하세요.")
            return

        name, ok = QInputDialog.getText(self, "소분류 추가", "소분류 이름")
        if not ok or not name.strip():
            return

        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "도면 이미지 선택",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        if not image_path:
            return

        sub = SubPart(
            id=new_id("subpart"),
            name=name.strip(),
            image_path=image_path,
            inspections={}
        )

        part.subparts.append(sub)
        self._save_project()
        self._on_part_selected()   # 소분류 리스트 갱신
        
    def rename_subpart(self):
        sp = self._selected_subpart()
        if not sp:
            return

        name, ok = QInputDialog.getText(
            self,
            "소분류 이름 변경",
            "새 소분류 이름",
            text=sp.name
        )
        if not ok or not name.strip():
            return

        sp.name = name.strip()
        self._save_project()
        self._on_part_selected()
        
    def delete_subpart(self):
        part = self._selected_part()
        sp = self._selected_subpart()
        if not part or not sp:
            return

        ok = QMessageBox.question(
            self,
            "삭제 확인",
            f"소분류 '{sp.name}'를 삭제할까요?\n(하자 정보도 함께 삭제됩니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ok != QMessageBox.StandardButton.Yes:
            return

        part.subparts = [x for x in part.subparts if x.id != sp.id]
        self._save_project()      
        self._on_part_selected()
        self._set_buttons()
        
    def _update_part_info(self, part: Part, subpart: SubPart):
        self.lbl_part_major.setText(f"대분류: {part.name}")
        self.lbl_part_minor.setText(f"소분류: {subpart.name}")
        self.lbl_part_image.setText(f"도면: {subpart.image_path}")

        self.part_info_widget.show()
        
    def _selected_inspection(self) -> str | None:
        items = self.inspection_list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)
        
    def add_inspection(self):
        sp = self._selected_subpart()
        if not sp:
            return

        dlg = InspectionCreateDialog(self, title="점검 생성")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        if not data["name"] or not data["start_date"]:
            QMessageBox.warning(self, "입력 오류", "검진 이름과 시작일은 필수입니다.")
            return

        insp_id = new_id("insp")
        sp.inspections[insp_id] = {
            "name": data["name"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "defects": {}
        }

        self._save_project()
        self._refresh_inspection_list(sp)

        # 생성된 점검 자동 선택
        for i in range(self.inspection_list.count()):
            if self.inspection_list.item(i).data(Qt.ItemDataRole.UserRole) == insp_id:
                self.inspection_list.setCurrentRow(i)
                break
        
    def copy_inspection(self):
        sp = self._selected_subpart()
        src = self._selected_inspection()
        if not sp or not src:
            return

        dlg = InspectionCreateDialog(self, title="점검 복사(신규 생성)")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        if not data["name"] or not data["start_date"]:
            QMessageBox.warning(self, "입력 오류", "검진 이름과 시작일은 필수입니다.")
            return

        new_id_ = new_id("insp")
        sp.inspections[new_id_] = {
            "name": data["name"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "defects": dict(sp.inspections[src].get("defects", {}))
        }

        self._save_project()
        self._refresh_inspection_list(sp)

        for i in range(self.inspection_list.count()):
            if self.inspection_list.item(i).data(Qt.ItemDataRole.UserRole) == new_id_:
                self.inspection_list.setCurrentRow(i)
                break
    def edit_inspection(self):
        sp = self._selected_subpart()
        insp_id = self._selected_inspection()
        if not sp or not insp_id:
            return

        info = sp.inspections.get(insp_id)
        if not info:
            return

        dlg = InspectionCreateDialog(
            self,
            title="점검 수정",
            default_name=info.get("name", "")
        )

        dlg.start_date.setDate(QDate.fromString(info["start_date"], "yyyy-MM-dd"))

        if info.get("end_date"):
            dlg.end_enabled.setChecked(True)
            dlg.end_date.setDate(QDate.fromString(info["end_date"], "yyyy-MM-dd"))

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        if not data["name"] or not data["start_date"]:
            QMessageBox.warning(self, "입력 오류", "검진 이름과 시작일은 필수입니다.")
            return

        info["name"] = data["name"]
        info["start_date"] = data["start_date"]
        info["end_date"] = data["end_date"]

        self._save_project()
        self._refresh_inspection_list(sp)

        # 수정 후 다시 선택 유지
        for i in range(self.inspection_list.count()):
            if self.inspection_list.item(i).data(Qt.ItemDataRole.UserRole) == insp_id:
                self.inspection_list.setCurrentRow(i)
                break
                
    def delete_inspection(self):
        sp = self._selected_subpart()
        insp_id = self._selected_inspection()
        if not sp or not insp_id:
            return

        info = sp.inspections.get(insp_id)
        if not info:
            return

        ret = QMessageBox.question(
            self,
            "점검 삭제",
            f"점검 '{info['name']}'을(를) 삭제하시겠습니까?\n"
            "이 점검에 포함된 모든 하자 정보가 함께 삭제됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if ret != QMessageBox.StandardButton.Yes:
            return

        del sp.inspections[insp_id]

        self._save_project()
        self._refresh_inspection_list(sp)
        self.insp_info_widget.hide()

        if self.inspection_list.count() > 0:
            self.inspection_list.setCurrentRow(0)

        self._set_buttons()
        
    def edit_defects(self):
        sp = self._selected_subpart()
        insp = self._selected_inspection()

        if not sp or not insp:
            QMessageBox.warning(
                self,
                "점검 필요",
                "하자를 편집하려면 점검을 먼저 선택하세요."
            )
            return

        defects = sp.inspections[insp].get("defects", {})

        dlg = FaultEditorDialog(
            image_path=sp.image_path,
            defects=defects,
            parent=self
        )

        def on_save(new_defects):
            sp.inspections[insp]["defects"] = new_defects
            self._save_project()

        dlg.saveRequested.connect(on_save)
        dlg.exec()
                
    def _refresh_inspection_list(self, sp: SubPart):
        self.inspection_list.clear()
        
        for insp_id, info in sp.inspections.items():
            item = QListWidgetItem(info["name"])
            item.setData(Qt.ItemDataRole.UserRole, insp_id)
            self.inspection_list.addItem(item)

    def export_reports(self):
        part = self._selected_part()
        sub = self._selected_subpart()

        if not part or not sub:
            QMessageBox.warning(
                self,
                "선택 필요",
                "보고서를 출력하려면 대분류와 소분류를 선택하세요."
            )
            return

        from report_exporter_hwpx import ReportExporter

        exporter = ReportExporter(
            project=self.project,
            part=part,
            subpart=sub,
            project_path=self.project_path
        )

        exporter.export_visual_inspection()
        exporter.export_defect_drawing()

        QMessageBox.information(self, "완료", "보고서가 생성되었습니다.")
