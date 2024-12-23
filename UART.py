import sys
import serial
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox, QLineEdit, QHBoxLayout
from PyQt5.QtCore import QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from serial.tools import list_ports

# 数据窗口大小
WINDOW_SIZE = 500  # 绘图数据缓冲区大小

# 自动检测可用串口
def get_available_ports():
    ports = list_ports.comports()
    return [port.device for port in ports]

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 窗口设置
        self.setWindowTitle("串口波形显示软件 - v1.6")
        self.setGeometry(100, 100, 800, 600)

        # 主布局
        layout = QVBoxLayout()

        # 串口选择区域
        self.port_label = QLabel("选择串口:")
        layout.addWidget(self.port_label)

        self.port_combo = QComboBox()
        self.ports = get_available_ports()
        if self.ports:
            self.port_combo.addItems(self.ports)
            self.selected_port = self.ports[0]
        else:
            self.port_combo.addItem("无可用串口")
            self.selected_port = None
        self.port_combo.currentIndexChanged.connect(self.update_selected_port)
        layout.addWidget(self.port_combo)

        # 串口参数设置
        self.baudrate_label = QLabel("波特率:")
        layout.addWidget(self.baudrate_label)

        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(["9600", "19200", "38400", "57600", "115200", "128000", "256000"])
        self.baudrate_combo.setCurrentText("115200")  # 默认波特率
        layout.addWidget(self.baudrate_combo)

        self.databits_label = QLabel("数据位:")
        layout.addWidget(self.databits_label)

        self.databits_combo = QComboBox()
        self.databits_combo.addItems(["5", "6", "7", "8"])
        self.databits_combo.setCurrentText("8")
        layout.addWidget(self.databits_combo)

        self.stopbits_label = QLabel("停止位:")
        layout.addWidget(self.stopbits_label)

        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])
        self.stopbits_combo.setCurrentText("1")
        layout.addWidget(self.stopbits_combo)

        self.parity_label = QLabel("校验位:")
        layout.addWidget(self.parity_label)

        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["无", "奇", "偶"])
        self.parity_combo.setCurrentText("无")
        layout.addWidget(self.parity_combo)

        self.flowcontrol_label = QLabel("流控:")
        layout.addWidget(self.flowcontrol_label)

        self.flowcontrol_combo = QComboBox()
        self.flowcontrol_combo.addItems(["无", "硬件", "软件"])
        self.flowcontrol_combo.setCurrentText("无")
        layout.addWidget(self.flowcontrol_combo)

        # 状态显示标签
        self.status_label = QLabel("状态: 未连接")
        layout.addWidget(self.status_label)

        # 波形显示画布
        self.canvas_widget = QWidget()
        self.canvas_layout = QVBoxLayout(self.canvas_widget)
        self.plot_canvas = PlotCanvas(self, width=8, height=5)
        self.canvas_layout.addWidget(self.plot_canvas)
        layout.addWidget(self.canvas_widget)

        # 控制按钮
        button_layout = QHBoxLayout()

        self.start_button = QPushButton("开始")
        self.start_button.clicked.connect(self.start_reading)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.stop_reading)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

        # 保存数据按钮
        self.save_button = QPushButton("保存数据")
        self.save_button.clicked.connect(self.save_data)
        layout.addWidget(self.save_button)

        # 设置中心小部件
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 定时器用于更新波形
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)

        # 数据缓冲区
        self.data_buffer = []
        self.ser = None

    # 更新选中的串口
    def update_selected_port(self, index):
        self.selected_port = self.port_combo.currentText()

    # 开始读取串口数据
    def start_reading(self):
        if self.selected_port:
            try:
                # 配置串口参数
                baudrate = int(self.baudrate_combo.currentText())
                databits = int(self.databits_combo.currentText())
                stopbits = float(self.stopbits_combo.currentText())
                parity = self.parity_combo.currentText()
                if parity == "无":
                    parity = serial.PARITY_NONE
                elif parity == "奇":
                    parity = serial.PARITY_ODD
                elif parity == "偶":
                    parity = serial.PARITY_EVEN

                self.ser = serial.Serial(
                    self.selected_port,
                    baudrate=baudrate,
                    bytesize=databits,
                    stopbits=stopbits,
                    parity=parity,
                    timeout=1
                )

                self.status_label.setText(f"状态: 已连接到 {self.selected_port}，波特率: {baudrate}")
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(True)
                self.timer.start(50)  # 设置定时器间隔，单位为毫秒
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法连接到 {self.selected_port}: {e}")
        else:
            QMessageBox.warning(self, "警告", "未选择串口。")

    # 停止读取串口数据
    def stop_reading(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.status_label.setText("状态: 未连接")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.timer.stop()

    # 更新波形显示
    def update_plot(self):
        if self.ser and self.ser.in_waiting > 0:
            try:
                raw_data = self.ser.readline().decode('utf-8').strip()  # 从串口读取一行数据
                value = float(raw_data)  # 转换为浮点数
                self.data_buffer.append(value)
                if len(self.data_buffer) > WINDOW_SIZE:
                    self.data_buffer.pop(0)
                self.plot_canvas.update_data(self.data_buffer)  # 更新波形
            except Exception as e:
                print(f"读取串口数据时出错: {e}")

    # 保存波形数据到文件
    def save_data(self):
        if self.data_buffer:
            file_path, _ = QFileDialog.getSaveFileName(self, "保存数据", "", "CSV 文件 (*.csv)")
            if file_path:
                try:
                    with open(file_path, 'w') as f:
                        f.write("Value\n")
                        for value in self.data_buffer:
                            f.write(f"{value}\n")
                    QMessageBox.information(self, "成功", f"数据已保存到 {file_path}")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"保存数据时出错: {e}")
        else:
            QMessageBox.warning(self, "警告", "没有可保存的数据。")

class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.data = [0] * WINDOW_SIZE
        self.line, = self.ax.plot(self.data, 'b-')
        self.ax.set_ylim(0, 1000)  # 默认Y轴范围
        self.ax.set_xlim(0, WINDOW_SIZE)

    # 更新波形数据
    def update_data(self, data):
        self.ax.clear()
        self.ax.plot(data, 'b-')
        self.ax.set_ylim(min(data) - 10, max(data) + 10)
        self.ax.set_xlim(0, len(data))
        self.ax.set_title("串口数据波形")
        self.ax.set_xlabel("样本索引")
        self.ax.set_ylabel("值")
        self.draw()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
