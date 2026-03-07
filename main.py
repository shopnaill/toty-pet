"""
Toty — توتي  |  Desktop Pet
Run this file to launch the pet.
"""

import sys
from PyQt6.QtWidgets import QApplication
from desktop_pet import DesktopPet


def main():
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
