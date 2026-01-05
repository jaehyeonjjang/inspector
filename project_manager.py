from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QTextEdit, QFileDialog
)

from models import Project
import storage

from part_manager import PartManagerDialog

APP_DIR = Path.home() / ".fault_app"
INDEX_PATH = str(APP_DIR / "projects_index.json")

class ProjectInfoDialog(QDialog):
    def __init__(self, parent=None, project: Project | None = None):
        super().__init__(parent)
        self.setWindowTitle("프로젝트 기본 정보")
        self.resize(520, 360)

        self._project = project or Project.create_empty()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ed_name = QLineEdit(self._project.building.name)
        self.ed_addr = QLineEdit(self._project.building.address)
        self.ed_loc = QLineEdit(self._project.building.location)
        self.ed_memo = QTextEdit(self._project.building.memo)

        form.addRow("건축물명", self.ed_name)
        form.addRow("주소", self.ed_addr)
        form.addRow("위치(지번/설명)", self.ed_loc)
        form.addRow("메모", self.ed_memo)

        layout.addLayout(form)

        btns = QHBoxLayout()
        self.btn_ok = QPushButton("저장")
        self.btn_cancel = QPushButton("취소")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)

        layout.addLayout(btns)

    def project(self) -> Project:
        p = self._project
        p.building.name = self.ed_name.text().strip()
        p.building.address = self.ed_addr.text().strip()
        p.building.location = self.ed_loc.text().strip()
        p.building.memo = self.ed_memo.toPlainText().strip()
        return p


class ProjectManagerWindow(QMainWindow):
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("프로젝트 관리")
        self.resize(900, 600)

        self.index = storage.load_index(INDEX_PATH)  # id -> file path
        self.projects: dict[str, Project] = {}       # id -> Project (lazy load)

        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)

        # 왼쪽: 리스트
        left = QVBoxLayout()
        self.listw = QListWidget()
        self.listw.itemSelectionChanged.connect(self._on_select)
        self.lbl_project_list_title = QLabel("프로젝트 목록")
        self.lbl_project_list_title.setStyleSheet(self.TITLE_LABEL_STYLE)
        left.addWidget(self.lbl_project_list_title)
        left.addWidget(self.listw, 1)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("새 프로젝트")
        self.btn_edit = QPushButton("기본정보 수정")
        self.btn_delete = QPushButton("삭제")
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_delete)
        left.addLayout(btn_row)

        io_row = QHBoxLayout()
        self.btn_import = QPushButton("불러오기(.json)")
        self.btn_export = QPushButton("다른 이름으로 저장")
        io_row.addWidget(self.btn_import)
        io_row.addWidget(self.btn_export)
        left.addLayout(io_row)

        main.addLayout(left, 2)

        # 오른쪽: 선택 프로젝트 정보
        right = QVBoxLayout()
        self.lbl_project_info_title = QLabel("선택 프로젝트 정보")
        self.lbl_project_info_title.setStyleSheet(self.TITLE_LABEL_STYLE)
        right.addWidget(self.lbl_project_info_title)

        # =========================
        # 기본정보 섹션
        # =========================
        self.basic_info_widget = QWidget()
        basic_outer = QVBoxLayout(self.basic_info_widget)
        basic_outer.setContentsMargins(0, 0, 0, 0)
        basic_outer.setSpacing(6)

        # 섹션 타이틀
        self.lbl_basic_title = QLabel("기본정보")
        self.lbl_basic_title.setStyleSheet("font-weight: 700;")

        # 네모 박스 컨테이너
        self.basic_box = QWidget()
        self.basic_box.setStyleSheet("""
        QWidget {
            border: 1px solid #C8C8C8;
            border-radius: 4px;
            background-color: #FAFAFA;
        }
        """)

        basic_box_layout = QVBoxLayout(self.basic_box)
        basic_box_layout.setContentsMargins(8, 8, 8, 8)
        basic_box_layout.setSpacing(4)

        self.lbl_name = QLabel("")
        self.lbl_addr = QLabel("")
        self.lbl_loc = QLabel("")
        self.lbl_name.setStyleSheet(self.TEXT_ONLY_STYLE)
        self.lbl_addr.setStyleSheet(self.TEXT_ONLY_STYLE)
        self.lbl_loc.setStyleSheet(self.TEXT_ONLY_STYLE)

        basic_box_layout.addWidget(self.lbl_name)
        basic_box_layout.addWidget(self.lbl_addr)
        basic_box_layout.addWidget(self.lbl_loc)

        basic_outer.addWidget(self.lbl_basic_title)
        basic_outer.addWidget(self.basic_box)

        # =========================
        # 메모 섹션
        # =========================
        self.memo_widget = QWidget()
        memo_outer = QVBoxLayout(self.memo_widget)
        memo_outer.setContentsMargins(0, 0, 0, 0)
        memo_outer.setSpacing(6)

        # 섹션 타이틀
        self.lbl_memo_title = QLabel("메모")
        self.lbl_memo_title.setStyleSheet("font-weight: 700;")

        # 네모 박스 컨테이너
        self.memo_box = QWidget()
        self.memo_box.setStyleSheet("""
        QWidget {
            border: 1px solid #C8C8C8;
            border-radius: 4px;
            background-color: #FFFFFF;
        }
        """)

        memo_box_layout = QVBoxLayout(self.memo_box)
        memo_box_layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_memo = QLabel("")
        self.lbl_memo.setWordWrap(True)
        self.lbl_memo.setStyleSheet(self.TEXT_ONLY_STYLE)

        memo_box_layout.addWidget(self.lbl_memo)

        memo_outer.addWidget(self.lbl_memo_title)
        memo_outer.addWidget(self.memo_box)

        # 파트 관리 버튼 먼저 생성
        self.btn_open_parts = QPushButton("파트 관리로 이동")
        self.btn_open_parts.setEnabled(False)

        right.addWidget(self.basic_info_widget)
        right.addWidget(self.memo_widget)
        right.addStretch(1)
        right.addWidget(self.btn_open_parts)

        main.addLayout(right, 3)

        # 초기 상태: 섹션 숨김
        self.basic_info_widget.hide()
        self.memo_widget.hide()

        # signals
        self.btn_new.clicked.connect(self.create_project)
        self.btn_edit.clicked.connect(self.edit_project)
        self.btn_delete.clicked.connect(self.delete_project)
        self.btn_import.clicked.connect(self.import_project_file)
        self.btn_export.clicked.connect(self.export_project_as)
        self.btn_open_parts.clicked.connect(self.open_part_manager_placeholder)

        self._refresh_list()
        self._set_buttons()

    # ---------- helpers ----------
    def _selected_project_id(self) -> str | None:
        items = self.listw.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _load_project_if_needed(self, pid: str) -> Project | None:
        if pid in self.projects:
            return self.projects[pid]
        path = self.index.get(pid)
        if not path:
            return None
        try:
            proj = storage.load_project(path)
            self.projects[pid] = proj
            return proj
        except Exception as e:
            QMessageBox.critical(self, "로드 실패", f"프로젝트 파일을 읽지 못했습니다.\n{path}\n\n{e}")
            return None

    def _default_project_path(self, pid: str) -> str:
        return str(APP_DIR / f"{pid}.json")

    def _refresh_list(self):
        self.listw.clear()
        for pid, path in self.index.items():
            proj = self._load_project_if_needed(pid)
            title = proj.building.name if proj and proj.building.name else "(이름 없음)"
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self.listw.addItem(item)

    def _on_select(self):
        pid = self._selected_project_id()
        self._show_project(pid)
        self._set_buttons()

    def _set_buttons(self):
        has_sel = self._selected_project_id() is not None
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)
        self.btn_export.setEnabled(has_sel)
        self.btn_open_parts.setEnabled(has_sel)

    def _show_project(self, pid: str | None):
        if not pid:
            self.basic_info_widget.hide()
            self.memo_widget.hide()
            return

        proj = self._load_project_if_needed(pid)
        if not proj:
            return

        b = proj.building

        # 기본정보
        self.lbl_name.setText(f"이름: {b.name or '(미입력)'}")
        self.lbl_addr.setText(f"주소: {b.address}")
        self.lbl_loc.setText(f"지번: {b.location}")
        self.basic_info_widget.show()

        # 메모
        memo = b.memo.strip()
        if memo:
            self.lbl_memo.setText(memo)
            self.memo_widget.show()
        else:
            self.memo_widget.hide()

    # ---------- actions ----------
    def create_project(self):
        dlg = ProjectInfoDialog(self, Project.create_empty())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        proj = dlg.project()
        # 최소 유효성
        if not proj.building.name:
            QMessageBox.warning(self, "입력 필요", "건축물명은 필수입니다.")
            return

        # 저장 경로 결정
        path = self._default_project_path(proj.id)
        storage.save_project(proj, path)

        self.index[proj.id] = path
        storage.save_index(self.index, INDEX_PATH)
        self.projects[proj.id] = proj

        self._refresh_list()
        # 방금 생성한 것 선택
        for i in range(self.listw.count()):
            if self.listw.item(i).data(Qt.ItemDataRole.UserRole) == proj.id:
                self.listw.setCurrentRow(i)
                break

    def edit_project(self):
        pid = self._selected_project_id()
        if not pid:
            return
        proj = self._load_project_if_needed(pid)
        if not proj:
            return

        dlg = ProjectInfoDialog(self, proj)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        proj = dlg.project()
        storage.save_project(proj, self.index[pid])
        self.projects[pid] = proj
        self._show_project(pid)

    def delete_project(self):
        pid = self._selected_project_id()
        if not pid:
            return
        path = self.index.get(pid, "")

        ok = QMessageBox.question(
            self, "삭제 확인",
            f"프로젝트를 삭제할까요?\n\nID: {pid}\n파일: {path}\n\n(파일도 함께 삭제됩니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ok != QMessageBox.StandardButton.Yes:
            return

        # 파일 삭제 시도
        try:
            if path and Path(path).exists():
                Path(path).unlink()
        except Exception:
            pass

        self.index.pop(pid, None)
        self.projects.pop(pid, None)
        storage.save_index(self.index, INDEX_PATH)

        self._refresh_list()
        self._show_project(None)
        self._set_buttons()

    def import_project_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "프로젝트 불러오기", "", "Project (*.json)")
        if not path:
            return
        try:
            proj = storage.load_project(path)
        except Exception as e:
            QMessageBox.critical(self, "불러오기 실패", str(e))
            return

        # 인덱스에 등록 (원본 경로 그대로 사용)
        self.index[proj.id] = path
        self.projects[proj.id] = proj
        storage.save_index(self.index, INDEX_PATH)
        self._refresh_list()

    def export_project_as(self):
        pid = self._selected_project_id()
        if not pid:
            return
        proj = self._load_project_if_needed(pid)
        if not proj:
            return
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", "", "Project (*.json)")
        if not path:
            return
        storage.save_project(proj, path)

    def open_part_manager_placeholder(self):
        pid = self._selected_project_id()
        if not pid:
            return
        proj = self._load_project_if_needed(pid)
        if not proj:
            return

        dlg = PartManagerDialog(
            self,
            project=proj,
            project_path=self.index[pid]
        )
        dlg.exec()

        # Part Manager에서 변경된 내용 반영
        self.projects[pid] = proj
        self._show_project(pid)
        
