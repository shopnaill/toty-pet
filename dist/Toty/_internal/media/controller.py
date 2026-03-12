import ctypes


class MediaController:
    """Send media key events on Windows via ctypes."""

    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_VOLUME_UP = 0xAF
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_MUTE = 0xAD

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002

    @staticmethod
    def _press_key(vk_code: int):
        ctypes.windll.user32.keybd_event(vk_code, 0, MediaController.KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(
            vk_code, 0,
            MediaController.KEYEVENTF_EXTENDEDKEY | MediaController.KEYEVENTF_KEYUP, 0
        )

    @classmethod
    def play_pause(cls):
        cls._press_key(cls.VK_MEDIA_PLAY_PAUSE)

    @classmethod
    def next_track(cls):
        cls._press_key(cls.VK_MEDIA_NEXT_TRACK)

    @classmethod
    def prev_track(cls):
        cls._press_key(cls.VK_MEDIA_PREV_TRACK)

    @classmethod
    def volume_up(cls):
        for _ in range(5):
            cls._press_key(cls.VK_VOLUME_UP)

    @classmethod
    def volume_down(cls):
        for _ in range(5):
            cls._press_key(cls.VK_VOLUME_DOWN)

    @classmethod
    def mute(cls):
        cls._press_key(cls.VK_VOLUME_MUTE)
