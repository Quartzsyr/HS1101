import sys
import serial
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, QHBoxLayout, QComboBox, QFileDialog
from PyQt5.QtCore import QTimer, Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from serial.tools import list_ports  # 自动列出可用串口

# 数据窗口大小
WINDOW_SIZE = 200  # 实时波形窗口大小
history_data = []  # 历史数据存储
breathing_rate_buffer = []  # 呼吸频率滑动窗口（用于平滑呼吸频率）
# 呼吸频率范围
MIN_BREATHING_RATE = 12
MAX_BREATHING_RATE = 20
# 波形变化阈值
BREATH_THRESHOLD = 50  # 波形变化阈值，视为一次呼吸
#波形坐标轴自适应阈值
AutoTH = 0

# 自动检测可用串口
def get_available_ports():
    ports = list_ports.comports()
    return [port.device for port in ports]

# 主窗口类
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 窗口设置
        self.setWindowTitle("HS1101呼吸频率测量 by 石殷睿")  # 修改窗口标题
        self.setGeometry(100, 100, 800, 600)

        # 创建主控件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 创建布局
        main_layout = QVBoxLayout(self.central_widget)

        # 串口选择下拉菜单
        self.port_label = QLabel("选择串口:", self)
        self.port_label.setStyleSheet("font-size: 16px;")
        main_layout.addWidget(self.port_label)

        self.port_combo = QComboBox(self)
        self.ports = get_available_ports()
        if self.ports:
            self.port_combo.addItems(self.ports)
            self.selected_port = self.ports[0]  # 默认选择第一个串口
        else:
            self.port_combo.addItem("无可用串口")
            self.selected_port = None
        self.port_combo.currentIndexChanged.connect(self.update_selected_port)
        main_layout.addWidget(self.port_combo)

        # 显示学号和姓名
        self.info_label = QLabel("学号: 2228410216  姓名: 石殷睿", self)
        self.info_label.setStyleSheet("font-size: 16px; color: purple;")
        self.info_label.setAlignment(Qt.AlignCenter)  # 居中显示
        main_layout.addWidget(self.info_label)

        # 实时数据显示标签
        self.frequency_label = QLabel("当前频率: -- kHz", self)
        self.frequency_label.setStyleSheet("font-size: 16px; color: red;")
        main_layout.addWidget(self.frequency_label)

        # 呼吸频率显示标签
        self.breathing_rate_label = QLabel("呼吸频率: -- breaths/min", self)
        self.breathing_rate_label.setStyleSheet("font-size: 16px; color: green;")
        main_layout.addWidget(self.breathing_rate_label)

        # 呼吸状态显示标签
        self.breathing_status_label = QLabel("呼吸状态: --", self)
        self.breathing_status_label.setStyleSheet("font-size: 16px; color: black;")
        main_layout.addWidget(self.breathing_status_label)

        # 实时波形画布
        self.real_time_canvas = PlotCanvas(self, width=8, height=5)
        main_layout.addWidget(self.real_time_canvas)

        # 添加按钮布局
        button_layout = QHBoxLayout()
        self.history_button = QPushButton("显示历史波形")
        self.history_button.clicked.connect(self.show_history)
        button_layout.addWidget(self.history_button)

        # 添加保存按钮
        self.save_button = QPushButton("导出为图片或CSV文件")
        self.save_button.clicked.connect(self.save_waveform_and_data)
        button_layout.addWidget(self.save_button)

        main_layout.addLayout(button_layout)

        # 定时器用于实时更新
        self.timer = QTimer()
        self.timer.setInterval(50)  # 更新间隔减少到 50ms
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

        # 打开默认串口
        self.ser = None
        self.open_serial_port()

    # 打开串口
    def open_serial_port(self):
        if self.selected_port:
            try:
                self.ser = serial.Serial(self.selected_port, 115200, timeout=1)
                print(f"Connected to {self.selected_port}")
            except Exception as e:
                print(f"Failed to connect to {self.selected_port}: {e}")
        else:
            print("No available ports to connect.")

    # 更新选中的串口
    def update_selected_port(self, index):
        self.selected_port = self.port_combo.currentText()
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.open_serial_port()

    # 更新实时波形
    def update_plot(self):
        global history_data
        if self.ser and self.ser.in_waiting > 0:  # 检查串口是否有数据
            try:
                # 读取串口数据
                raw_data = self.ser.readline().decode('utf-8').strip()  # 解码数据
                value = float(raw_data)  # 转换为浮点数
                global AutoTH 
                AutoTH = value#更新全局自适应变量
                self.real_time_canvas.update_data(value)  # 更新实时波形
                self.frequency_label.setText(f"当前频率: {value:.2f} kHz")  # 更新频率显示
                history_data.append(value)  # 添加到历史数据中

                # 计算呼吸频率
                self.calculate_breathing_rate()

            except Exception as e:
                print(f"Error reading data: {e}")

    # 显示历史波形
    def show_history(self):
        if history_data:
            self.history_canvas = HistoryCanvas(self, width=8, height=5, data=history_data)
            self.history_canvas.show()

    # 基于波形变化检测计算呼吸频率
    def calculate_breathing_rate(self):
        global breathing_rate_buffer

        # 获取当前波形数据
        data = np.array(self.real_time_canvas.data)

        # 使用滑动窗口检测波形变化
        step = 50  # 每段数据的步长
        num_segments = len(data) // step  # 将数据分成 num_segments 段
        changes = 0

        for i in range(num_segments - 1):
            segment_1 = data[i * step:(i + 1) * step]
            segment_2 = data[(i + 1) * step:(i + 2) * step]
            if abs(np.mean(segment_2) - np.mean(segment_1)) > BREATH_THRESHOLD:
                changes += 1

        # 将变化次数视为呼吸次数
        breathing_rate = (changes / (WINDOW_SIZE * 0.05)) * 60# 每点采样间隔为 0.05 秒 

        # 将当前频率加入滑动窗口
        breathing_rate_buffer.append(breathing_rate)
        if len(breathing_rate_buffer) > 20:  # 限制滑动窗口大小为 20 个
            breathing_rate_buffer.pop(0)

        # 计算滑动平均呼吸频率
        smoothed_breathing_rate = np.mean(breathing_rate_buffer)

        # 判断呼吸频率状态
        if smoothed_breathing_rate < MIN_BREATHING_RATE or smoothed_breathing_rate > MAX_BREATHING_RATE: #12-20成年人为正常
            self.breathing_status_label.setText("呼吸状态: 异常")
            self.breathing_status_label.setStyleSheet("font-size: 16px; color: red;")
        else:
            self.breathing_status_label.setText("呼吸状态: 正常")
            self.breathing_status_label.setStyleSheet("font-size: 16px; color: green;")

        # 更新显示
        self.breathing_rate_label.setText(f"呼吸频率: {smoothed_breathing_rate:.2f} breaths/min")

    # 保存波形和数据到文件
    def save_waveform_and_data(self):
        # 弹出文件保存对话框
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Waveform & Data", "", "CSV Files (*.csv);;PNG Files (*.png)", options=options)

        if file_name:
            # 保存波形图像
            if file_name.endswith(".png"):
                self.real_time_canvas.save_waveform_image(file_name)

            # 保存数据为CSV
            if file_name.endswith(".csv"):
                self.real_time_canvas.save_waveform_data(file_name)

# 实时波形画布类
class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        from matplotlib import rcParams

        # 设置字体为 SimHei（黑体）
        rcParams['font.sans-serif'] = ['SimHei']
        rcParams['axes.unicode_minus'] = False  # 避免负号显示为方块

        # 初始设置
        self.setParent(parent)
        self.data = [0] * WINDOW_SIZE  # 初始化数据
        self.line, = self.ax.plot(self.data, 'b-', label="频率(kHz)")  # 蓝色波形
        self.ax.set_ylim(6000, 8500)  # 设置y轴范围
        self.ax.set_xlim(0, WINDOW_SIZE)  # 设置x轴范围
        self.ax.set_xlabel("数据点/100ms")
        self.ax.set_ylabel("频率(kHz)")
        self.ax.set_title("实时频率波形")
        self.ax.legend(loc="upper right")
        self.ax.grid(True)

    # 更新数据并重绘
    def update_data(self, value):
        self.data.append(value)  # 添加新数据
        self.data.pop(0)  # 移除最旧的数据
        self.line.set_ydata(self.data)  # 更新波形数据
        global AutoTH#调用全局变量
        self.ax.set_ylim(AutoTH-1000, AutoTH+1000) #y轴坐标实时更新
        self.draw()  # 重绘画布

    # 保存波形图像
    def save_waveform_image(self, file_path):
        self.fig.savefig(file_path)
        print(f"波形图像成功保存至 {file_path}")

    # 保存波形数据为CSV
    def save_waveform_data(self, file_path):
        data = np.array(self.data)
        np.savetxt(file_path, data, delimiter=",")
        print(f"波形数据成功保存至 {file_path}")

# 历史波形画布类
class HistoryCanvas(QWidget):
    def __init__(self, parent=None, width=8, height=5, data=None):
        super().__init__(parent)
        from matplotlib import rcParams

        # 设置字体为 SimHei（黑体）
        rcParams['font.sans-serif'] = ['SimHei']
        rcParams['axes.unicode_minus'] = False  # 避免负号显示为方块

        self.setWindowTitle("History Waveform")
        self.setGeometry(150, 150, 800, 400)

        # 创建布局
        layout = QVBoxLayout(self)

        # 创建Matplotlib画布
        self.fig = Figure(figsize=(width, height))
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)

        # 绘制历史数据波形
        global AutoTH
        if data:
            self.ax.plot(data, 'r-', label="历史频率")  # 红色波形
            self.ax.set_ylim(AutoTH-2000, AutoTH+2000)  # 根据频率范围调整
            self.ax.set_xlabel("数据点/100ms")
            self.ax.set_ylabel("频率(kHz)")
            self.ax.set_title("历史频率波形")
            self.ax.legend(loc="upper right")
            self.ax.grid(True)
            self.canvas.draw()

        # 添加到布局中
        layout.addWidget(self.canvas)

        # 添加关闭按钮
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.close)  # 点击按钮关闭窗口
        layout.addWidget(self.close_button)

# 主函数
def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
