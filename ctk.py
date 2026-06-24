import sys
from PyQt5.QtWidgets import *


class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # StatusBar
        self.statusbar = QStatusBar(self)          # QStatusBar 객체 생성
        self.setStatusBar(self.statusbar)          # 위젯 배치
        self.statusbar.showMessage("PYSTOCK v1.0")

app = QApplication(sys.argv)
mywindow = MyWindow()
mywindow.show()
app.exec_()
