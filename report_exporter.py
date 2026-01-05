import win32com.client
import win32clipboard
import os

class ReportExporter:
    def __init__(self, project, part, subpart, project_path):
        self.project = project
        self.part = part
        self.sub = subpart
        self.base_path = project_path

    def _base_filename(self):
        project_name = self.project.building.name or "프로젝트"
        part_name = self.part.name or "대분류"
        sub_name = self.sub.name or "소분류"
        return f"{project_name}-{part_name}-{sub_name}"

    def _create_hwp(self):
        hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
        hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")

        # 한글 창 안 보이게 (백그라운드 생성)
        try:
            hwp.XHwpWindows.Item(0).Visible = False
        except Exception:
            pass

        hwp.HAction.Run("FileNew")
        return hwp

    def _insert_text(self, hwp, text: str):
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text)
        win32clipboard.CloseClipboard()

        hwp.HAction.Run("Paste")
        
    def _save_hwp(self, hwp, path: str):
        ps = hwp.CreateSet("HFileSaveAs")
        ps.SetItem("FileName", path)
        ps.SetItem("Format", "HWP")

        try:
            hwp.HAction.Execute("FileSaveAs", ps)
        except Exception:
            # 한글 2020에서는
            # 저장 다이얼로그 이후 COM 예외가 정상적으로 발생함
            pass
    
    def export_visual_inspection(self):
        hwp = self._create_hwp()

        try:
            hwp.HAction.Run("MoveDocBegin")
            self._insert_text(hwp, "육안조사활동현황\n")

            path = os.path.join(
                self.base_path,
                self._base_filename() + "-육안조사활동현황.hwp"
            )

            self._save_hwp(hwp, path)

        finally:
            hwp.Quit()

    def export_defect_drawing(self):
        hwp = self._create_hwp()

        try:
            hwp.HAction.Run("MoveDocBegin")
            self._insert_text(hwp, "하자도면\n")
            self._write_defect_drawings(hwp)

            path = os.path.join(
                self.base_path,
                self._base_filename() + "-하자도면.hwp"
            )

            self._save_hwp(hwp, path)

        finally:
            hwp.Quit()

    def _write_visual_table(self, hwp):
        ps = hwp.CreateSet("HTableCreation")
        ps.SetItem("Rows", 12)
        ps.SetItem("Cols", 9)
        hwp.HAction.Execute("TableCreate", ps)

        headers = [
            "번호","부위","부재","유형 및 형상",
            "폭(mm)","길이(m)","개수","진행","비고"
        ]

        for i, text in enumerate(headers):
            hwp.PutFieldText(f"A1{i+1}", text)

    def _write_defect_drawings(self, hwp):
        hwp.HAction.Run("MoveDocBegin")

        ps = hwp.CreateSet("HInsertPicture")
        ps.SetItem("FileName", self.sub.image_path)
        hwp.HAction.Execute("InsertPicture", ps)


