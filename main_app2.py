import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter, QLabel, QFrame,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsObject, QGraphicsTextItem,
    QLineEdit, QPushButton, QFileDialog, QSpinBox, QFormLayout, QComboBox, QScrollArea,
    # --- ADD THESE TWO ---
    QGraphicsSceneHoverEvent, 
    QGraphicsSceneMouseEvent,
    QGraphicsPathItem
)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QObject, QEvent
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath # Added QPainterPath
import uuid


# --- Phase 2: Data Model Definitions (from previous step) ---
class Node:
    def __init__(self, node_type, name="New Node", position=(50, 50), properties=None):
        self.id = str(uuid.uuid4())
        self.node_type = node_type
        self.name = name
        self.position = QPointF(position[0], position[1])
        self.properties = properties if properties is not None else {}
        
        self.width = 150
        self.height = 80

        # --- NEW: Define Ports ---
        self.input_ports = []
        self.output_ports = []
        self._define_ports() 

        # Add default properties for certain node types if desired
        if self.node_type == "Log Message" and "message" not in self.properties:
            self.properties["message"] = "Default log message"
        if self.node_type == "Delay/Wait" and "duration_ms" not in self.properties:
            self.properties["duration_ms"] = 1000 # Default 1 second
        # ... other defaults ...
        self.width = 150 # Default width
        self.height = 80  # Default height

    def _define_ports(self):
        # General case: one input (except Start), one output (except End)
        if self.node_type != "Start":
            self.input_ports.append({"name": "in", "type": "input"}) # Generic input

        if self.node_type != "End":
            if self.node_type == "Conditional (If/Else)":
                self.output_ports.append({"name": "true", "type": "output"})
                self.output_ports.append({"name": "false", "type": "output"})
            else:
                self.output_ports.append({"name": "out", "type": "output"}) # Generic output
    
    def get_port_scene_position(self, graphics_node, port_name, port_type):
        # This will be a helper in GraphicsNode later, but conceptually:
        # Calculate the scene position of a port
        node_scene_pos = graphics_node.scenePos()
        
        # Simplified port positioning (can be made more dynamic)
        port_y_offset = self.height / 2
        if port_type == "input":
            if self.input_ports: # Check if list is not empty
                 # Distribute multiple input ports if any, for now just one
                idx = next((i for i, p in enumerate(self.input_ports) if p["name"] == port_name), 0)
                port_y_offset = (self.height / (len(self.input_ports) + 1)) * (idx + 1)
                return node_scene_pos + QPointF(0, port_y_offset) # Left side
        elif port_type == "output":
            if self.output_ports: # Check if list is not empty
                idx = next((i for i, p in enumerate(self.output_ports) if p["name"] == port_name), 0)
                if self.node_type == "Conditional (If/Else)" and len(self.output_ports) == 2:
                    port_y_offset = (self.height / 3) * (idx + 1) # Position true/false outputs
                else: # Single output port
                    port_y_offset = self.height / 2
                return node_scene_pos + QPointF(self.width, port_y_offset) # Right side
        return node_scene_pos # Fallback

    def __repr__(self):
        return f"Node(id={self.id}, type='{self.node_type}', name='{self.name}')"
# --- Event Filter for SpinBoxes ---
class SpinBoxWheelEventFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, QSpinBox):
            if not obj.hasFocus():
                event.ignore() # Tell the event system this event should be ignored by this widget
                return True    # Event handled (ignored), stop further processing by this widget
        return super().eventFilter(obj, event) # Continue with default event processing


class Connection:
    def __init__(self, from_node_id, from_port_name, to_node_id, to_port_name):
        self.id = str(uuid.uuid4())
        self.from_node_id = from_node_id
        self.from_port_name = from_port_name
        self.to_node_id = to_node_id
        self.to_port_name = to_port_name

    def __repr__(self):
        return f"Connection(from={self.from_node_id}.{self.from_port_name} to {self.to_node_id}.{self.to_port_name})"

class Flow:
    def __init__(self):
        self.nodes = {}
        self.connections = []

    def add_node(self, node):
        self.nodes[node.id] = node

    def add_connection(self, connection):
        self.connections.append(connection)

    def get_node(self, node_id):
        return self.nodes.get(node_id)

    def __repr__(self):
        return f"Flow(nodes={len(self.nodes)}, connections={len(self.connections)})"


# --- Phase 3: Visual Node Item ---
class GraphicsNode(QGraphicsObject): # QGraphicsObject allows signals/slots
    # Signal emitted when the node is selected
    node_selected = pyqtSignal(object) # Will pass the data_node object
    
    # --- NEW: Signals for port interaction ---
    port_drag_started = pyqtSignal(object, str, QPointF) # self, port_name, scene_pos
    port_drag_ended_on_port = pyqtSignal(object, str, object, str) # from_graphics_node, from_port_name, to_graphics_node, to_port_name
    port_drag_ended_on_nothing = pyqtSignal()
    node_moved = pyqtSignal(str) # NEW SIGNAL: Pass node_id (data_node.id)

    def __init__(self, data_node: Node, parent=None):
        super().__init__(parent)
        self.data_node = data_node

        self.setPos(self.data_node.position)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.width = self.data_node.width # Ensure these are set from data_node
        self.height = self.data_node.height

        self.color = QColor("#5DADE2")
        self.border_color = QColor("#1B4F72")
        self.text_color = QColor(Qt.GlobalColor.black) 
        self.font = QFont("Arial", 10)

        self.title_item = QGraphicsTextItem(self) 
        self.update_display_text() 
        # self.title_item.setDefaultTextColor(self.text_color) # Done in update_display_text
        # self.title_item.setFont(self.font) # Done in update_display_text
        # title_rect = self.title_item.boundingRect() # Done in update_display_text
        # self.title_item.setPos((self.width - title_rect.width()) / 2, 5) # Done

        # --- NEW: Port Properties ---
        self.port_radius = 6  # Visual size of the port
        self.port_color_input = QColor("#2ECC71") # Green for input
        self.port_color_output = QColor("#E74C3C") # Red for output
        self.hovered_port_name = None
        self.hovered_port_type = None

        self.setAcceptHoverEvents(True) # To detect mouse hovering over ports

        self._dragging_from_port = None # Stores {'name': str, 'type': str, 'item': GraphicsPortItem (optional)}

    def update_display_text(self):
        # Updates the text displayed on the node (e.g., type or name)
        # You can choose to display node_type, name, or a combination
        display_text = f"{self.data_node.name}" # Or self.data_node.node_type
        if len(display_text) > 18: # Simple truncation
            display_text = display_text[:17] + "..."

        self.title_item.setPlainText(display_text)
        self.title_item.setDefaultTextColor(self.text_color) # Ensure color is set
        self.title_item.setFont(self.font) # Ensure font is set

        # Recenter title
        title_rect = self.title_item.boundingRect()
        self.title_item.setPos((self.width - title_rect.width()) / 2, 5)
        self.update() # Request a repaint of the node

    def boundingRect(self):
        # Defines the outer boundary of the item, important for collision detection and redraws
        return QRectF(0, 0, self.width, self.height)


    def get_port_item_rect(self, port_info):
        """Calculates the QRectF for a given port_info dictionary in local coordinates."""
        y_offset = self.height / 2 # Default center
        port_name = port_info["name"]
        port_type = port_info["type"]

        if port_type == "input":
            num_ports = len(self.data_node.input_ports)
            idx = next((i for i, p in enumerate(self.data_node.input_ports) if p["name"] == port_name), 0)
            y_offset = (self.height / (num_ports + 1)) * (idx + 1)
            return QRectF(-self.port_radius, y_offset - self.port_radius,
                          2 * self.port_radius, 2 * self.port_radius)
        elif port_type == "output":
            num_ports = len(self.data_node.output_ports)
            idx = next((i for i, p in enumerate(self.data_node.output_ports) if p["name"] == port_name), 0)
            if self.data_node.node_type == "Conditional (If/Else)" and num_ports == 2:
                 y_offset = (self.height / 3) * (idx + 1)
            elif num_ports > 0 : # handles single or multiple generic outputs
                 y_offset = (self.height / (num_ports + 1)) * (idx + 1)

            return QRectF(self.width - self.port_radius, y_offset - self.port_radius,
                          2 * self.port_radius, 2 * self.port_radius)
        return QRectF()

    def paint(self, painter: QPainter, option, widget=None):
        # Draw the node's background (existing code)
        path_outline = QRectF(0, 0, self.width, self.height)
        painter.setBrush(QBrush(self.color))
        painter.setPen(QPen(self.border_color, 1))
        painter.drawRoundedRect(path_outline, 5, 5)

        # Draw Title (QGraphicsTextItem handles this, already added as child)

        # --- NEW: Draw Ports ---
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        # Draw Input Ports
        for port_info in self.data_node.input_ports:
            rect = self.get_port_item_rect(port_info)
            painter.setBrush(QBrush(self.port_color_input))
            if self.hovered_port_name == port_info["name"] and self.hovered_port_type == "input":
                painter.setBrush(QBrush(self.port_color_input.lighter(130)))
            painter.drawEllipse(rect)

        # Draw Output Ports
        for port_info in self.data_node.output_ports:
            rect = self.get_port_item_rect(port_info)
            painter.setBrush(QBrush(self.port_color_output))
            if self.hovered_port_name == port_info["name"] and self.hovered_port_type == "output":
                 painter.setBrush(QBrush(self.port_color_output.lighter(130)))
            painter.drawEllipse(rect)
            
        # Highlight if selected (existing code)
        if self.isSelected():
            pen = QPen(QColor(Qt.GlobalColor.yellow), 2)
            painter.setPen(pen)
            painter.drawRoundedRect(self.boundingRect().adjusted(-1,-1,1,1), 5, 5)

    def get_port_at_pos(self, pos: QPointF):
        """Checks if a point (in local coords) is over any port."""
        for port_info in self.data_node.input_ports + self.data_node.output_ports:
            rect = self.get_port_item_rect(port_info)
            if rect.contains(pos):
                return port_info
        return None

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
        pos = event.pos() # Position in local coordinates of the node
        hovered_port = self.get_port_at_pos(pos)
        
        new_hovered_name = hovered_port["name"] if hovered_port else None
        new_hovered_type = hovered_port["type"] if hovered_port else None

        if self.hovered_port_name != new_hovered_name or self.hovered_port_type != new_hovered_type:
            self.hovered_port_name = new_hovered_name
            self.hovered_port_type = new_hovered_type
            self.update() # Trigger repaint for hover effect
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
        if self.hovered_port_name is not None:
            self.hovered_port_name = None
            self.hovered_port_type = None
            self.update() # Trigger repaint to remove hover effect
        super().hoverLeaveEvent(event)
        
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        pos = event.pos()
        port_info = self.get_port_at_pos(pos)

        if port_info and port_info["type"] == "output": # Start dragging from an output port
            self._dragging_from_port = port_info
            scene_pos = self.mapToScene(self.get_port_item_rect(port_info).center())
            self.port_drag_started.emit(self, port_info["name"], scene_pos)
            event.accept() # Consume event so node doesn't move
            return 
        elif port_info and port_info["type"] == "input": # Clicked on input port (for completing a drag)
            # This case will be handled by the FlowCanvas when a drag is active
            event.accept()
            return

        self._dragging_from_port = None # Reset if not dragging from port
        super().mousePressEvent(event) # Default behavior (select/move node)


    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging_from_port:
            # The actual line drawing will be handled by FlowCanvas/MainWindow
            # This event is consumed if we started dragging from a port
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging_from_port:
            # Check if mouse is over another port on release
            # This logic will primarily be in FlowCanvas which has access to all items
            # For now, emit a generic "ended on nothing" if we just release here
            # More robust: FlowCanvas checks itemAt(event.scenePos())
            
            # To find target item/port properly, FlowCanvas needs to handle this release
            # For simplicity here, we assume FlowCanvas will handle the drop check
            # The GraphicsNode itself doesn't know about other nodes.
            self.port_drag_ended_on_nothing.emit() # Placeholder
            self._dragging_from_port = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.data_node.position = self.pos()
            self.node_moved.emit(self.data_node.id) # EMIT THE NEW SIGNAL
            
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:
                self.node_selected.emit(self.data_node)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        print(f"Node '{self.data_node.name}' double-clicked!")
        super().mouseDoubleClickEvent(event)


# --- Phase 3: Flow Canvas (QGraphicsView & QGraphicsScene) ---
class FlowCanvas(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, main_window_ref, parent=None): # Added main_window_ref
        super().__init__(scene, parent)
        self.main_window_ref = main_window_ref # Store the reference
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # Initialize the missing attribute
        self._middle_mouse_pressed = False # <--- ADD THIS LINE
        # --- NEW: For Connection Drawing ---
        self.temp_connection_line = None
        self.dragging_connection_from_node = None # The GraphicsNode instance
        self.dragging_connection_from_port_name = None # Name of the output port
        self.start_drag_scene_pos = None


    def wheelEvent(self, event):
        # Zoom functionality
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._middle_mouse_pressed = True
            self._last_middle_mouse_pos = event.pos()
        super().mousePressEvent(event)

    def start_connection_drag(self, source_graphics_node: GraphicsNode, port_name: str, port_scene_pos: QPointF):
        if self.temp_connection_line: # Should not happen, but cleanup if it does
            self.scene().removeItem(self.temp_connection_line)
            self.temp_connection_line = None

        self.dragging_connection_from_node = source_graphics_node
        self.dragging_connection_from_port_name = port_name
        self.start_drag_scene_pos = port_scene_pos

        # Create a temporary line for visual feedback
        path = QPainterPath(self.start_drag_scene_pos)
        path.lineTo(self.start_drag_scene_pos) # Initially a point
        self.temp_connection_line = QGraphicsPathItem(path)
        self.temp_connection_line.setPen(QPen(Qt.GlobalColor.cyan, 2, Qt.PenStyle.DashLine))
        self.scene().addItem(self.temp_connection_line)
        print(f"Connection drag started from {source_graphics_node.data_node.name}.{port_name}")

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent): # Make sure this is QGraphicsSceneMouseEvent
        if self.temp_connection_line:
            # We are dragging a connection
            current_scene_pos = self.mapToScene(event.pos()) # Map viewport pos to scene pos
            path = QPainterPath(self.start_drag_scene_pos)
            
            # Simple straight line for now, can be Bezier curve later
            # Calculate control points for a smoother curve (optional for now)
            # mid_x = (self.start_drag_scene_pos.x() + current_scene_pos.x()) / 2
            # control1 = QPointF(mid_x, self.start_drag_scene_pos.y())
            # control2 = QPointF(mid_x, current_scene_pos.y())
            # path.cubicTo(control1, control2, current_scene_pos)
            path.lineTo(current_scene_pos)

            self.temp_connection_line.setPath(path)
            event.accept() # Consume event
            return
        
        # Handle middle mouse panning if not dragging connection
        if self._middle_mouse_pressed and event.buttons() & Qt.MouseButton.MiddleButton:
            delta = event.pos() - self._last_middle_mouse_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._last_middle_mouse_pos = event.pos()
            event.accept() # Consume event
            return

        super().mouseMoveEvent(event) # Default behavior for other cases

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent): # Make sure this is QGraphicsSceneMouseEvent
        if self.temp_connection_line and self.dragging_connection_from_node:
            # We were dragging a connection
            current_scene_pos = self.mapToScene(event.pos())
            self.scene().removeItem(self.temp_connection_line)
            self.temp_connection_line = None

            # Check if we dropped on a valid target port
            item_at_drop = self.itemAt(event.pos()) # event.pos() is viewport coords

            target_graphics_node = None
            target_port_name = None

            if isinstance(item_at_drop, GraphicsNode):
                target_graphics_node = item_at_drop
                # Convert drop pos to target node's local coordinates
                local_pos_on_target = target_graphics_node.mapFromScene(current_scene_pos)
                port_info = target_graphics_node.get_port_at_pos(local_pos_on_target)
                if port_info and port_info["type"] == "input":
                    # Check if not connecting to self output (unless allowed)
                    if target_graphics_node != self.dragging_connection_from_node:
                        target_port_name = port_info["name"]
                    # else: print("Cannot connect node to its own input via its output port in this simple setup")
            
            if target_graphics_node and target_port_name:
                print(f"Connection attempt from {self.dragging_connection_from_node.data_node.name}.{self.dragging_connection_from_port_name} to {target_graphics_node.data_node.name}.{target_port_name}")
                # Emit a signal or call a MainWindow method to create the actual connection
                # For now, we'll just print. The actual Connection object creation is next.
                self.main_window_ref.handle_connection_dropped( # NEW
                    self.dragging_connection_from_node.data_node.id,
                    self.dragging_connection_from_port_name,
                    target_graphics_node.data_node.id,
                    target_port_name
                )

            else:
                print("Connection drag ended on nothing valid.")

            self.dragging_connection_from_node = None
            self.dragging_connection_from_port_name = None
            self.start_drag_scene_pos = None
            event.accept()
            return

        # Handle middle mouse release
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self._middle_mouse_pressed = False
            event.accept()
            return

        super().mouseReleaseEvent(event)


class GraphicsConnectionItem(QGraphicsPathItem):
    def __init__(self, connection_data: Connection, 
                 source_graphics_node: GraphicsNode, 
                 target_graphics_node: GraphicsNode, 
                 parent=None):
        super().__init__(parent)
        self.connection_data = connection_data
        self.source_gnode = source_graphics_node
        self.target_gnode = target_graphics_node

        self.line_color = QColor(Qt.GlobalColor.white) # Or another visible color
        self.line_width = 2
        self.arrow_size = 10 # For drawing an arrowhead

        self.setZValue(-1) # Draw connections behind nodes

        self.update_path() # Initial path calculation

    def get_port_scene_pos(self, graphics_node: GraphicsNode, port_name: str, port_type: str):
        """Helper to get the scene position of a port on a given graphics node."""
        # data_node = graphics_node.data_node # Not actually used in this version of the helper

        port_rect_local = graphics_node.get_port_item_rect({"name": port_name, "type": port_type})
        if port_rect_local.isNull():
            print(f"Warning: Port rect is null for {graphics_node.data_node.name}, port {port_name} ({port_type})")
            return graphics_node.scenePos() # Fallback to node's origin
            
        port_center_local = port_rect_local.center()
        
        # Map local port center to scene coordinates
        return graphics_node.mapToScene(port_center_local)


    # def update_path(self):
    #     if not self.source_gnode or not self.target_gnode:
    #         return

    #     # Get scene positions of the source and target ports
    #     p1 = self.get_port_scene_pos(self.source_gnode, 
    #                                  self.connection_data.from_port_name, 
    #                                  "output")
    #     p2 = self.get_port_scene_pos(self.target_gnode, 
    #                                  self.connection_data.to_port_name, 
    #                                  "input")

    #     path = QPainterPath(p1)
        
    #     # --- Simple Straight Line ---
    #     # path.lineTo(p2)

    #     # --- Simple Curved Line (Cubic Bezier) ---
    #     # Adjust dx for how much the curve bows out
    #     dx = abs(p2.x() - p1.x()) * 0.5 
    #     # If p1 and p2 are very close vertically, reduce dx to avoid extreme curves
    #     if abs(p2.y() - p1.y()) < self.source_gnode.height / 2 :
    #          dx = abs(p2.x() - p1.x()) * 0.25

    #     # Control points: one extending horizontally from source, one from target
    #     c1 = QPointF(p1.x() + dx, p1.y())
    #     c2 = QPointF(p2.x() - dx, p2.y())
    #     path.cubicTo(c1, c2, p2)
        
    #     # --- Draw Arrowhead (Optional) ---
    #     # angle = math.atan2(p2.y() - c2.y(), p2.x() - c2.x()) # Angle of the curve end
    #     # arrow_p1 = p2 + QPointF(math.sin(angle - math.pi / 3) * self.arrow_size,
    #     #                         math.cos(angle - math.pi / 3) * self.arrow_size)
    #     # arrow_p2 = p2 + QPointF(math.sin(angle - math.pi + math.pi / 3) * self.arrow_size,
    #     #                         math.cos(angle - math.pi + math.pi / 3) * self.arrow_size)
    #     # path.moveTo(arrow_p1)
    #     # path.lineTo(p2)
    #     # path.lineTo(arrow_p2)
    #     # --- End Arrowhead ---

    #     p1 = self.get_port_scene_pos(...)
    #     p2 = self.get_port_scene_pos(...)
    #     print(f"Conn {self.connection_data.id[-6:]}: Updating path from {p1} to {p2} for nodes {self.source_gnode.data_node.name} -> {self.target_gnode.data_node.name}")


    #     self.setPath(path)
    #     self.setPen(QPen(self.line_color, self.line_width))

    def update_path(self):
        if not self.source_gnode or not self.target_gnode:
            print("Update_path: Missing source or target gnode") # Debug
            return

        # Get scene positions of the source and target ports
        p1 = self.get_port_scene_pos(self.source_gnode, 
                                     self.connection_data.from_port_name, 
                                     "output")
        p2 = self.get_port_scene_pos(self.target_gnode, 
                                     self.connection_data.to_port_name, 
                                     "input")
        
        # This is the debug print statement using the p1 and p2 calculated above
        print(f"Conn {self.connection_data.id[-6:]}: Updating path from {p1} to {p2} for nodes {self.source_gnode.data_node.name} -> {self.target_gnode.data_node.name}")

        path = QPainterPath(p1)
        
        dx = abs(p2.x() - p1.x()) * 0.5 
        if abs(p2.y() - p1.y()) < self.source_gnode.height / 2 :
             dx = abs(p2.x() - p1.x()) * 0.25

        c1 = QPointF(p1.x() + dx, p1.y())
        c2 = QPointF(p2.x() - dx, p2.y())
        path.cubicTo(c1, c2, p2)
        
        self.setPath(path) 
        self.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine)) # Explicitly set pen here
        self.update()


    def paint(self, painter, option, widget=None):
        # If you want selection highlight for connections:
        # if self.isSelected():
        #     selection_pen = QPen(Qt.GlobalColor.yellow, self.line_width + 2)
        #     painter.setPen(selection_pen)
        #     painter.drawPath(self.path())
        #     # Then reset pen for actual drawing or let superclass handle it with current pen
        super().paint(painter, option, widget)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Visual Bot Creator")
        self.setGeometry(100, 100, 1200, 700) # Adjusted default height slightly

        self.current_flow = Flow()
        self.graphics_nodes = {}
        self.selected_data_node = None
        
        self.graphics_connections = {} # Store GraphicsConnectionItem by connection_data.id

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)

        self.node_palette = QListWidget()
        self.node_palette.setFixedWidth(200)
        self.populate_node_palette()
        self.node_palette.itemDoubleClicked.connect(self.add_node_from_palette)
        main_splitter.addWidget(self.node_palette)

        right_area_splitter = QSplitter(Qt.Orientation.Vertical)

        self.scene = QGraphicsScene()
        self.scene.setSceneRect(-2000, -2000, 4000, 4000)
        self.flow_canvas = FlowCanvas(self.scene, self) # Pass 'self' (MainWindow instance)
        right_area_splitter.addWidget(self.flow_canvas)

        # --- Create an instance of the event filter ---
        self.spinbox_wheel_filter = SpinBoxWheelEventFilter(self) # Parent to MainWindow

        # --- Properties Panel with ScrollArea ---
        self.properties_scroll_area = QScrollArea()
        self.properties_scroll_area.setWidgetResizable(True)
        self.properties_scroll_area.setMinimumHeight(200)
        self.properties_scroll_area.setMaximumHeight(400)

        self.properties_panel_widget_internal = QWidget()
        self.properties_layout = QFormLayout(self.properties_panel_widget_internal)
        self.properties_layout.setContentsMargins(10, 10, 10, 10)
        self.properties_layout.setSpacing(7)

        self.properties_scroll_area.setWidget(self.properties_panel_widget_internal)
        
        right_area_splitter.addWidget(self.properties_scroll_area)

        main_splitter.addWidget(right_area_splitter)
        main_splitter.setSizes([200, 1000])
        # Adjust splitter sizes if needed, e.g., give properties panel a bit more space by default
        right_area_splitter.setSizes([self.height() - 280, 250]) # Example dynamic sizing, adjust 280/250

        self.update_properties_panel(None)

        print("Initialized new Flow:", self.current_flow)

    def populate_node_palette(self):
        available_nodes = [
            "Start", "End", "Find Window", "Find Image",
            "Mouse Action", "Keyboard Action", "Delay/Wait",
            "Conditional (If/Else)", "Log Message"
        ]
        for node_name in available_nodes:
            self.node_palette.addItem(node_name)

    def add_node_from_palette(self, item: QListWidgetItem):
        node_type = item.text()
        
        default_props = {}
        if node_type == "Log Message":
            default_props["message"] = "Default log message"
        elif node_type == "Delay/Wait":
            default_props["duration_ms"] = 1000
        elif node_type == "Find Image":
            default_props["image_path"] = ""
            default_props["confidence"] = 0.8
            default_props["search_mode"] = "FullScreen"
            default_props["search_rect_x"] = 0
            default_props["search_rect_y"] = 0
            default_props["search_rect_w"] = 100
            default_props["search_rect_h"] = 100
        
        new_data_node = Node(node_type=node_type, name=node_type,
                             position=(len(self.current_flow.nodes) * 50 % 500, (len(self.current_flow.nodes) // 10) * 100),
                             properties=default_props)
        
        self.current_flow.add_node(new_data_node)

        graphics_node = GraphicsNode(new_data_node)
        graphics_node.node_selected.connect(self.handle_node_selection)
        graphics_node.port_drag_started.connect(self.flow_canvas.start_connection_drag)
        graphics_node.node_moved.connect(self.update_connections_for_node) # CONNECT NEW SIGNAL

        self.scene.addItem(graphics_node)
        self.graphics_nodes[new_data_node.id] = graphics_node

        print(f"Added node '{new_data_node.name}' (Type: {new_data_node.node_type}) with properties: {new_data_node.properties}")

    def update_connections_for_node(self, moved_node_id: str):
        print(f"MainWindow: Updating connections for moved node {moved_node_id}") # <--- Ensure this is active
        for conn_id, g_conn_item in self.graphics_connections.items():
            if (g_conn_item.connection_data.from_node_id == moved_node_id or
                g_conn_item.connection_data.to_node_id == moved_node_id):
                print(f"    Updating path for connection: {g_conn_item.connection_data.id}") # <--- And this
                g_conn_item.update_path()


    def handle_connection_dropped(self, from_node_id, from_port_name, to_node_id, to_port_name):
        print(f"MainWindow: Creating connection from {from_node_id}.{from_port_name} to {to_node_id}.{to_port_name}")
        
        from_node_data = self.current_flow.get_node(from_node_id)
        to_node_data = self.current_flow.get_node(to_node_id)

        if not from_node_data or not to_node_data:
            print("Error: One or both nodes not found in data model.")
            return

        # Basic validation: Don't connect a node to itself via same port type (e.g. output to output)
        if from_node_id == to_node_id:
            print("Warning: Self-connections should be handled carefully (not fully supported here).")
            # You might want to allow this for specific scenarios, but often it's disallowed.
            # For now, let's disallow direct output-to-input self-connection for simplicity.
            # return 

        # Prevent duplicate connections (same source port to same target port)
        for conn_id, g_conn_item in self.graphics_connections.items():
            if (g_conn_item.connection_data.from_node_id == from_node_id and
                g_conn_item.connection_data.from_port_name == from_port_name and
                g_conn_item.connection_data.to_node_id == to_node_id and
                g_conn_item.connection_data.to_port_name == to_port_name):
                print("Warning: This exact connection already exists.")
                return
        
        # Prevent an input port from having more than one incoming connection (typical for sequential flow)
        for conn_id, g_conn_item in self.graphics_connections.items():
            if (g_conn_item.connection_data.to_node_id == to_node_id and
                g_conn_item.connection_data.to_port_name == to_port_name):
                print(f"Warning: Input port {to_node_id}.{to_port_name} is already connected. Replacing.")
                # Remove the old connection visually and from data model
                self.scene.removeItem(g_conn_item)
                del self.graphics_connections[conn_id]
                # Also remove from self.current_flow.connections
                self.current_flow.connections = [
                    c for c in self.current_flow.connections if c.id != g_conn_item.connection_data.id
                ]
                break # Assuming only one connection per input port is allowed

        # Create data model connection
        new_connection_data = Connection(from_node_id, from_port_name, to_node_id, to_port_name)
        self.current_flow.add_connection(new_connection_data)
        print("Connection added to flow model:", new_connection_data)

        # --- NEW: Create GraphicsConnectionItem ---
        source_gnode = self.graphics_nodes.get(from_node_id)
        target_gnode = self.graphics_nodes.get(to_node_id)

        if source_gnode and target_gnode:
            graphics_conn = GraphicsConnectionItem(new_connection_data, source_gnode, target_gnode)
            self.scene.addItem(graphics_conn)
            self.graphics_connections[new_connection_data.id] = graphics_conn
            print(f"GraphicsConnectionItem created and added to scene for {new_connection_data.id}")
        else:
            print("Error: Could not find source or target GraphicsNode for visual connection.")

    def handle_node_selection(self, data_node: Node):
        self.selected_data_node = data_node # Store the selected data node
        self.update_properties_panel(data_node)

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout()) # Recursively clear nested layouts

    def update_properties_panel(self, data_node: Node):
        self.clear_layout(self.properties_layout)

        if data_node is None:
            self.properties_layout.addRow(QLabel("No node selected."))
            return

        # ... (General Properties, Name Edit) ...
        self.properties_layout.addRow(QLabel(f"<b>Type:</b> {data_node.node_type}"))
        self.properties_layout.addRow(QLabel(f"<b>ID:</b> {data_node.id}"))

        name_edit = QLineEdit(data_node.name)
        name_edit.textChanged.connect(lambda text, dn=data_node: self.update_node_name(dn, text))
        self.properties_layout.addRow("Name:", name_edit)


        if data_node.node_type == "Log Message":
            msg_edit = QLineEdit(data_node.properties.get("message", ""))
            msg_edit.textChanged.connect( lambda text, dn=data_node: self.update_node_property(dn, "message", text) )
            self.properties_layout.addRow("Message:", msg_edit)

        elif data_node.node_type == "Delay/Wait":
            duration_spinbox = QSpinBox()
            duration_spinbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Keep this for keyboard focus behavior
            duration_spinbox.installEventFilter(self.spinbox_wheel_filter) # <--- INSTALL FILTER
            duration_spinbox.setRange(0, 600000)
            duration_spinbox.setSuffix(" ms")
            duration_spinbox.setValue(data_node.properties.get("duration_ms", 1000))
            duration_spinbox.valueChanged.connect(lambda val, dn=data_node: self.update_node_property(dn, "duration_ms", val))
            self.properties_layout.addRow("Duration:", duration_spinbox)

        elif data_node.node_type == "Find Image":
            # ... (Image Path layout) ...
            path_layout = QHBoxLayout()
            path_edit = QLineEdit(data_node.properties.get("image_path", ""))
            path_edit.setReadOnly(True)
            browse_button = QPushButton("Browse...")
            def browse_image_for_node(dn=data_node, pe=path_edit): self.browse_image(dn, pe)
            browse_button.clicked.connect(browse_image_for_node)
            path_layout.addWidget(path_edit)
            path_layout.addWidget(browse_button)
            self.properties_layout.addRow("Image Path:", path_layout)


            confidence_spinbox = QSpinBox()
            confidence_spinbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Keep for keyboard
            confidence_spinbox.installEventFilter(self.spinbox_wheel_filter) # <--- INSTALL FILTER
            confidence_spinbox.setRange(0, 100)
            confidence_spinbox.setValue(int(data_node.properties.get("confidence", 0.8) * 100))
            confidence_spinbox.setSuffix(" %")
            def update_confidence(val, dn=data_node): self.update_node_property(dn, "confidence", val / 100.0)
            confidence_spinbox.valueChanged.connect(update_confidence)
            self.properties_layout.addRow("Confidence:", confidence_spinbox)

            self.properties_layout.addRow(QLabel("<b>Search Region:</b>"))
            search_mode_combo = QComboBox()
            # ... (search_mode_combo setup as before) ...
            search_modes = ["FullScreen", "Rectangle"] # Ensure this is defined
            search_mode_combo.addItems(search_modes)
            current_search_mode = data_node.properties.get("search_mode", "FullScreen")
            search_mode_combo.setCurrentText(current_search_mode)


            rect_coords_widget = QWidget()
            rect_layout = QFormLayout(rect_coords_widget)
            rect_layout.setContentsMargins(0,0,0,0)

            sr_x_spin = QSpinBox()
            sr_x_spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Keep for keyboard
            sr_x_spin.installEventFilter(self.spinbox_wheel_filter) # <--- INSTALL FILTER
            sr_x_spin.setRange(-10000, 10000)
            sr_x_spin.setValue(data_node.properties.get("search_rect_x", 0))
            sr_x_spin.valueChanged.connect(lambda val, dn=data_node: self.update_node_property(dn, "search_rect_x", val))
            rect_layout.addRow("Rect X:", sr_x_spin)

            sr_y_spin = QSpinBox()
            sr_y_spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Keep for keyboard
            sr_y_spin.installEventFilter(self.spinbox_wheel_filter) # <--- INSTALL FILTER
            sr_y_spin.setRange(-10000, 10000)
            sr_y_spin.setValue(data_node.properties.get("search_rect_y", 0))
            sr_y_spin.valueChanged.connect(lambda val, dn=data_node: self.update_node_property(dn, "search_rect_y", val))
            rect_layout.addRow("Rect Y:", sr_y_spin)

            sr_w_spin = QSpinBox()
            sr_w_spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Keep for keyboard
            sr_w_spin.installEventFilter(self.spinbox_wheel_filter) # <--- INSTALL FILTER
            sr_w_spin.setRange(1, 10000)
            sr_w_spin.setValue(data_node.properties.get("search_rect_w", 100))
            sr_w_spin.valueChanged.connect(lambda val, dn=data_node: self.update_node_property(dn, "search_rect_w", val))
            rect_layout.addRow("Rect W:", sr_w_spin)

            sr_h_spin = QSpinBox()
            sr_h_spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Keep for keyboard
            sr_h_spin.installEventFilter(self.spinbox_wheel_filter) # <--- INSTALL FILTER
            sr_h_spin.setRange(1, 10000)
            sr_h_spin.setValue(data_node.properties.get("search_rect_h", 100))
            sr_h_spin.valueChanged.connect(lambda val, dn=data_node: self.update_node_property(dn, "search_rect_h", val))
            rect_layout.addRow("Rect H:", sr_h_spin)
            
            def on_search_mode_change(index, dn=data_node, rc_w=rect_coords_widget):
                mode = search_modes[index]
                self.update_node_property(dn, "search_mode", mode)
                rc_w.setVisible(mode == "Rectangle")

            search_mode_combo.currentIndexChanged.connect(on_search_mode_change)
            self.properties_layout.addRow("Search Mode:", search_mode_combo)
            self.properties_layout.addRow(rect_coords_widget)
            rect_coords_widget.setVisible(current_search_mode == "Rectangle")

        self.properties_layout.addRow(QLabel(f"Pos: ({data_node.position.x():.0f}, {data_node.position.y():.0f})"))
        # self.properties_panel_widget_internal.adjustSize() # May help ensure scrollbar appears if needed

    def update_node_name(self, data_node: Node, new_name: str):
        data_node.name = new_name
        graphics_node = self.graphics_nodes.get(data_node.id)
        if graphics_node:
            graphics_node.update_display_text() # Call the new method
        print(f"Node '{data_node.id}' name changed to: {data_node.name}")


    def update_node_property(self, data_node: Node, key: str, value):
        data_node.properties[key] = value
        print(f"Node '{data_node.name}' property '{key}' changed to: {value}")
        # Potentially update visual representation or re-validate node if needed


    def browse_image(self, data_node: Node, path_edit_widget: QLineEdit):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Image", "", 
                                                   "Image Files (*.png *.jpg *.bmp)")
        if file_name:
            self.update_node_property(data_node, "image_path", file_name)
            path_edit_widget.setText(file_name)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())