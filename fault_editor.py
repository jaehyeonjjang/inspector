from __future__ import annotations

import math
from enum import Enum, auto

from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QLineF, QSize, QEvent, QTimer,
    pyqtSignal, QSignalBlocker, 
)
from PyQt6.QtGui import (
    QAction, QActionGroup,
    QPixmap, QPen, QBrush, 
    QPainterPath, QPainterPathStroker,
    QFont, QTransform,
    QPolygonF, QPainter, QIcon, QColor
)
from PyQt6.QtWidgets import (
    QStyle, QDialog, QFrame,
    QMenuBar, QMenu,
    QGraphicsObject, 
    QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsPixmapItem,
    QGraphicsEllipseItem, QGraphicsRectItem,
    QGraphicsPolygonItem, QGraphicsPathItem,
    QGraphicsTextItem, QGraphicsSimpleTextItem,
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox,   
    QListWidget, QListWidgetItem, 
    QLineEdit, QTextEdit, QCheckBox,
    QGraphicsLineItem
)

# =====================================================
# 편집 모드
# =====================================================
class EditMode(Enum):
    SELECT = auto()
    AREA_SELECT = auto()

# =====================================================
# 마우스 드래그 모드
# =====================================================
class DragMode(Enum):
    NONE = auto()
    CREATE = auto()
    MOVE = auto()
    MOVE_ANCHOR = auto()

# =====================================================
# 공통 베이스
# =====================================================
class BaseMarkMixin:
    def setup_flags(self):
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, False)
        self._attached_line = None

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # anchor는 scene 고정, 종점만 갱신
            if hasattr(self, "_update_attached_line_geometry"):
                self._update_attached_line_geometry()

        if hasattr(self, "_update_defect_label_pos"):
            self._update_defect_label_pos()

        return QGraphicsItem.itemChange(self, change, value)
        
    def _update_attached_line_geometry(self):
        anchor_scene = getattr(self, "_line_anchor_scene_pos", None)
        line = getattr(self, "_attached_line", None)
        if anchor_scene is None or line is None:
            return

        # 종점은 도형의 현재 중심(scenePos) 방향으로, 도형 외곽 교차점
        center_scene = self.scenePos()
        end_scene = self.ray_intersection_point(anchor_scene, center_scene) or center_scene

        # 항상 scene 좌표로 그린다 (로컬 변환 금지)
        line.setLine(QLineF(anchor_scene, end_scene))
        line.setOpacity(1.0)        

class DirtyMixin:
    def _mark_dirty(self):
        scene = self.scene()
        if not scene:
            return
        editor = getattr(scene, "_editor", None)
        if editor and hasattr(editor, "mark_dirty"):
            editor.mark_dirty()

class DefectLabelMixin:
    _defect_label: QGraphicsSimpleTextItem | None = None

    def enable_defect_label(self, text: str):
        if self._defect_label is not None:
            assert hasattr(self._defect_label, "set_text")
            self._defect_label.set_text(text)
            self._update_defect_label_pos()
            return

        label = DefectLabelItem(text, self)
        self._defect_label = label
        self._update_defect_label_pos()
        label.setZValue(10)
        label.setDefaultTextColor(Qt.GlobalColor.red)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )
        label.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)    
        
        self._update_defect_label_pos()       

    def _enable_label_edit(self):
        if self._defect_label:
            self._defect_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextEditorInteraction
            )
            self._defect_label.setFocus()

    def update_defect_label(self, text: str):
        if self._defect_label:
            assert hasattr(self._defect_label, "set_text"), \
                "Defect label must implement set_text()"
            self._defect_label.set_text(text)
            self._update_defect_label_pos()

    def disable_defect_label(self):
        if self._defect_label:
            self.scene().removeItem(self._defect_label)
            self._defect_label = None

    def _update_defect_label_pos(self):
        if not self._defect_label:
            return

        rect = self.boundingRect()
        if rect.isNull():
            return        
        label_rect = self._defect_label.boundingRect()

        MARGIN_X = 6
        MARGIN_Y = 2

        x = rect.right() + MARGIN_X
        y = rect.bottom() - label_rect.height() + MARGIN_Y
        self._defect_label.setPos(x, y)
        
class DefectLabelItem(QGraphicsTextItem):
    def __init__(self, text: str, owner_mark):
        super().__init__(text, owner_mark)
        self._owner = owner_mark
        self.setZValue(10)
        self.setDefaultTextColor(Qt.GlobalColor.red)
        font = QFont("Malgun Gothic", 14, QFont.Weight.Medium)
        self.setFont(font)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    # 안전한 텍스트 설정 API
    def set_text(self, text: str):
        self.setPlainText(text)

    def mouseDoubleClickEvent(self, event):
        # 텍스트 더블클릭 → 텍스트 편집만
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction
        )
        self.setFocus(Qt.FocusReason.MouseFocusReason)

        event.accept()   # 중요: 부모로 이벤트 전파 차단

    def focusOutEvent(self, event):
        # 편집 종료 → owner에 저장
        if hasattr(self._owner, "defect_info"):
            self._owner.defect_info["member"] = self.toPlainText()
        if hasattr(self._owner, "_mark_dirty"):
            self._owner._mark_dirty()

        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        super().focusOutEvent(event)        

class IdTextItem(QGraphicsSimpleTextItem):
    def set_text(self, text: str):
        self.setText(text)

class GeometryRayMixin:
    def _outline_segments_scene(self) -> list[QLineF]:
        segments: list[QLineF] = []

        if isinstance(self, QGraphicsPolygonItem):
            poly = self.polygon()
            scene_poly = self.mapToScene(poly)
            n = len(scene_poly)
            for i in range(n):
                segments.append(QLineF(scene_poly[i], scene_poly[(i + 1) % n]))
            return segments

        scene_path = self.mapToScene(self.shape())
        polys = scene_path.toSubpathPolygons()
        for poly in polys:
            n = len(poly)
            for i in range(n):
                segments.append(QLineF(poly[i], poly[(i + 1) % n]))
        return segments

    def ray_intersection_point(self, start_scene: QPointF, toward_scene: QPointF) -> QPointF | None:
        direction = toward_scene - start_scene
        if direction.manhattanLength() < 2:
            center_scene = self.mapToScene(self.boundingRect().center())
            direction = center_scene - start_scene

        length = math.hypot(direction.x(), direction.y())
        if length < 1e-6:
            return None

        direction /= length
        ray = QLineF(start_scene, start_scene + direction * 10000)

        candidates: list[QPointF] = []
        for edge in self._outline_segments_scene():
            itype, ip = ray.intersects(edge)
            if itype == QLineF.IntersectionType.BoundedIntersection:
                if QLineF(start_scene, ip).length() > 1e-6:
                    candidates.append(ip)

        if not candidates:
            return None

        return min(candidates, key=lambda p: QLineF(start_scene, p).length())
        
class AttachLineMixin:
    def begin_attach(self, scene, anchor_scene: QPointF):
        # 실선은 반드시 scene item
        line = QGraphicsLineItem(QLineF(anchor_scene, anchor_scene))
        line.setPen(QPen(Qt.GlobalColor.red, 2))
        line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        line.setZValue(-1)
        line.setOpacity(0.4)  # preview
        scene.addItem(line)

        self._attached_line = line
        self._line_anchor_scene_pos = QPointF(anchor_scene)
        return line

    def update_attach_preview(self, target_scene: QPointF):
        line = getattr(self, "_attached_line", None)
        anchor = getattr(self, "_line_anchor_scene_pos", None)
        if not line or anchor is None:
            return

        # drag 중에는 교차점 계산 없이 anchor → 마우스
        line.setLine(QLineF(anchor, target_scene))

    def _update_attached_line_geometry(self):
        line = getattr(self, "_attached_line", None)
        anchor = getattr(self, "_line_anchor_scene_pos", None)
        if not line or anchor is None:
            return

        center = self.scenePos()
        if hasattr(self, "ray_intersection_point"):
            end = self.ray_intersection_point(anchor, center) or center
        else:
            end = center

        line.setLine(QLineF(anchor, end))

    def confirm_attach(self, _end_scene_pos=None):
        # preview 종료 → 고정
        self._update_attached_line_geometry()
        if self._attached_line:
            self._attached_line.setOpacity(1.0)

    def cancel_attach(self, scene):
        line = getattr(self, "_attached_line", None)
        if line:
            scene.removeItem(line)
        self._attached_line = None
        self._line_anchor_scene_pos = None
                  
class SerializableMixin:
    def to_dict(self):
        d = {
            "type": self.__class__.__name__,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "scale": self.scale(),
            "rotation": self.rotation(),
        }

        line = getattr(self, "_attached_line", None)
        if line:
            l = line.line()
            d["line"] = {"p1": [l.p1().x(), l.p1().y()], "p2": [l.p2().x(), l.p2().y()]}

        for k in ("internal_id", "display_id", "defect_info"):
            if hasattr(self, k):
                d[k] = getattr(self, k)
        return d

    @classmethod
    def from_dict(cls, info: dict, scene, editor):
        raise NotImplementedError(
            f"{cls.__name__}.from_dict() must be overridden"
        )
                      
class MemoLine(QGraphicsLineItem):
    def __init__(self, p1, p2):
        super().__init__(QLineF(p1, p2))
        self.is_memo = True

        self._normal_pen = QPen(QColor(30, 144, 255), 2)
        self._selected_pen = QPen(QColor(255, 80, 80), 3)
        self._selected_pen.setStyle(Qt.PenStyle.DashLine)

        self.setPen(self._normal_pen)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def shape(self):
        """
        선택(hit-test) 영역을 시각적 선보다 넓게 만든다
        """
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())

        stroker = QPainterPathStroker()
        stroker.setWidth(10)  # ← 핵심 (픽셀 단위, 취향에 따라 8~12)
        return stroker.createStroke(path)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.setPen(self._selected_pen if value else self._normal_pen)
        return super().itemChange(change, value)

class MemoFreePath(QGraphicsPathItem):
    def __init__(self, start):
        super().__init__()
        self.is_memo = True

        self._normal_pen = QPen(QColor(30, 144, 255), 2)
        self._selected_pen = QPen(QColor(255, 80, 80), 3)
        self._selected_pen.setStyle(Qt.PenStyle.DashLine)

        self._path = QPainterPath(start)
        self.setPath(self._path)
        self.setPen(self._normal_pen)

        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def add_point(self, p):
        self._path.lineTo(p)
        self.setPath(self._path)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())
        
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.setPen(self._selected_pen if value else self._normal_pen)
        return super().itemChange(change, value)       
                              
# =====================================================
# 도형 정의
# =====================================================
class CircleMark(QGraphicsObject, BaseMarkMixin, SerializableMixin, AttachLineMixin, GeometryRayMixin, DefectLabelMixin, DirtyMixin):
    requestOpenDefectDetail = pyqtSignal(object)

    def __init__(self, center: QPointF, r=18):
        super().__init__()
        self._rect = QRectF(-r, -r, r * 2, r * 2)
        self.setup_flags()
        self.setPos(center)

        # pen 분리 (핵심)
        self._normal_pen = QPen(Qt.GlobalColor.red, 3)
        self._selected_pen = QPen(Qt.GlobalColor.red, 4)
        self._selected_pen.setStyle(Qt.PenStyle.DashLine)

        self._select_box_pen = QPen(Qt.GlobalColor.black, 0)  # width=0 => cosmetic pen(줌에도 일정)
        self._select_box_pen.setStyle(Qt.PenStyle.DashLine)

        self._pen = self._normal_pen
        self._brush = QBrush(Qt.BrushStyle.NoBrush)

        # ID 텍스트
        self._id_text_item = IdTextItem("", self)
        self._id_text_item.setBrush(QBrush(Qt.GlobalColor.red))
        self._id_text_item.setZValue(20)   # 원/실선보다 항상 위
        self._id_text_item.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )

    def paint(self, painter, option, widget=None):
        # 1) 원은 항상 동일하게 그린다 (선택 여부로 원 테두리 스타일을 바꾸지 않음)
        painter.setPen(self._pen)
        painter.setBrush(self._brush)
        painter.drawEllipse(self._rect)

        # 2) 선택 상태면, 다른 도형과 동일한 "점선 사각 선택 박스"를 boundingRect 기준으로 추가
        if option.state & QStyle.StateFlag.State_Selected:
            painter.save()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(self._select_box_pen)
            painter.drawRect(self.boundingRect())
            painter.restore()

    def boundingRect(self):
        return self._rect
      
    def set_circle_id(self, n: int):
        self.display_id = n
        self._id_text_item.set_text(str(n))

        font = QFont("Malgun Gothic", 10, QFont.Weight.Bold)
        self._id_text_item.setFont(font)

        # 중앙 정렬
        br = self._id_text_item.boundingRect()
        self._id_text_item.setPos(
            -br.width() / 2,
            -br.height() / 2
        )
        
    MIN_SCALE = 0.6
    MAX_SCALE = 2.5
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemScaleChange:
            s = value
            if s < self.MIN_SCALE:
                return self.MIN_SCALE
            if s > self.MAX_SCALE:
                return self.MAX_SCALE

        return super().itemChange(change, value)
            
    def mouseDoubleClickEvent(self, event):
        # 1️.텍스트 위라면 상세 패널 열지 않음
        if self._defect_label and self._defect_label.isUnderMouse():
            event.ignore()
            return

        # 2️.텍스트가 아닌 원 영역 → 상세정보 패널
        self._open_defect_detail_panel()
        event.accept()
        
    def _open_defect_detail_panel(self):
        self.requestOpenDefectDetail.emit(self)
        
    def _commit_label_edit(self):
        if self._defect_label:
            text = self._defect_label.toPlainText()
            self.defect_info["member"] = text
            self._defect_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.NoTextInteraction
            )
            self._mark_dirty()
               
    def to_dict(self):
        d = super().to_dict()
        br = self.boundingRect()
        d["radius"] = br.width() / 2
        return d
        
    @classmethod
    def from_dict(cls, info: dict, scene, editor):
        x = info.get("x", 0)
        y = info.get("y", 0)
        r = info.get("radius", 18)

        item = cls(QPointF(x, y), r=r)
        return item
               
class SquareMark(QGraphicsRectItem, BaseMarkMixin, SerializableMixin, DefectLabelMixin, DirtyMixin):
    def __init__(self, center: QPointF, size=36):
        super().__init__(-size/2, -size/2, size, size)
        self.setup_flags()
        self.setPos(center)
        self.setPen(QPen(Qt.GlobalColor.red, 2))
        self.setBrush(QBrush(Qt.GlobalColor.red))
       
    def to_dict(self):
        d = super().to_dict()
        d["size"] = self.rect().width()
        return d
        
    @classmethod
    def from_dict(cls, info: dict, scene, editor):
        x = info.get("x", 0)
        y = info.get("y", 0)
        size = info.get("size", 36)

        item = cls(QPointF(x, y), size=size)
        return item        
       
    def set_new_rect(self, rect):
        self.prepareGeometryChange()
        self.setRect(rect)
        self.update()
        self._mark_dirty()        

class TriangleMark(QGraphicsPolygonItem, BaseMarkMixin, SerializableMixin, DefectLabelMixin, DirtyMixin):
    def __init__(self, center: QPointF, size=40):
        h = size * math.sqrt(3) / 2
        polygon = QPolygonF([
            QPointF(0, -h/2),
            QPointF(-size/2, h/2),
            QPointF(size/2, h/2)
        ])
        super().__init__(polygon)
        self.setup_flags()
        self.setPos(center)
        self.setPen(QPen(Qt.GlobalColor.red, 2))
        self.setBrush(QBrush(Qt.GlobalColor.red))
        
    def to_dict(self):
        d = super().to_dict()
        d["size"] = self.boundingRect().width()
        return d
        
    @classmethod
    def from_dict(cls, info: dict, scene, editor):
        x = info.get("x", 0)
        y = info.get("y", 0)
        size = info.get("size", 40)

        item = cls(QPointF(x, y), size=size)
        return item
                 
class SCurveWithMidCircle(QGraphicsPathItem, BaseMarkMixin, SerializableMixin, DefectLabelMixin, DirtyMixin):
    def __init__(self, center: QPointF,
                 w=43, h=55, mid_r=8, curve=0.9):
        path = QPainterPath()

        top = -h / 2
        bottom = h / 2
        w2 = w / 2

        path.moveTo(0, top)
        path.cubicTo(
            -w2 * curve, top + h * 0.25,
             w2 * curve, top + h * 0.75,
             0, bottom
        )

        super().__init__(path)
        self.setup_flags()
        self.setPos(center)
        self.setPen(QPen(Qt.GlobalColor.red, 3))

        self.mid = QGraphicsEllipseItem(
            -mid_r, -mid_r, mid_r * 2, mid_r * 2, parent=self
        )
        self.mid.setPen(QPen(Qt.GlobalColor.red, 3))
        self.mid.setBrush(QBrush(Qt.GlobalColor.white))

           
    def to_dict(self):
        d = super().to_dict()
        d.update({
            "w": self.boundingRect().width(),
            "h": self.boundingRect().height()
        })
        return d
        
    @classmethod
    def from_dict(cls, info: dict, scene, editor):
        x = info.get("x", 0)
        y = info.get("y", 0)
        w = info.get("w", 43)
        h = info.get("h", 55)

        item = cls(QPointF(x, y), w=w, h=h)
        return item        
        
class NoteText(QGraphicsTextItem, BaseMarkMixin, SerializableMixin, DefectLabelMixin, DirtyMixin):
    def __init__(self, center: QPointF, text="하자"):
        super().__init__(text)
        
        # 텍스트 내용이 실제로 바뀔 때마다 호출
        self.document().contentsChanged.connect(
            self._on_text_contents_changed
        )
        
        self.setup_flags()
        self.setPos(center)
        self.setDefaultTextColor(Qt.GlobalColor.blue)
        self.setFont(QFont("Malgun Gothic", 12))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        
    def to_dict(self):
        d = super().to_dict()
        d["text"] = self.toPlainText()
        return d        

    @classmethod
    def from_dict(cls, info: dict, scene, editor):
        x = info.get("x", 0)
        y = info.get("y", 0)
        text = info.get("text", "")

        item = cls(QPointF(x, y), text=text)
        return item
        
    def mouseDoubleClickEvent(self, event):
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction
        )
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()
        
    def focusInEvent(self, event):
        scene = self.scene()
        dialog = getattr(scene, "_editor", None)
        editor = getattr(dialog, "editor", None) if dialog else None

        if editor:
            editor._begin_edit()

        super().focusInEvent(event)
           
    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        scene = self.scene()
        dialog = getattr(scene, "_editor", None)
        editor = getattr(dialog, "editor", None) if dialog else None

        if editor:
            editor._end_edit()

        super().focusOutEvent(event)

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)
        
    def _on_text_contents_changed(self):
        # geometry가 바뀔 수 있으므로
        self.prepareGeometryChange()

        # ID 라벨 위치 즉시 재계산
        self._update_defect_label_pos()

        # undo 대상 마킹 (너무 잦으면 DirtyMixin에서 내부 debounce 가능)
        self._mark_dirty()
                
# =====================================================
# View
# =====================================================
class PlanView(QGraphicsView):
    def __init__(self, owner):
        super().__init__(owner.scene)
        self.owner = owner
       
    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)

        # view 크기가 확정되는 타이밍에 맞추기
        if self.owner.bg_item and not getattr(self.owner, "_fitted", False):
            self.fitInView(self.owner.bg_item, Qt.AspectRatioMode.KeepAspectRatio)
            # 최초 fit scale 저장
            self.owner._base_view_scale = self.transform().m11()
            self.owner._current_view_scale = self.owner._base_view_scale
            self.owner._fitted = True
            
    def mousePressEvent(self, event):
        handled = self.owner._on_mouse_press(event)
        if handled:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 드래그 작업 중이면: 작업 종류에 따라 super 호출 여부 분기
        if self.owner._drag_mode == DragMode.MOVE_ANCHOR:
            self.owner._on_mouse_move(event)
            event.accept()
            return

        if self.owner._drag_mode == DragMode.CREATE:
            self.owner._on_mouse_move(event)
            return  # accept하지 않는다

        # MOVE는 Qt 기본 이동이 필요(press를 Qt에 넘겼다는 전제)
        super().mouseMoveEvent(event)
        if self.owner._drag_mode == DragMode.MOVE:
            self.owner._on_mouse_move(event)
            event.accept()
            return

        # 드래그 중 아니면 hover 처리
        self.owner._on_hover_move(event)

    def mouseReleaseEvent(self, event):
        handled = self.owner._on_mouse_release(event)
        if handled:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        handled = self.owner._on_mouse_double_click(event)
        if handled:
            event.accept()
            return

        # 중요: 아이템이 있으면 아이템에게 먼저 기회 준다
        item = self.itemAt(event.position().toPoint())
        if item:
            super().mouseDoubleClickEvent(event)
            return

        super().mouseDoubleClickEvent(event)
        
    def wheelEvent(self, event):
        delta = event.angleDelta().y()

        # Ctrl + 휠 : 선택 도형 확대/축소
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.1 if delta > 0 else 1 / 1.1

            items = self.scene().selectedItems()
            if not items:
                event.ignore()
                return

            # 편집 세션 시작 (한 번만)
            if not getattr(self.owner, "_editing", False):
                self.owner._begin_edit()

            for item in items:
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setScale(item.scale() * factor)

            # 연속 휠을 하나의 undo로 묶기
            self.owner._edit_end_timer.start(300)

            event.accept()
            return

        # Shift + 휠 : 화면 확대/축소
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.scale(factor, factor)
            self.owner._current_view_scale *= factor

            if hasattr(self.owner.parent(), "status_bar"):
                self.owner.parent().status_bar.set_zoom(
                    self.owner._current_view_scale / self.owner._base_view_scale
                )

            event.accept()
            return

        super().wheelEvent(event)

# =====================================================
# QFrame for editor of detail
# =====================================================
class DefectDetailPanel(QFrame):
    """
    하단 상세정보 입력 패널(모달 아님).
    CircleMark 더블클릭 시 표시되고, 입력 즉시 circle.defect_info에 반영한다.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._circle = None

        self.setFixedHeight(210)
        self.setStyleSheet("""
            QFrame {
                background: #F9F9F9;
                border-top: 1px solid #999;
            }
            QLabel { font-weight: 600; color: #333; }
            QLineEdit, QTextEdit {
                background: white;
                border: 1px solid #BBB;
                padding: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # --- Row1: 부재/부위 ---
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.member_edit = QLineEdit()
        self.member_edit.setPlaceholderText("예: 벽체")
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText("예: 계단실, EV기계실")

        row1.addWidget(QLabel("부재"))
        row1.addWidget(self.member_edit, 2)
        row1.addSpacing(12)
        row1.addWidget(QLabel("부위"))
        row1.addWidget(self.location_edit, 3)

        # --- Row2: 유형 + 폭/길이/개소 ---
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.type_edit = QLineEdit()
        self.type_edit.setPlaceholderText("예: 수직균열")

        self.width_edit = QLineEdit()
        self.width_edit.setPlaceholderText("mm")
        self.length_edit = QLineEdit()
        self.length_edit.setPlaceholderText("m")
        self.count_edit = QLineEdit()
        self.count_edit.setPlaceholderText("EA")

        row2.addWidget(QLabel("유형"))
        row2.addWidget(self.type_edit, 3)
        row2.addSpacing(12)
        row2.addWidget(QLabel("폭"))
        row2.addWidget(self.width_edit, 1)
        row2.addWidget(QLabel("길이"))
        row2.addWidget(self.length_edit, 1)
        row2.addWidget(QLabel("개소"))
        row2.addWidget(self.count_edit, 1)

        # --- Row3: 진행성 O/X ---
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.progress_check = QCheckBox("진행성 (O)")
        row3.addWidget(self.progress_check)
        row3.addStretch(1)

        # --- Remark ---
        self.remark_edit = QTextEdit()
        self.remark_edit.setFixedHeight(70)

        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addLayout(row3)
        layout.addWidget(QLabel("비고"))
        layout.addWidget(self.remark_edit)

        # 입력 즉시 반영
        self.member_edit.textChanged.connect(self._commit)
        self.location_edit.textChanged.connect(self._commit)
        self.type_edit.textChanged.connect(self._commit)
        self.width_edit.textChanged.connect(self._commit)
        self.length_edit.textChanged.connect(self._commit)
        self.count_edit.textChanged.connect(self._commit)
        self.progress_check.toggled.connect(self._commit)
        self.remark_edit.textChanged.connect(self._commit)

        self.hide()

    def show_for_circle(self, circle):
        self._circle = circle
        info = getattr(circle, "defect_info", {}) or {}

        blockers = [
            QSignalBlocker(self.member_edit),
            QSignalBlocker(self.location_edit),
            QSignalBlocker(self.type_edit),
            QSignalBlocker(self.width_edit),
            QSignalBlocker(self.length_edit),
            QSignalBlocker(self.count_edit),
            QSignalBlocker(self.progress_check),
            QSignalBlocker(self.remark_edit),
        ]

        self.member_edit.setText(info.get("member", ""))
        self.location_edit.setText(info.get("location", ""))

        self.type_edit.setText(info.get("defect_type", ""))

        size = info.get("size", {}) or {}
        self.width_edit.setText(size.get("width_mm", ""))
        self.length_edit.setText(size.get("length_m", ""))
        self.count_edit.setText(size.get("count_ea", ""))

        self.progress_check.setChecked(bool(info.get("progress", False)))
        self.remark_edit.setPlainText(info.get("remark", ""))

        # blockers 리스트를 scope에 유지해야 해서 그냥 둠(함수 끝날 때 해제됨)
        self.show()

        # UX: 처음 열릴 때 커서를 “가장 먼저 채워야 할 곳”으로
        if not self.member_edit.text().strip():
            self.member_edit.setFocus()
        elif not self.location_edit.text().strip():
            self.location_edit.setFocus()
        elif not self.type_edit.text().strip():
            self.type_edit.setFocus()

    def _commit(self):
        if not self._circle:
            return

        info = getattr(self._circle, "defect_info", None)
        if info is None:
            self._circle.defect_info = {}
            info = self._circle.defect_info

        info["member"] = self.member_edit.text()
        info["location"] = self.location_edit.text()
        info["defect_type"] = self.type_edit.text()

        info["size"] = {
            "width_mm": self.width_edit.text(),
            "length_m": self.length_edit.text(),
            "count_ea": self.count_edit.text(),
        }

        # 진행성: False = X(기본), True = O
        info["progress"] = self.progress_check.isChecked()
        info["remark"] = self.remark_edit.toPlainText()

        # 도면 옆 텍스트(부재)는 즉시 반영
        if hasattr(self._circle, "update_defect_label"):
            self._circle.update_defect_label(info["member"])

        if hasattr(self._circle, "_mark_dirty"):
            self._circle._mark_dirty()

# =====================================================
# Widget for editor (핵심 control)
# =====================================================
class FaultEditorWidget(QWidget):
    dirtyChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # ===== Undo / Redo =====
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._undo_block = False   # undo/redo 중 재기록 방지       

        self._baseline_snapshot: dict | None = None        
        
        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.view = PlanView(self)
        self.view.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        
        self.detail_panel = DefectDetailPanel(self)
        layout.addWidget(self.detail_panel)
        
        self._edit_mode = EditMode.SELECT
        self.current_tool = "circle"
        self.bg_item = None

        self._build_shape_panel()

        self._next_defect_index = 1
        
        self._fitted = False      
        self._press_pos = None
        self._drag_mode: DragMode = DragMode.NONE
        self._drag_item = None
        self._drag_line = None
        
        self._panel_dragging = False
        self._panel_drag_offset = QPointF()
              
        # ===== 도형 패널 드래그 최적화 =====
        self._panel_pending_pos = None
        self._panel_move_timer = QTimer(self)
        self._panel_move_timer.setSingleShot(True)
        self._panel_move_timer.timeout.connect(self._apply_pending_panel_move)
              
        self._press_timer = QTimer(self)
        self._press_timer.setSingleShot(True)
        self._press_timer.timeout.connect(self._begin_drag_create)

        self._pending_press_pos = None
        self._pressing = False               
        
        self._anchor_handle = QGraphicsEllipseItem(-4, -4, 8, 8)
        self._anchor_handle.setBrush(QBrush(Qt.GlobalColor.white))
        self._anchor_handle.setPen(QPen(Qt.GlobalColor.red, 2))
        self._anchor_handle.setZValue(999)
        self._anchor_handle.setVisible(False)
        self._anchor_handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._anchor_handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(self._anchor_handle)

        self._anchor_handle_target = None
        self._anchor_handle_radius_px = 10
        
        # ===== 연속 편집 묶기용 타이머 =====
        self._edit_end_timer = QTimer(self)
        self._edit_end_timer.setSingleShot(True)
        self._edit_end_timer.timeout.connect(self._end_edit)
        
        self.view.viewport().installEventFilter(self)
                     
    def _apply_pending_panel_move(self):
        if self._panel_pending_pos is None:
            return

        # 드래그 중 과도한 repaint 방지
        self.shape_panel.setUpdatesEnabled(False)
        self.shape_panel.move(self._panel_pending_pos)
        self.shape_panel.setUpdatesEnabled(True)

        self._panel_pending_pos = None
                     
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if not self.detail_panel.isHidden():
                # 클릭 위치 (FaultEditorWidget 좌표계)
                pos = event.position().toPoint()

                # 상세 패널 영역
                panel_rect = self.detail_panel.geometry()

                # 패널 바깥 클릭 → 닫기
                if not panel_rect.contains(pos):
                    self._hide_detail_panel()

        return super().eventFilter(obj, event)
                     
    def _hide_detail_panel(self):
        self.detail_panel._circle = None
        self.detail_panel.hide()

    def _show_detail_for_circle(self, circle: CircleMark):
        # 패널 표시 + 포커스/선택 상태를 일관되게
        if circle and not circle.isSelected():
            self.scene.clearSelection()
            circle.setSelected(True)
        self.detail_panel.show_for_circle(circle)

    def _on_scene_selection_changed(self):
        # 아무 것도 하지 않거나
        pass
                     
    def _on_open_defect_detail(self, circle):
        # 부모 위임 제거(또는 fallback만 남기기)
        self._show_detail_for_circle(circle)
        parent = self.parent()
        if parent and hasattr(parent, "_on_open_defect_detail"):
            parent._on_open_defect_detail(circle)
            
    def _safe_connect_open_detail(self, item: CircleMark):
        try:
            item.requestOpenDefectDetail.disconnect(self._on_open_defect_detail)
        except TypeError:
            pass
        item.requestOpenDefectDetail.connect(self._on_open_defect_detail)
                        
    def _begin_edit(self):
        if self._undo_block:
            return
        self._editing = True

    def _end_edit(self):
        if self._undo_block:
            return
        if not getattr(self, "_editing", False):
            return

        snapshot = self._make_snapshot()
        if not self._undo_stack or self._undo_stack[-1] != snapshot:
            self._undo_stack.append(snapshot)
            self._redo_stack.clear()

            # 핵심 추가
            parent = self.parent()
            if parent and hasattr(parent, "mark_dirty"):
                parent.mark_dirty()

        self._editing = False
        
    def _renumber_circle_ids(self):
        """
        현재 씬에 존재하는 CircleMark들의 ID를
        1부터 연속 번호로 재정렬한다.
        """
        circles = []

        for item in self.scene.items():
            if isinstance(item, CircleMark):
                if isinstance(item.display_id, int):
                    circles.append(item)

        # 기존 번호 순서대로 정렬
        circles.sort(key=lambda c: c.display_id)

        # 1부터 다시 부여
        for idx, circle in enumerate(circles, start=1):
            if circle.display_id != idx:
                circle.set_circle_id(idx)
                circle.display_id = idx
                       
    def _make_snapshot(self) -> dict:
        parent = self.parent()
        snap = parent.get_defects() if parent and hasattr(parent, "get_defects") else {"items": []}
        snap["__version__"] = 1

        # undo/redo 전용: memo만 별도 저장
        memos = []
        for it in self.scene.items():
            if isinstance(it, MemoLine):
                l = it.line()
                memos.append({
                    "type": "memo_line",
                    "p1": [l.p1().x(), l.p1().y()],
                    "p2": [l.p2().x(), l.p2().y()],
                })
            elif isinstance(it, MemoFreePath):
                path = it.path()
                pts = []
                for i in range(path.elementCount()):
                    e = path.elementAt(i)
                    pts.append([e.x, e.y])
                memos.append({
                    "type": "memo_free",
                    "pts": pts
                })

        snap["memos"] = memos
        return snap
        
    def _restore_snapshot(self, snapshot: dict):
        version = snapshot.get("__version__", 0)
        if version == 0:
            # legacy 데이터 (초기 버전)
            pass
        elif version == 1:
            pass
            
        self.open_png_from_path(snapshot.get("image", self.bg_path))

        for info in snapshot.get("items", []):
            self._restore_item(info)

        # memo 복원
        for m in snapshot.get("memos", []):
            if m.get("type") == "memo_line":
                p1 = QPointF(*m["p1"])
                p2 = QPointF(*m["p2"])
                self.scene.addItem(MemoLine(p1, p2))
            elif m.get("type") == "memo_free":
                pts = m.get("pts") or []
                if pts:
                    item = MemoFreePath(QPointF(*pts[0]))
                    for xy in pts[1:]:
                        item.add_point(QPointF(*xy))
                    self.scene.addItem(item)

        self._next_defect_index = self._calc_next_defect_index()
        
    def undo(self):
        # 기준 상태(최소 1개)는 남겨야 하므로 2개 이상일 때만 undo
        if len(self._undo_stack) < 2:
            return

        self._undo_block = True

        # 현재 상태를 redo로 이동
        current = self._undo_stack.pop()
        self._redo_stack.append(current)

        # 이전 상태 복원
        snapshot = self._undo_stack[-1]
        self._restore_snapshot(snapshot)

        self._undo_block = False
        self.mark_dirty()

    def redo(self):
        if not self._redo_stack:
            return

        self._undo_block = True

        snapshot = self._redo_stack.pop()
        self._undo_stack.append(snapshot)
        self._restore_snapshot(snapshot)

        self._undo_block = False
        self.mark_dirty()
        
    def set_edit_mode(self, mode: EditMode):
        if self._edit_mode == mode:
            return
        self._edit_mode = mode
        self._update_view_drag_mode()
        
    def _update_view_drag_mode(self):
        if self._edit_mode == EditMode.AREA_SELECT:
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        
    def _scene_dist_from_view_px(self, px: float) -> float:
        # 화면 px 반경을 scene 반경으로 변환 (줌 대응)
        p0 = self.view.mapToScene(0, 0)
        p1 = self.view.mapToScene(int(px), 0)
        return QLineF(p0, p1).length()

    def _on_hover_move(self, event):
        # 드래그 중이면 hover는 하지 않음
        if self._drag_mode in (DragMode.MOVE, DragMode.MOVE_ANCHOR, DragMode.CREATE):
            return

        scene_pos = self.view.mapToScene(event.position().toPoint())
        radius_scene = self._scene_dist_from_view_px(self._anchor_handle_radius_px)

        best_item = None
        best_dist = 1e18
        best_anchor = None

        # line이 붙은 도형만 대상으로 anchor 근접 검사
        for it in self.scene.items():
            if not hasattr(it, "to_dict"):
                continue
            # line이 붙은 항목만
            line = getattr(it, "_attached_line", None)
            anchor = getattr(it, "_line_anchor_scene_pos", None)
            if line is None or anchor is None:
                continue

            d = QLineF(scene_pos, anchor).length()
            if d < radius_scene and d < best_dist:
                best_item = it
                best_dist = d
                best_anchor = anchor

        if best_item:
            self._anchor_handle_target = best_item
            self._anchor_handle.setPos(best_anchor)
            self._anchor_handle.setVisible(True)
        else:
            self._anchor_handle_target = None
            self._anchor_handle.setVisible(False)
        
    def _calc_next_defect_index(self) -> int:
        max_n = 0
        for item in self.scene.items():
            if hasattr(item, "display_id"):
                did = item.display_id

                # Circle: display_id가 int
                if isinstance(did, int):
                    max_n = max(max_n, did)

                # 기존 문자열 ID 호환
                elif isinstance(did, str):
                    try:
                        n = int(did.split("-")[-1])
                        max_n = max(max_n, n)
                    except:
                        pass

        return max_n + 1

        
    def _can_create_at(self, scene_pos: QPointF) -> bool:
        """
        기존 도형 위에서는 새 도형 생성 불가
        (최종 생성 방어용)
        """
        hit = self.scene.itemAt(scene_pos, QTransform())
        block = hit
        while block is not None:
            if hasattr(block, "to_dict"):
                return False
            block = block.parentItem()
        return True
        
    def _init_defect_for_item(self, item):
        import uuid

        item.internal_id = str(uuid.uuid4())

        if isinstance(item, CircleMark):
            item.set_circle_id(self._next_defect_index)
            self._next_defect_index += 1

            item.defect_info = {
                "member": "벽체",
                "location": "",
                "defect_type": "",
                "size": {"width_mm": "", "length_m": "", "count_ea": ""},
                "progress": False,
                "remark": ""
            }
            item.enable_defect_label(item.defect_info["member"])
            self._safe_connect_open_detail(item)
              
    def mark_dirty(self):
        self.dirtyChanged.emit()
        
    def reset_view_transform(self):
        self.view.resetTransform()

        if hasattr(self, "_base_view_scale"):
            s = self._base_view_scale
            self.view.scale(s, s)
            self._current_view_scale = s

        parent = self.parent()
        if parent and hasattr(parent, "status_bar"):
            parent.status_bar.set_zoom(1.0)
        
    # ---------- 삭제 ----------
    def delete_selected_items(self):
        items = self.scene.selectedItems()
        if not items:
            return

        self._begin_edit()

        for item in items:
            if hasattr(item, "_attached_line") and item._attached_line:
                self.scene.removeItem(item._attached_line)
            self.scene.removeItem(item)

        # 삭제 완료 후 Circle ID 재정렬
        self._renumber_circle_ids()

        # 다음 생성 ID도 재계산(안전)
        self._next_defect_index = self._calc_next_defect_index()

        self.scene.clearSelection()
        self._end_edit()
        self.mark_dirty()
        
    def _add_shape(self, tool, label, pixmap):
        item = QListWidgetItem(QIcon(pixmap), label)
        item.setSizeHint(QSize(
            self.shape_list.iconSize().width() + 20,
            self._menu_item_height
        ))
        item.setData(Qt.ItemDataRole.UserRole, tool)
        self.shape_list.addItem(item)

    def _on_shape_selected(self, current, _):
        if current:
            self.current_tool = current.data(Qt.ItemDataRole.UserRole)

    # ---------- 아이콘 ----------
    def _icon_line(self):
        pix = QPixmap(48, 48)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(Qt.GlobalColor.blue, 2))   # 굵기 ↓
        p.drawLine(14, 34, 34, 14)               # 여백 ↑
        p.end()
        return pix

    def _icon_free(self):
        pix = QPixmap(48, 48)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(Qt.GlobalColor.blue, 2))
        path = QPainterPath(QPointF(14, 24))
        path.cubicTo(18, 14, 30, 34, 34, 24)
        p.drawPath(path)
        p.end()
        return pix
        
    def _icon_circle(self):
        pix = QPixmap(48, 48)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(Qt.GlobalColor.red, 3))
        p.drawEllipse(12, 12, 24, 24)
        p.end()
        return pix

    def _icon_square(self):
        pix = QPixmap(48, 48)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(Qt.GlobalColor.red, 1))
        p.setBrush(QBrush(Qt.GlobalColor.red))
        p.drawRect(11, 11, 26, 26)
        p.end()
        return pix

    def _icon_triangle(self):
        pix = QPixmap(48, 48)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(Qt.GlobalColor.red, 1))
        p.setBrush(QBrush(Qt.GlobalColor.red))
        p.drawPolygon(QPolygonF([
            QPointF(24, 12),
            QPointF(12, 36),
            QPointF(36, 36)
        ]))
        p.end()
        return pix

    def _icon_s(self):
        pix = QPixmap(48, 48)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(Qt.GlobalColor.red, 1))
        path = QPainterPath()
        path.moveTo(24, 6)
        path.cubicTo(12, 16, 36, 32, 24, 42)
        p.drawPath(path)
        p.setBrush(QBrush(Qt.GlobalColor.red))
        p.drawEllipse(QPointF(24, 24), 3, 3)
        p.end()
        return pix

    def _icon_text(self):
        pix = QPixmap(48, 48)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setPen(Qt.GlobalColor.blue)
        p.setFont(QFont("Malgun Gothic", 16, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, 48, 48), Qt.AlignmentFlag.AlignCenter, "T")
        p.end()
        return pix

    def _is_basic_shape(self):
        return self.current_tool in ("circle", "rect", "tri", "s", "text")

    # ---------- 마우스 ----------
    def _on_mouse_move(self, event):
        if self._drag_mode == DragMode.NONE:
            return
              
        if self._drag_mode == DragMode.MOVE_ANCHOR and self._drag_item:
            scene_pos = self.view.mapToScene(event.position().toPoint())
            item = self._drag_item

            # anchor는 오직 이 모드에서만 변경
            item._line_anchor_scene_pos = scene_pos
            item._update_attached_line_geometry()

            self._anchor_handle_target = item
            self._anchor_handle.setPos(scene_pos)
            self._anchor_handle.setVisible(True)
            return
    
        if self._drag_mode == DragMode.MOVE and self._drag_item:
            item = self._drag_item

            # 핵심: MOVE 중 실시간 leader line 갱신 (old 방식)
            if hasattr(item, "_update_attached_line_geometry"):
                item._update_attached_line_geometry()

            item._update_defect_label_pos()
            return
                       
        # ===== CREATE: memo 전용 =====
        if self._drag_mode == DragMode.CREATE and isinstance(self._drag_item, MemoLine):
            scene_pos = self.view.mapToScene(event.position().toPoint())
            self._drag_item.setLine(QLineF(self._press_pos, scene_pos))
            return

        if self._drag_mode == DragMode.CREATE and isinstance(self._drag_item, MemoFreePath):
            scene_pos = self.view.mapToScene(event.position().toPoint())
            self._drag_item.add_point(scene_pos)
            return

        # ===== CREATE: Circle + leader line (old 방식) =====
        if (
            self._drag_mode == DragMode.CREATE
            and isinstance(self._drag_item, CircleMark)
            and self._drag_line
            and (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            scene_pos = self.view.mapToScene(event.position().toPoint())
            item = self._drag_item

            item.setPos(scene_pos)
            item.setVisible(True)

            # 실선은 항상 원 외곽 기준
            item._update_attached_line_geometry()

            # ID 실시간 표시 + 중앙 정렬
            if hasattr(item, "display_id"):
                item.set_circle_id(item.display_id)
            return

    def _on_mouse_release(self, event):
        MIN_MEMO_LINE_LEN = 8.0
        MIN_MEMO_PATH_SIZE = 6.0
        if event.button() != Qt.MouseButton.LeftButton:
            return
              
        if isinstance(self._drag_item, MemoLine):
            line = self._drag_item.line()
            if line.length() < MIN_MEMO_LINE_LEN:
                # 너무 짧으면 취소
                self.scene.removeItem(self._drag_item)
                self._end_edit()
                self._reset_mouse_drag()
                return
                
        if isinstance(self._drag_item, MemoFreePath):
            rect = self._drag_item.path().boundingRect()
            if rect.width() < MIN_MEMO_PATH_SIZE and rect.height() < MIN_MEMO_PATH_SIZE:
                # 점처럼 찍힌 경우 → 취소
                self.scene.removeItem(self._drag_item)
                self._end_edit()
                self._reset_mouse_drag()
                return
              
        if self._drag_mode in (DragMode.MOVE, DragMode.MOVE_ANCHOR):
            item = self._drag_item

            if (
                self._drag_mode == DragMode.MOVE
                and item
                and hasattr(item, "_attached_line")
                and item._attached_line
            ):
                item._update_attached_line_geometry()

            self._edit_end_timer.start(300)
            self._drag_mode = DragMode.NONE
            self._drag_item = None
            self.mark_dirty()
            return
             
        self._press_timer.stop()
        self._pressing = False
        self._pending_press_pos = None

        # memo CREATE 종료 먼저 처리
        if self._drag_mode == DragMode.CREATE and isinstance(self._drag_item, (MemoLine, MemoFreePath)):
            self._end_edit()
            self._reset_mouse_drag()
            self.mark_dirty()
            return
        
        # ---- CREATE 종료 처리 ----
        if self._drag_mode == DragMode.CREATE and self._drag_item is not None:
            end_pos = self.view.mapToScene(event.position().toPoint())
            straight_len = QLineF(self._press_pos, end_pos).length()

            if not isinstance(self._drag_item, NoteText):
                min_len = self._min_line_length_for_item(self._drag_item)
                if straight_len < min_len:
                    self._drag_item.cancel_attach(self.scene)
                    self.scene.removeItem(self._drag_item)
                    self._reset_mouse_drag()
                    return

            self._drag_item.setPos(end_pos)
            item = self._drag_item
            item.setPos(end_pos)
            item.setVisible(True)
            item.confirm_attach()
            
            # 핵심: 드래그 생성 후에도 초기화 반드시 수행
            self._init_defect_for_item(item)
            
            self._end_edit()
            self.mark_dirty()
            self._reset_mouse_drag()
            return
                          
    def _on_mouse_press(self, event):
        if self.bg_item is None:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
   
        scene_pos = self.view.mapToScene(event.position().toPoint())

        if self._anchor_handle.isVisible() and self._anchor_handle_target is not None:
            anchor = getattr(self._anchor_handle_target, "_line_anchor_scene_pos", None)

            if anchor is not None:
                radius_scene = self._scene_dist_from_view_px(self._anchor_handle_radius_px)
                if QLineF(scene_pos, anchor).length() <= radius_scene:
                    self._begin_edit()
                    self._drag_mode = DragMode.MOVE_ANCHOR
                    self._drag_item = self._anchor_handle_target
                    return True
                    
        # ... _on_mouse_press 내부, scene_pos 만든 직후에 추가
        raw = self.scene.itemAt(scene_pos, QTransform())
        if isinstance(raw, (MemoLine, MemoFreePath)):
            mods = event.modifiers()

            # 단일 선택 동작 (Ctrl/Shift 없으면 기존 선택 해제 후 선택)
            if self._edit_mode != EditMode.AREA_SELECT:
                if not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
                    self.scene.clearSelection()
                    raw.setSelected(True)
                else:
                    raw.setSelected(not raw.isSelected())

            # memo는 이동/생성 로직으로 안 흘러가게 여기서 끝
            return True

        hit = self._find_shape_at(scene_pos)
        # memo 도형은 Qt 기본 선택 처리에 맡긴다
        if isinstance(hit, (MemoLine, MemoFreePath)):
            return False        
        # ---- 단일 선택 강제 (영역선택 모드가 아닐 때) ----
        if self._edit_mode != EditMode.AREA_SELECT:
            self.scene.clearSelection()

        if hit and self._edit_mode == EditMode.SELECT:
            # ⭐ MOVE 시작 → 편집 세션 시작
            self._begin_edit()
            self._drag_mode = DragMode.MOVE
            self._drag_item = hit
                           
            return False   # Qt 이동은 그대로 사용
        
        # 선택 모드 + 빈 공간일 때만 생성 대기
        if self._edit_mode == EditMode.SELECT and hit is None:
            if self.current_tool == "memo_line":
                self._press_timer.stop()
                self._pressing = False
                self._pending_press_pos = None

                self._begin_edit()
                self._drag_mode = DragMode.CREATE
                self._press_pos = scene_pos
                self._drag_item = MemoLine(scene_pos, scene_pos)
                self._drag_line = None
                self.scene.addItem(self._drag_item)
                return True

            if self.current_tool == "memo_free":
                self._press_timer.stop()
                self._pressing = False
                self._pending_press_pos = None

                self._begin_edit()
                self._drag_mode = DragMode.CREATE
                self._press_pos = scene_pos
                self._drag_item = MemoFreePath(scene_pos)
                self._drag_line = None
                self.scene.addItem(self._drag_item)
                return True
        
            self._pressing = True
            self._pending_press_pos = scene_pos
            self._press_timer.start(500)
            
        return False
                    
    def _on_mouse_double_click(self, event) -> bool:
        # 드래그 타이머 완전 취소
        self._press_timer.stop()
        self._pressing = False
        self._pending_press_pos = None
        
        # 왼쪽 버튼만 처리
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # 배경 없거나 도형 생성 불가 상태면 처리 안 함
        if (
            self.bg_item is None
            or not self._is_basic_shape()
            or self._edit_mode != EditMode.SELECT
        ):
            return False

        pos = self.view.mapToScene(event.position().toPoint())

        # 기존 도형 위에서는 더블클릭 생성 금지
        if not self._can_create_at(pos):
            return False

        item = None
        if self.current_tool == "circle":
            item = CircleMark(pos)
        elif self.current_tool == "rect":
            item = SquareMark(pos)
        elif self.current_tool == "tri":
            item = TriangleMark(pos)
        elif self.current_tool == "s":
            item = SCurveWithMidCircle(pos)
        elif self.current_tool == "text":
            item = NoteText(pos)

        if not item:
            return False
      
        # ---- 실제 처리 ----
        self._begin_edit()
        self.scene.addItem(item)
        self._init_defect_for_item(item)
        item.setSelected(True)
        self._end_edit()
        self.mark_dirty()
        return True
        
    def _begin_drag_create(self):
        if self.current_tool != "circle":
            return
        if self._drag_mode != DragMode.NONE:
            return
        if self._edit_mode != EditMode.SELECT:
            return
        if not self._pressing or not self._pending_press_pos:
            return

        self._begin_edit()

        scene_pos = self._pending_press_pos
        self._pressing = False
        self._pending_press_pos = None

        # anchor = 최초 press 위치 (절대 고정)
        anchor_scene = scene_pos

        # Circle 생성 (center는 release 시 확정)
        item = CircleMark(scene_pos)
        item.setVisible(False)
        self.scene.addItem(item)

        # CREATE 중에도 ID가 보이도록 임시 ID 완전 초기화
        if hasattr(item, "_id_text_item"):
            next_id = self._next_defect_index
            # 핵심: display_id를 먼저 설정
            item.display_id = next_id
            # 중앙 정렬 포함 초기화
            item.set_circle_id(next_id)
            item._id_text_item.setVisible(True)

        item.begin_attach(self.scene, anchor_scene)

        # drag 상태 진입
        self._drag_mode = DragMode.CREATE
        self._press_pos = scene_pos
        self._drag_item = item
        self._drag_line = item._attached_line
              
    def _min_line_length_for_item(self, item) -> float:
        rect = item.boundingRect()
        base = max(rect.width(), rect.height())
        return base + 10.0 # 10 마진
                      
    def _find_shape_at(self, scene_pos):
        for hit in self.scene.items(scene_pos):
            it = hit
            while it is not None:
                if hasattr(it, "to_dict"):
                    return it
                it = it.parentItem()
        return None
                                            
    def _reset_mouse_drag(self):
        self._drag_mode = DragMode.NONE
        self._press_pos = None

        self._drag_item = None
        self._drag_line = None
          
        # once 플래그 리셋 (position + transform 모두)
        for item in self.scene.items():
            if hasattr(item, "_position_dirty_once"):
                item._position_dirty_once = False
            if hasattr(item, "_transform_dirty_once"):
                item._transform_dirty_once = False
            if hasattr(item, "_scale_dirty_once"):
                item._scale_dirty_once = False
              
    # ---------- 메뉴 패널 ----------    
    def _build_shape_panel(self):
        self.shape_panel = QWidget(self)
        self.shape_panel.raise_()
        
        # 이동 중 깜빡임/리페인트 비용 감소
        self.shape_panel.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.shape_panel.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        
        # ---------- Frame (외곽 테두리용) ----------
        self.shape_frame = QFrame(self.shape_panel)
        self.shape_frame.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #444;
            }
        """)
        
        self._menu_item_height = 36 # 핵심 (32~38 취향 조절 가능)
        
        # 패널은 마우스 이벤트를 정상적으로 받는다 (명시)
        self.shape_panel.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            False
        )
        
        self.shape_panel.setMouseTracking(True)
        self.shape_panel.setStyleSheet("""
            QWidget {
                background: white;
                border: none;
            }
        """)
        
        # ---------- Header (Drag Handle) ----------
        self.shape_header = QWidget(self.shape_panel)
        self.shape_header.setFixedHeight(18)   # 22 → 18
        self.shape_header.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
                border-bottom: 1px solid #444;
            }
        """)
      
        header_layout = QHBoxLayout(self.shape_header)
        header_layout.setContentsMargins(8, 0, 8, 0)  # 위/아래 여백 제거
        header_layout.setSpacing(0)

        header_label = QLabel("도형 선택")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 12px;
            }
        """)

        header_layout.addStretch(1)
        header_layout.addWidget(header_label)
        header_layout.addStretch(1)

        self.shape_list = QListWidget(self.shape_panel)
        # 핵심 3종 세트
        self.shape_list.setViewportMargins(0, 0, 0, 0)
        self.shape_list.viewport().setContentsMargins(0, 0, 0, 0)
        self.shape_list.setSpacing(0)

        self.shape_list.setIconSize(QSize(28, 28))
        self.shape_list.setFrameShape(QFrame.Shape.NoFrame)
        self.shape_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.shape_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
                outline: 0;
            }
            QListWidget::viewport {
                padding-top: -2px;   /* 핵심 */
                margin: 0px;
            }
            QListWidget::item {
                margin: 0px;
                padding: 2px 4px;
            }
        """)

        # frame 내부 레이아웃
        frame_layout = QVBoxLayout(self.shape_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        frame_layout.addWidget(self.shape_header)
        frame_layout.addWidget(self.shape_list)

        # panel 전체 레이아웃
        outer = QVBoxLayout(self.shape_panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.shape_frame)

        # ===== 메모 / 드로잉 =====
        self._add_shape("memo_line", "직선", self._icon_line())
        self._add_shape("memo_free", "자유곡선", self._icon_free())

        self._add_divider_item()

        # ===== 하자 포인트 (핵심) =====
        self._add_shape("circle", "동그라미", self._icon_circle())

        self._add_divider_item()

        # ===== 범례 / 표시용 =====
        self._add_shape("rect", "정사각형", self._icon_square())
        self._add_shape("tri", "정삼각형", self._icon_triangle())
        self._add_shape("s", "균열(S)", self._icon_s())
        self._add_shape("text", "텍스트", self._icon_text())

        self.shape_list.currentItemChanged.connect(self._on_shape_selected)
        self.shape_list.setCurrentRow(0)

        # 메뉴 수형 길이
        self.shape_list.setFixedWidth(140)
        
        # 메뉴 수직 길이
        list_height = 0
        for i in range(self.shape_list.count()):
            item = self.shape_list.item(i)
            hint = item.sizeHint()
            list_height += hint.height()

        # spacing 보정
        list_height += self.shape_list.spacing() * max(0, self.shape_list.count() - 1)
        self.shape_list.setFixedHeight(list_height)
     
        self.shape_panel.adjustSize()
        
        self.shape_header.mousePressEvent = self._on_shape_panel_header_press
        self.shape_header.mouseMoveEvent = self._on_shape_panel_header_move
        self.shape_header.mouseReleaseEvent = self._on_shape_panel_header_release

        self.shape_panel.hide()
        
    def _add_divider_item(self, height=1):
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)  # 선택 불가
        item.setSizeHint(QSize(self.shape_list.width(), height + 2))

        frame = QFrame()
        frame.setFixedHeight(height)
        frame.setStyleSheet("background: #999; margin-left: 8px; margin-right: 8px;")

        self.shape_list.addItem(item)
        self.shape_list.setItemWidget(item, frame)
                        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 패널 위치는 항상 재계산
        self._reposition_shape_panel()
        
    def _reposition_shape_panel(self):
        if not self.shape_panel.isVisible():
            return

        panel_size = self.shape_panel.size()        
        editor_rect = self.rect()
        x = editor_rect.width() - panel_size.width() - 16
        y = (editor_rect.height() - panel_size.height()) // 2
        self.shape_panel.move(x, y)
              
    def _on_shape_panel_header_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panel_dragging = True
            self._panel_drag_offset = (
                event.globalPosition().toPoint()
                - self.shape_panel.pos()
            )
            self._panel_pending_pos = None

            # 타이머 돌고 있으면 중지
            if self._panel_move_timer.isActive():
                self._panel_move_timer.stop()

            event.accept()

    def _on_shape_panel_header_move(self, event):
        if not self._panel_dragging:
            return

        # 목표 위치 계산
        new_pos = (
            event.globalPosition().toPoint()
            - self._panel_drag_offset
        )

        # 바로 move하지 말고 "대기 위치"만 갱신한다 (throttle)
        self._panel_pending_pos = new_pos

        # 60fps 정도로만 이동 적용(16ms)
        if not self._panel_move_timer.isActive():
            self._panel_move_timer.start(16)

        event.accept()

    def _on_shape_panel_header_release(self, event):
        self._panel_dragging = False

        # 마지막 위치는 즉시 반영 (마무리 튐 방지)
        if self._panel_move_timer.isActive():
            self._panel_move_timer.stop()
        self._apply_pending_panel_move()

        event.accept()
        
    def open_png_from_path(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            return

        self.scene.clear()

        # 기존 anchor_handle은 C++에서 삭제됨
        self._anchor_handle = QGraphicsEllipseItem(-4, -4, 8, 8)
        self._anchor_handle.setBrush(QBrush(Qt.GlobalColor.white))
        self._anchor_handle.setPen(QPen(Qt.GlobalColor.red, 2))
        self._anchor_handle.setZValue(999)
        self._anchor_handle.setVisible(False)
        self._anchor_handle.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )
        self._anchor_handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(self._anchor_handle)

        self._anchor_handle_target = None
    
        self.bg_path = path
        self.bg_item = QGraphicsPixmapItem(pix)
        self.bg_item.setZValue(-100)
        self.scene.addItem(self.bg_item)

        self.scene.setSceneRect(QRectF(pix.rect()))
        self.view.resetTransform()
        self._fitted = False

        self.shape_panel.show()
        self.shape_panel.adjustSize()
        
        # viewport 확정 이후 위치 보정
        QTimer.singleShot(0, self._reposition_shape_panel)
                       
    MARK_CLASSES = {
        "CircleMark": CircleMark,
        "SquareMark": SquareMark,
        "TriangleMark": TriangleMark,
        "SCurveWithMidCircle": SCurveWithMidCircle,
        "NoteText": NoteText,
    }

    def _restore_item(self, info):
        cls = self.MARK_CLASSES.get(info["type"])
        if not cls:
            return

        item = cls.from_dict(info, self.scene, self)
        if not item:
            return

        # 위치/형태 복원 후
        self.scene.addItem(item)
        item.setScale(info.get("scale", 1.0))
        item.setRotation(info.get("rotation", 0))

        # ID / 하자 정보 복원
        item.internal_id = info.get("internal_id")
        item.display_id = info.get("display_id")
        item.defect_info = info.get("defect_info", {})
        
        if isinstance(item, CircleMark):
            di = item.defect_info or {}
            di.setdefault("member", "")
            di.setdefault("location", "")
            di.setdefault("defect_type", "")
            di.setdefault("size", {"width_mm": "", "length_m": "", "count_ea": ""})
            di.setdefault("progress", False)
            di.setdefault("remark", "")
            item.defect_info = di

            # 시그널 연결(복원된 아이템도 연결 필요)
            self._safe_connect_open_detail(item)

        if isinstance(item, CircleMark) and item.display_id:
            # 원 안 숫자 복원
            item.set_circle_id(item.display_id)

            # 오른쪽 설명 복원
            text = item.defect_info.get("member", "")
            item.enable_defect_label(text)          
        elif item.display_id:
            # 기존 도형은 그대로
            item.enable_defect_label(item.display_id)

        line_data = info.get("line")
        if line_data:
            p1 = QPointF(*line_data["p1"])
            p2 = QPointF(*line_data["p2"])

            line = QGraphicsLineItem(QLineF(p1, p2))
            line.setPen(QPen(Qt.GlobalColor.red, 2))
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            line.setZValue(-1)
            self.scene.addItem(line)

            item._attached_line = line
            item._line_anchor_scene_pos = p1
            item._update_attached_line_geometry()

# =====================================================
# QWidget for status bar
# =====================================================             
class FaultEditorStatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(26)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        # 상태 텍스트 (좌측)
        self.status_label = QLabel("준비됨")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # (확장용) 선택 정보 라벨 – 지금은 숨김
        self.selection_label = QLabel("")
        self.selection_label.setVisible(False)

        # Zoom (우측)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self.status_label)
        layout.addWidget(self._vline())
        layout.addWidget(self.selection_label)
        layout.addStretch(1)
        layout.addWidget(self._vline())
        layout.addWidget(self.zoom_label)

    def _vline(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    # ---------- API ----------
    def set_dirty(self, dirty: bool):
        if dirty:
            self.status_label.setText("변경 사항 있음")
        else:
            self.status_label.setText("저장됨")

    def set_zoom(self, scale: float):
        self.zoom_label.setText(f"{int(scale * 100)}%")

    def set_selection_count(self, count: int):
        if count > 0:
            self.selection_label.setText(f"선택: {count}개")
            self.selection_label.setVisible(True)
        else:
            self.selection_label.setVisible(False)         
                                                       
# =====================================================
# Dialog for editor(Main)
# =====================================================                        
class FaultEditorDialog(QDialog):
    saveRequested = pyqtSignal(dict)  # 실제 defects 전달
    def __init__(self, image_path: str, defects: dict | None = None, parent=None):
        super().__init__(parent)
             
        self._base_title = "하자 편집"
        self.setWindowTitle(self._base_title)
        self.resize(1400, 900)
        
        self.editor = FaultEditorWidget(self)
        self.editor.dirtyChanged.connect(self.mark_dirty)
        
        # ----- Menu Bar -----
        menubar = QMenuBar(self)
        menubar.setNativeMenuBar(False)
        
        # ---------- 파일 ----------
        file_menu = menubar.addMenu("파일")

        self.act_save = QAction("저장", self)
        self.act_save.setShortcut("Ctrl+S")         
        self.act_save.triggered.connect(self.save_if_dirty)
        file_menu.addAction(self.act_save)

        file_menu.addSeparator()

        self.act_close = QAction("닫기", self)
        self.act_close.setShortcut("Ctrl+W") 
        self.act_close.triggered.connect(self.reject)
        file_menu.addAction(self.act_close)

        # ---------- 편집 ----------
        edit_menu = menubar.addMenu("편집")
        
        self.act_undo = QAction("실행취소", self)
        self.act_undo.setShortcut("Ctrl+Z")
        self.act_undo.triggered.connect(self.editor.undo)

        self.act_redo = QAction("다시실행", self)
        self.act_redo.setShortcut("Ctrl+Y")
        self.act_redo.triggered.connect(self.editor.redo)

        edit_menu.addSeparator()
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        
        self.act_select_mode = QAction("선택", self, checkable=True)
        self.act_area_select_mode = QAction("영역선택", self, checkable=True)

        self.act_select_mode.setChecked(True)

        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        mode_group.addAction(self.act_select_mode)
        mode_group.addAction(self.act_area_select_mode)

        edit_menu.addSeparator()
        edit_menu.addAction(self.act_select_mode)
        edit_menu.addAction(self.act_area_select_mode)
        
        self.act_select_mode.triggered.connect(
            lambda: self.editor.set_edit_mode(EditMode.SELECT)
        )
        self.act_area_select_mode.triggered.connect(
            lambda: self.editor.set_edit_mode(EditMode.AREA_SELECT)
        )        

        self.act_delete_selected = QAction("도형삭제", self)
        self.act_delete_selected.setShortcut("Del") 
        self.act_delete_selected.triggered.connect(
            self.editor.delete_selected_items
        )
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_delete_selected)
        self.act_delete_selected.setEnabled(False)  # 처음엔 선택 없으므로 비활성
        self.act_delete_selected.setShortcutContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        
         # ---------- 보기 ----------
        view_menu = menubar.addMenu("보기")

        self.act_reset_view = QAction("화면 원래 크기", self)
        self.act_reset_view.setShortcut("Ctrl+0")
        self.act_reset_view.triggered.connect(
            self.editor.reset_view_transform
        )
        view_menu.addAction(self.act_reset_view)
        
        self.editor.scene.selectionChanged.connect(self._update_edit_actions)
        self.editor.scene._editor = self
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(menubar)
        layout.addWidget(self.editor)

        # ── 편집창 / 상태바 구분선 ──
        hline = QFrame(self)
        hline.setFrameShape(QFrame.Shape.HLine)
        hline.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(hline)

        # ── 상태바 ──
        self.status_bar = FaultEditorStatusBar(self)
        layout.addWidget(self.status_bar)

        # 이미지 로드
        self.editor.open_png_from_path(image_path)
        
        snap = self.editor._make_snapshot()
        self.editor._baseline_snapshot = snap
        self.editor._undo_stack.clear()
        self.editor._redo_stack.clear()
        self.editor._undo_stack.append(snap)
                     
        self.status_bar.set_dirty(False)
        self.status_bar.set_zoom(1.0)
        
        # defects 로드
        if defects:
            self._load_defects(defects)
            self._update_edit_actions()
        else:
            # 빈 문서도 baseline으로 설정
            self.editor._baseline_snapshot = self.editor._make_snapshot()
                
        self._dirty = False
        self._update_title()
        
    def _on_open_defect_detail(self, circle: CircleMark):
        circle.setSelected(True)
        self.editor.scene.clearSelection()
        self.editor.detail_panel.show_for_circle(circle)
        
    def _update_title(self):
        self.setWindowTitle(self._base_title)
        
    def _update_edit_actions(self):
        has_selection = bool(self.editor.scene.selectedItems())
        self.act_delete_selected.setEnabled(has_selection)
    
    def mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self.status_bar.set_dirty(True)    
  
    def save_if_dirty(self):
        if not self._dirty:
            QMessageBox.information(self, "저장", "변경된 내용이 없습니다.")
            return

        defects = self.get_defects()

        # 저장 완료 후: undo 기준점을 "저장본"으로 리셋
        snap = self.editor._make_snapshot()
        self.editor._baseline_snapshot = snap
        self.editor._undo_stack.clear()
        self.editor._redo_stack.clear()
        self.editor._undo_stack.append(snap)

        self.saveRequested.emit(defects)  # 실제 저장 요청
        self._dirty = False
        self.status_bar.set_dirty(False)

        QMessageBox.information(self, "저장", "하자 데이터가 저장되었습니다.")  
        
    def _load_defects(self, defects: dict):
        """
        defects 구조는 기존 save_project()에서 쓰던 data["items"] 그대로
        """
        data = {
            "image": self.editor.bg_path,
            "items": defects.get("items", [])
        }
        self.editor.scene.clear()
        self.editor.open_png_from_path(data["image"])

        for info in data["items"]:
            self.editor._restore_item(info)  # 아래에서 추가할 helper
        
        self.editor._next_defect_index = self.editor._calc_next_defect_index()
        self._dirty = False
        self._update_title()
        self._last_saved = self.get_defects()
        
        # ===== baseline 설정 =====
        self.editor._baseline_snapshot = self.get_defects()
        self.editor._undo_stack.clear()
        self.editor._redo_stack.clear()        
        self.editor._undo_stack.append(self.editor._baseline_snapshot)

    def get_defects(self) -> dict:
        items = []
        for item in self.editor.scene.items():
            if hasattr(item, "to_dict"):
                items.append(item.to_dict())
        return {"items": items}
               
    def accept(self):
        self._accepted = True
        super().accept()

    def reject(self):
        if self._dirty:
            ok = QMessageBox.question(
                self,
                "저장되지 않은 변경",
                "저장되지 않은 변경 사항이 있습니다.\n종료하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ok != QMessageBox.StandardButton.Yes:
                return

        self._accepted = False
        super().reject()
        
            