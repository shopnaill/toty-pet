"""
Azkar (أذكار) — Islamic Remembrance & Supplications
Provides azkar collections, periodic reminders, and a reader dialog.
"""

import random
import time
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QWidget, QComboBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


# ══════════════════════════════════════════════════════════════
#  AZKAR DATABASE
# ══════════════════════════════════════════════════════════════

AZKAR_CATEGORIES = {
    "morning": {
        "name_ar": "أذكار الصباح",
        "name_en": "Morning Azkar",
        "icon": "🌅",
        "items": [
            {"ar": "أَصْبَحْنَا وَأَصْبَحَ الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَٰهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَىٰ كُلِّ شَيْءٍ قَدِيرٌ",
             "en": "We have entered the morning and the dominion belongs to Allah. Praise is to Allah. None has the right to be worshipped but Allah alone, with no partner. To Him belongs the dominion and to Him is the praise, and He is over all things Capable.",
             "repeat": 1, "source": "Muslim"},
            {"ar": "اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ النُّشُورُ",
             "en": "O Allah, by You we enter the morning, by You we enter the evening, by You we live, by You we die, and to You is the resurrection.",
             "repeat": 1, "source": "Tirmidhi"},
            {"ar": "اللَّهُمَّ أَنْتَ رَبِّي لَا إِلَٰهَ إِلَّا أَنْتَ، خَلَقْتَنِي وَأَنَا عَبْدُكَ، وَأَنَا عَلَىٰ عَهْدِكَ وَوَعْدِكَ مَا اسْتَطَعْتُ، أَعُوذُ بِكَ مِنْ شَرِّ مَا صَنَعْتُ، أَبُوءُ لَكَ بِنِعْمَتِكَ عَلَيَّ، وَأَبُوءُ بِذَنْبِي فَاغْفِرْ لِي فَإِنَّهُ لَا يَغْفِرُ الذُّنُوبَ إِلَّا أَنْتَ",
             "en": "O Allah, You are my Lord, there is no god but You. You created me and I am Your servant. I abide by Your covenant and promise as best I can. I seek refuge in You from the evil I have done. I acknowledge Your favor upon me, and I acknowledge my sin, so forgive me, for none forgives sins but You.",
             "repeat": 1, "source": "Bukhari (Sayyid al-Istighfar)"},
            {"ar": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ",
             "en": "Glory be to Allah and His is the praise.",
             "repeat": 100, "source": "Muslim"},
            {"ar": "لَا إِلَٰهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَىٰ كُلِّ شَيْءٍ قَدِيرٌ",
             "en": "None has the right to be worshipped but Allah alone, with no partner. To Him belongs the dominion and to Him is the praise, and He is over all things Capable.",
             "repeat": 10, "source": "Bukhari & Muslim"},
            {"ar": "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ",
             "en": "O Allah, I ask You for pardon and well-being in this world and the Hereafter.",
             "repeat": 3, "source": "Ibn Majah"},
            {"ar": "بِسْمِ اللَّهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ",
             "en": "In the Name of Allah, with Whose Name nothing on earth or in heaven can cause harm, and He is the All-Hearing, All-Knowing.",
             "repeat": 3, "source": "Abu Dawud & Tirmidhi"},
            {"ar": "اللَّهُمَّ عَافِنِي فِي بَدَنِي، اللَّهُمَّ عَافِنِي فِي سَمْعِي، اللَّهُمَّ عَافِنِي فِي بَصَرِي، لَا إِلَٰهَ إِلَّا أَنْتَ",
             "en": "O Allah, grant me health in my body. O Allah, grant me health in my hearing. O Allah, grant me health in my sight. There is no god but You.",
             "repeat": 3, "source": "Abu Dawud"},
            {"ar": "حَسْبِيَ اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ عَلَيْهِ تَوَكَّلْتُ وَهُوَ رَبُّ الْعَرْشِ الْعَظِيمِ",
             "en": "Allah is sufficient for me. There is no god but He. In Him I put my trust, and He is the Lord of the Mighty Throne.",
             "repeat": 7, "source": "Abu Dawud"},
            {"ar": "أَعُوذُ بِكَلِمَاتِ اللَّهِ التَّامَّاتِ مِنْ شَرِّ مَا خَلَقَ",
             "en": "I seek refuge in the perfect words of Allah from the evil of what He has created.",
             "repeat": 3, "source": "Muslim"},
        ],
    },
    "evening": {
        "name_ar": "أذكار المساء",
        "name_en": "Evening Azkar",
        "icon": "🌙",
        "items": [
            {"ar": "أَمْسَيْنَا وَأَمْسَى الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَٰهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَىٰ كُلِّ شَيْءٍ قَدِيرٌ",
             "en": "We have entered the evening and the dominion belongs to Allah. Praise is to Allah. None has the right to be worshipped but Allah alone, with no partner.",
             "repeat": 1, "source": "Muslim"},
            {"ar": "اللَّهُمَّ بِكَ أَمْسَيْنَا، وَبِكَ أَصْبَحْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ الْمَصِيرُ",
             "en": "O Allah, by You we enter the evening, by You we enter the morning, by You we live, by You we die, and to You is the final return.",
             "repeat": 1, "source": "Tirmidhi"},
            {"ar": "اللَّهُمَّ أَنْتَ رَبِّي لَا إِلَٰهَ إِلَّا أَنْتَ، خَلَقْتَنِي وَأَنَا عَبْدُكَ، وَأَنَا عَلَىٰ عَهْدِكَ وَوَعْدِكَ مَا اسْتَطَعْتُ، أَعُوذُ بِكَ مِنْ شَرِّ مَا صَنَعْتُ، أَبُوءُ لَكَ بِنِعْمَتِكَ عَلَيَّ، وَأَبُوءُ بِذَنْبِي فَاغْفِرْ لِي فَإِنَّهُ لَا يَغْفِرُ الذُّنُوبَ إِلَّا أَنْتَ",
             "en": "O Allah, You are my Lord, there is no god but You. You created me and I am Your servant. I abide by Your covenant and promise as best I can. I seek refuge in You from the evil I have done. I acknowledge Your favor upon me, and I acknowledge my sin, so forgive me, for none forgives sins but You.",
             "repeat": 1, "source": "Bukhari (Sayyid al-Istighfar)"},
            {"ar": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ",
             "en": "Glory be to Allah and His is the praise.",
             "repeat": 100, "source": "Muslim"},
            {"ar": "أَعُوذُ بِكَلِمَاتِ اللَّهِ التَّامَّاتِ مِنْ شَرِّ مَا خَلَقَ",
             "en": "I seek refuge in the perfect words of Allah from the evil of what He has created.",
             "repeat": 3, "source": "Muslim"},
            {"ar": "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ",
             "en": "O Allah, I ask You for pardon and well-being in this world and the Hereafter.",
             "repeat": 3, "source": "Ibn Majah"},
            {"ar": "بِسْمِ اللَّهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ",
             "en": "In the Name of Allah, with Whose Name nothing on earth or in heaven can cause harm, and He is the All-Hearing, All-Knowing.",
             "repeat": 3, "source": "Abu Dawud & Tirmidhi"},
            {"ar": "حَسْبِيَ اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ عَلَيْهِ تَوَكَّلْتُ وَهُوَ رَبُّ الْعَرْشِ الْعَظِيمِ",
             "en": "Allah is sufficient for me. There is no god but He. In Him I put my trust, and He is the Lord of the Mighty Throne.",
             "repeat": 7, "source": "Abu Dawud"},
        ],
    },
    "after_prayer": {
        "name_ar": "أذكار بعد الصلاة",
        "name_en": "After Prayer Azkar",
        "icon": "🕌",
        "items": [
            {"ar": "أَسْتَغْفِرُ اللَّهَ",
             "en": "I seek forgiveness from Allah.",
             "repeat": 3, "source": "Muslim"},
            {"ar": "اللَّهُمَّ أَنْتَ السَّلَامُ وَمِنْكَ السَّلَامُ، تَبَارَكْتَ يَا ذَا الْجَلَالِ وَالْإِكْرَامِ",
             "en": "O Allah, You are Peace and from You is peace. Blessed are You, O Possessor of Majesty and Honor.",
             "repeat": 1, "source": "Muslim"},
            {"ar": "لَا إِلَٰهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَىٰ كُلِّ شَيْءٍ قَدِيرٌ، اللَّهُمَّ لَا مَانِعَ لِمَا أَعْطَيْتَ وَلَا مُعْطِيَ لِمَا مَنَعْتَ وَلَا يَنْفَعُ ذَا الْجَدِّ مِنْكَ الْجَدُّ",
             "en": "None has the right to be worshipped but Allah alone, with no partner. O Allah, none can withhold what You give, and none can give what You withhold, and the wealth of the wealthy cannot benefit him against You.",
             "repeat": 1, "source": "Bukhari & Muslim"},
            {"ar": "سُبْحَانَ اللَّهِ",
             "en": "Glory be to Allah.",
             "repeat": 33, "source": "Muslim"},
            {"ar": "الْحَمْدُ لِلَّهِ",
             "en": "Praise be to Allah.",
             "repeat": 33, "source": "Muslim"},
            {"ar": "اللَّهُ أَكْبَرُ",
             "en": "Allah is the Greatest.",
             "repeat": 33, "source": "Muslim"},
            {"ar": "لَا إِلَٰهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَىٰ كُلِّ شَيْءٍ قَدِيرٌ",
             "en": "None has the right to be worshipped but Allah alone, with no partner. To Him belongs the dominion and to Him is the praise, and He is over all things Capable.",
             "repeat": 1, "source": "Muslim (completing the 100)"},
            {"ar": "آية الكرسي: اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَهُ مَا فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ ۗ مَنْ ذَا الَّذِي يَشْفَعُ عِنْدَهُ إِلَّا بِإِذْنِهِ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَيْءٍ مِنْ عِلْمِهِ إِلَّا بِمَا شَاءَ ۚ وَسِعَ كُرْسِيُّهُ السَّمَاوَاتِ وَالْأَرْضَ ۖ وَلَا يَئُودُهُ حِفْظُهُمَا ۚ وَهُوَ الْعَلِيُّ الْعَظِيمُ",
             "en": "Ayat al-Kursi (Verse of the Throne) — Surah Al-Baqarah 2:255",
             "repeat": 1, "source": "Nasa'i"},
        ],
    },
    "sleep": {
        "name_ar": "أذكار النوم",
        "name_en": "Sleep Azkar",
        "icon": "😴",
        "items": [
            {"ar": "بِاسْمِكَ اللَّهُمَّ أَمُوتُ وَأَحْيَا",
             "en": "In Your name, O Allah, I die and I live.",
             "repeat": 1, "source": "Bukhari"},
            {"ar": "اللَّهُمَّ قِنِي عَذَابَكَ يَوْمَ تَبْعَثُ عِبَادَكَ",
             "en": "O Allah, save me from Your punishment on the Day You resurrect Your servants.",
             "repeat": 3, "source": "Abu Dawud & Tirmidhi"},
            {"ar": "سُبْحَانَ اللَّهِ",
             "en": "Glory be to Allah.",
             "repeat": 33, "source": "Bukhari & Muslim"},
            {"ar": "الْحَمْدُ لِلَّهِ",
             "en": "Praise be to Allah.",
             "repeat": 33, "source": "Bukhari & Muslim"},
            {"ar": "اللَّهُ أَكْبَرُ",
             "en": "Allah is the Greatest.",
             "repeat": 34, "source": "Bukhari & Muslim"},
            {"ar": "اللَّهُمَّ بِاسْمِكَ رَبِّي وَضَعْتُ جَنْبِي، وَبِكَ أَرْفَعُهُ، فَإِنْ أَمْسَكْتَ نَفْسِي فَارْحَمْهَا، وَإِنْ أَرْسَلْتَهَا فَاحْفَظْهَا بِمَا تَحْفَظُ بِهِ عِبَادَكَ الصَّالِحِينَ",
             "en": "O Allah, in Your name, my Lord, I lay down my side and by You I raise it up. If You take my soul, have mercy on it, and if You send it back, protect it with what You protect Your righteous servants.",
             "repeat": 1, "source": "Bukhari & Muslim"},
        ],
    },
    "general": {
        "name_ar": "أذكار عامة",
        "name_en": "General Dhikr",
        "icon": "📿",
        "items": [
            {"ar": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ، سُبْحَانَ اللَّهِ الْعَظِيمِ",
             "en": "Glory be to Allah and His is the praise. Glory be to Allah the Almighty.",
             "repeat": 0, "source": "Bukhari & Muslim — Two words beloved to the Most Merciful"},
            {"ar": "لَا حَوْلَ وَلَا قُوَّةَ إِلَّا بِاللَّهِ",
             "en": "There is no power nor strength except with Allah.",
             "repeat": 0, "source": "Bukhari & Muslim — A treasure of Paradise"},
            {"ar": "سُبْحَانَ اللَّهِ، وَالْحَمْدُ لِلَّهِ، وَلَا إِلَٰهَ إِلَّا اللَّهُ، وَاللَّهُ أَكْبَرُ",
             "en": "Glory be to Allah, praise be to Allah, there is no god but Allah, and Allah is the Greatest.",
             "repeat": 0, "source": "Muslim — More beloved to me than everything the sun rises upon"},
            {"ar": "أَسْتَغْفِرُ اللَّهَ وَأَتُوبُ إِلَيْهِ",
             "en": "I seek forgiveness from Allah and repent to Him.",
             "repeat": 100, "source": "Bukhari & Muslim — The Prophet ﷺ used to seek forgiveness 100 times daily"},
            {"ar": "اللَّهُمَّ صَلِّ وَسَلِّمْ عَلَى نَبِيِّنَا مُحَمَّدٍ",
             "en": "O Allah, send blessings and peace upon our Prophet Muhammad ﷺ.",
             "repeat": 10, "source": "Muslim"},
            {"ar": "لَا إِلَٰهَ إِلَّا اللَّهُ",
             "en": "There is no god but Allah.",
             "repeat": 0, "source": "The best dhikr — Tirmidhi"},
            {"ar": "الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ",
             "en": "All praise is due to Allah, Lord of the worlds.",
             "repeat": 0, "source": "Quran 1:2"},
            {"ar": "رَبِّ اغْفِرْ لِي وَتُبْ عَلَيَّ إِنَّكَ أَنْتَ التَّوَّابُ الرَّحِيمُ",
             "en": "My Lord, forgive me and accept my repentance. Indeed, You are the Accepting of Repentance, the Most Merciful.",
             "repeat": 0, "source": "Abu Dawud & Tirmidhi"},
        ],
    },
    "dua": {
        "name_ar": "أدعية مختارة",
        "name_en": "Selected Du'a",
        "icon": "🤲",
        "items": [
            {"ar": "رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ",
             "en": "Our Lord, give us good in this world and good in the Hereafter, and save us from the punishment of the Fire.",
             "repeat": 0, "source": "Quran 2:201 — Most frequent du'a of the Prophet ﷺ"},
            {"ar": "اللَّهُمَّ إِنِّي أَعُوذُ بِكَ مِنَ الْهَمِّ وَالْحَزَنِ، وَالْعَجْزِ وَالْكَسَلِ، وَالْبُخْلِ وَالْجُبْنِ، وَضَلَعِ الدَّيْنِ وَغَلَبَةِ الرِّجَالِ",
             "en": "O Allah, I seek refuge in You from worry and grief, from incapacity and laziness, from miserliness and cowardice, from being overcome by debt and overpowered by people.",
             "repeat": 0, "source": "Bukhari"},
            {"ar": "رَبِّ زِدْنِي عِلْمًا",
             "en": "My Lord, increase me in knowledge.",
             "repeat": 0, "source": "Quran 20:114"},
            {"ar": "رَبِّ اشْرَحْ لِي صَدْرِي وَيَسِّرْ لِي أَمْرِي",
             "en": "My Lord, expand my chest and ease my task for me.",
             "repeat": 0, "source": "Quran 20:25-26"},
            {"ar": "اللَّهُمَّ إِنِّي أَسْأَلُكَ عِلْمًا نَافِعًا، وَرِزْقًا طَيِّبًا، وَعَمَلًا مُتَقَبَّلًا",
             "en": "O Allah, I ask You for beneficial knowledge, good provision, and accepted deeds.",
             "repeat": 0, "source": "Ibn Majah — Du'a after Fajr"},
            {"ar": "اللَّهُمَّ أَعِنِّي عَلَىٰ ذِكْرِكَ وَشُكْرِكَ وَحُسْنِ عِبَادَتِكَ",
             "en": "O Allah, help me to remember You, thank You, and worship You well.",
             "repeat": 0, "source": "Abu Dawud & Nasa'i"},
            {"ar": "يَا مُقَلِّبَ الْقُلُوبِ ثَبِّتْ قَلْبِي عَلَىٰ دِينِكَ",
             "en": "O Turner of hearts, make my heart firm upon Your religion.",
             "repeat": 0, "source": "Tirmidhi"},
            {"ar": "اللَّهُمَّ إِنَّكَ عَفُوٌّ تُحِبُّ الْعَفْوَ فَاعْفُ عَنِّي",
             "en": "O Allah, You are Forgiving and love forgiveness, so forgive me.",
             "repeat": 0, "source": "Tirmidhi — Du'a for Laylat al-Qadr"},
        ],
    },
}

# Quick reminder pool — short azkar suitable for popup bubbles
QUICK_AZKAR = [
    "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ 📿",
    "لَا إِلَٰهَ إِلَّا اللَّهُ 💚",
    "اللَّهُ أَكْبَرُ ✨",
    "الْحَمْدُ لِلَّهِ 🌟",
    "سُبْحَانَ اللَّهِ الْعَظِيمِ 🌿",
    "أَسْتَغْفِرُ اللَّهَ 🤲",
    "لَا حَوْلَ وَلَا قُوَّةَ إِلَّا بِاللَّهِ 💎",
    "اللَّهُمَّ صَلِّ عَلَى مُحَمَّدٍ ﷺ 🌹",
    "سُبْحَانَ اللَّهِ وَالْحَمْدُ لِلَّهِ 🍃",
    "حَسْبِيَ اللَّهُ وَنِعْمَ الْوَكِيلُ 🛡️",
    "رَبِّ زِدْنِي عِلْمًا 📖",
    "رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً 🤲",
]


# ══════════════════════════════════════════════════════════════
#  AZKAR MANAGER
# ══════════════════════════════════════════════════════════════

class AzkarManager:
    """Manages periodic azkar reminders and tracks reading state."""

    def __init__(self, settings):
        self.settings = settings
        self._last_reminder_time = 0.0
        self._last_category_reminder = ""
        self._morning_reminded = False
        self._evening_reminded = False
        self._today_date = datetime.now().date()

    def _reset_daily(self):
        today = datetime.now().date()
        if today != self._today_date:
            self._today_date = today
            self._morning_reminded = False
            self._evening_reminded = False

    def get_random_quick_dhikr(self) -> str:
        """Return a random short dhikr for popup bubble."""
        return random.choice(QUICK_AZKAR)

    def should_remind(self) -> dict | None:
        """
        Check if it's time for an azkar reminder.
        Returns dict with reminder info, or None.
        """
        self._reset_daily()

        interval = self.settings.get("azkar_reminder_min") * 60
        now = time.time()

        if now - self._last_reminder_time < interval:
            return None

        hour = datetime.now().hour

        # Morning azkar reminder (5-9 AM)
        if 5 <= hour <= 9 and not self._morning_reminded:
            self._last_reminder_time = now
            self._morning_reminded = True
            return {
                "type": "timed",
                "category": "morning",
                "message": "🌅 وقت أذكار الصباح!\nTime for morning azkar!",
            }

        # Evening azkar reminder (3-7 PM / after Asr)
        if 15 <= hour <= 19 and not self._evening_reminded:
            self._last_reminder_time = now
            self._evening_reminded = True
            return {
                "type": "timed",
                "category": "evening",
                "message": "🌙 وقت أذكار المساء!\nTime for evening azkar!",
            }

        # General periodic dhikr reminder
        self._last_reminder_time = now
        dhikr = self.get_random_quick_dhikr()
        return {
            "type": "quick",
            "category": "general",
            "message": f"📿 ذكر الله\n{dhikr}",
        }

    def get_time_appropriate_category(self) -> str:
        """Return the most appropriate category based on time of day."""
        hour = datetime.now().hour
        if 4 <= hour < 12:
            return "morning"
        elif 12 <= hour < 15:
            return "after_prayer"
        elif 15 <= hour < 20:
            return "evening"
        elif 20 <= hour or hour < 4:
            return "sleep"
        return "general"

    def get_category_count(self, cat_key: str) -> int:
        cat = AZKAR_CATEGORIES.get(cat_key, {})
        return len(cat.get("items", []))

    def get_random_from_category(self, cat_key: str) -> dict | None:
        cat = AZKAR_CATEGORIES.get(cat_key, {})
        items = cat.get("items", [])
        if items:
            return random.choice(items)
        return None


# ══════════════════════════════════════════════════════════════
#  AZKAR READER DIALOG
# ══════════════════════════════════════════════════════════════

class AzkarReaderDialog(QDialog):
    """A beautiful dialog for reading azkar collections."""

    def __init__(self, initial_category="morning", parent=None):
        super().__init__(parent)
        self.setWindowTitle("📿 Azkar Reader — قارئ الأذكار")
        self.setFixedSize(560, 600)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self._current_index = 0
        self._current_category = initial_category

        self._build_ui()
        self._load_category(initial_category)

    def _build_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0D1B2A, stop:1 #1B2838
                );
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── Header: title + category selector ──
        header = QHBoxLayout()

        title = QLabel("📿 أذكار")
        title.setStyleSheet("color: #F0C674; font-size: 20px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(title)

        header.addStretch()

        self._cat_combo = QComboBox()
        self._cat_combo.setStyleSheet("""
            QComboBox {
                background: #1E3044; color: #CDD6F4; border: 1px solid #3B5068;
                border-radius: 6px; padding: 6px 12px; font-size: 13px; min-width: 180px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1E3044; color: #CDD6F4; selection-background-color: #3B5068;
                border: 1px solid #3B5068;
            }
        """)
        for key, cat in AZKAR_CATEGORIES.items():
            self._cat_combo.addItem(
                f"{cat['icon']} {cat['name_ar']}  —  {cat['name_en']}", key
            )
        self._cat_combo.currentIndexChanged.connect(self._on_category_changed)
        header.addWidget(self._cat_combo)

        layout.addLayout(header)

        # ── Counter & progress ──
        self._progress_label = QLabel()
        self._progress_label.setStyleSheet(
            "color: #A6ADC8; font-size: 12px; padding: 2px 4px;"
        )
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._progress_label)

        # ── Scrollable azkar area ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 8px; background: #1E3044; }
            QScrollBar::handle:vertical { background: #3B5068; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(10)
        self._scroll.setWidget(self._container)

        layout.addWidget(self._scroll, stretch=1)

        # ── Bottom buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._random_btn = QPushButton("🎲 Random Dhikr")
        self._random_btn.setStyleSheet(self._btn_style("#6C7A89"))
        self._random_btn.clicked.connect(self._show_random)
        btn_row.addWidget(self._random_btn)

        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._btn_style("#89B4FA"))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    @staticmethod
    def _btn_style(bg: str) -> str:
        return (
            f"QPushButton {{ background: {bg}; color: #1E1E2E; border: none;"
            f"  border-radius: 6px; padding: 8px 18px; font-weight: bold; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {bg}DD; }}"
        )

    def _on_category_changed(self, index):
        key = self._cat_combo.itemData(index)
        if key:
            self._load_category(key)

    def _load_category(self, cat_key: str):
        self._current_category = cat_key
        cat = AZKAR_CATEGORIES.get(cat_key, {})
        items = cat.get("items", [])

        # Select combo to match
        for i in range(self._cat_combo.count()):
            if self._cat_combo.itemData(i) == cat_key:
                self._cat_combo.blockSignals(True)
                self._cat_combo.setCurrentIndex(i)
                self._cat_combo.blockSignals(False)
                break

        self._progress_label.setText(
            f"{cat.get('icon', '')} {cat.get('name_ar', '')}  —  "
            f"{len(items)} {'أذكار' if len(items) != 1 else 'ذكر'}"
        )

        # Clear existing
        while self._container_layout.count():
            child = self._container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Add each dhikr card
        for i, item in enumerate(items):
            card = self._create_dhikr_card(i + 1, item)
            self._container_layout.addWidget(card)

        self._container_layout.addStretch()
        self._scroll.verticalScrollBar().setValue(0)

    def _create_dhikr_card(self, num: int, item: dict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #162232;
                border: 1px solid #2A3F55;
                border-radius: 10px;
            }
        """)

        fl = QVBoxLayout(frame)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(6)

        # Number
        num_label = QLabel(f"#{num}")
        num_label.setStyleSheet("color: #F0C674; font-size: 11px; font-weight: bold; border: none;")
        fl.addWidget(num_label)

        # Arabic text
        ar_label = QLabel(item["ar"])
        ar_label.setWordWrap(True)
        ar_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        ar_label.setStyleSheet(
            "color: #E8E8E8; font-size: 16px; line-height: 1.8;"
            "font-family: 'Traditional Arabic', 'Amiri', 'Scheherazade', serif;"
            "padding: 6px 2px; border: none;"
        )
        fl.addWidget(ar_label)

        # English translation
        en_label = QLabel(item["en"])
        en_label.setWordWrap(True)
        en_label.setStyleSheet(
            "color: #89B4FA; font-size: 11px; font-style: italic; padding: 2px; border: none;"
        )
        fl.addWidget(en_label)

        # Footer: repeat count + source
        footer = QHBoxLayout()
        repeat = item.get("repeat", 0)
        if repeat > 0:
            rep_label = QLabel(f"🔁 ×{repeat}")
            rep_label.setStyleSheet("color: #A6E3A1; font-size: 11px; border: none;")
            footer.addWidget(rep_label)
        else:
            spacer_label = QLabel("")
            spacer_label.setStyleSheet("border: none;")
            footer.addWidget(spacer_label)

        footer.addStretch()

        source = item.get("source", "")
        if source:
            src_label = QLabel(f"📚 {source}")
            src_label.setStyleSheet("color: #6C7A89; font-size: 10px; border: none;")
            footer.addWidget(src_label)

        fl.addLayout(footer)

        return frame

    def _show_random(self):
        cat = AZKAR_CATEGORIES.get(self._current_category, {})
        items = cat.get("items", [])
        if not items:
            return
        item = random.choice(items)

        # Clear and show just one
        while self._container_layout.count():
            child = self._container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        card = self._create_dhikr_card(0, item)
        self._container_layout.addWidget(card)
        self._container_layout.addStretch()

        self._progress_label.setText(
            f"🎲 Random from {cat.get('name_en', '')}  —  "
            f"Click again for another, or change category to see all"
        )
