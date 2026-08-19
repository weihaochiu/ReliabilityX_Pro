"""
IVMetaWidget: A widget for displaying measurement metadata.
"""
import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QLabel, QGridLayout
from PyQt6.QtCore import pyqtSlot

logger = logging.getLogger(__name__)

class IVMetaWidget(QWidget):
    """
    A widget that displays metadata for an IV measurement, such as device,
    user, project, and environmental conditions.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        meta_group = QGroupBox("元數據總覽")
        meta_group.setStyleSheet("""
            QGroupBox { 
                font-weight: bold; 
                border: 1px solid silver; 
                border-radius: 5px; 
                margin-top: 10px; 
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                left: 10px; 
                padding: 0 3px 0 3px; 
            }
        """)
        
        meta_grid = QGridLayout(meta_group)

        self.meta_labels = {}
        # Define fields and their grid positions (row, col, rowspan, colspan)
        meta_fields = {
            "User": (0, 0), "Project": (0, 2), "Device": (1, 0), "Channel": (1, 2),
            "Relay Info": (2, 0, 1, 4), 
            "Line Resistance": (3, 0, 1, 4), 
            "Scan Settings": (4, 0, 1, 4),
            "Environment": (5, 0, 1, 4), 
            "File Path": (6, 0, 1, 4)
        }

        for name, pos in meta_fields.items():
            label_title = QLabel(f"<b>{name}:</b>")
            label_value = QLabel("--")
            label_value.setWordWrap(True)
            
            # Unpack position with defaults for rowspan and colspan
            row, col, rowspan, colspan = (pos + (1, 1, 1, 1))[0:4]
            
            meta_grid.addWidget(label_title, row, col)
            meta_grid.addWidget(label_value, row, col + 1, rowspan, colspan -1 if colspan > 1 else 1)
            self.meta_labels[name] = label_value
        
        layout.addWidget(meta_group)

    @pyqtSlot(dict)
    def update_metadata(self, data):
        """
        Populates the metadata fields from a dictionary. Handles both
        pre-scan (incomplete) and post-scan (complete) data.
        """
        self.meta_labels["User"].setText(str(data.get('user', '--')))
        self.meta_labels["Project"].setText(str(data.get('project', '--')))
        self.meta_labels["Device"].setText(str(data.get('device_name', '--')))
        self.meta_labels["Channel"].setText(str(data.get('ch_id', '--')))
        
        relay_str = f"Pos: {data.get('relay_pos', '--')} / Neg: {data.get('relay_neg', '--')}"
        self.meta_labels["Relay Info"].setText(relay_str)

        # Handle potentially missing pre-scan data
        rline_val = data.get('line_res')
        rline_date = data.get('line_res_date', '')
        if isinstance(rline_val, (int, float)):
            rline_str = f"{rline_val:.4f} Ω (on {rline_date})"
        else:
            rline_str = "未校準 (Uncalibrated)"
        self.meta_labels["Line Resistance"].setText(rline_str)

        scan_str = f"Start: {data.get('v_start', '--')}V, Stop: {data.get('v_stop', '--')}V, Step: {data.get('v_step', '--')}V, Delay: {data.get('delay_time', '--')}ms"
        self.meta_labels["Scan Settings"].setText(scan_str)
        
        temp = data.get('temp')
        hum = data.get('hum')
        if temp is not None and hum is not None:
            env_str = f"{temp:.2f}°C / {hum:.2f}% RH"
        else:
            env_str = "待測" # Not measured yet
        self.meta_labels["Environment"].setText(env_str)
        
        # Display predicted path before scan, and final path after scan
        file_path_str = data.get('file_path', '待產生')
        self.meta_labels["File Path"].setText(str(file_path_str))



    def clear(self):
        """Clears all metadata fields."""
        for label in self.meta_labels.values():
            label.setText("--")
