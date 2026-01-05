import sys
from PyQt6.QtWidgets import QApplication
from project_manager import ProjectManagerWindow


def main():
    app = QApplication(sys.argv)
    w = ProjectManagerWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
