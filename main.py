import os
import sys
import subprocess
import re
import json
import random
import asyncio
import time
from datetime import datetime
import flet as ft

# ==========================================
# 🤖 GROQ AI AYARLARI
# ==========================================
# Buraya kendi Groq API anahtarını yaz.
# Örnek: GROQ_API_KEY = "gsk_xxxxxxxxxxxxxxxxx"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

# Groq model: hızlı ve güçlü genel amaçlı sohbet modeli.
GROQ_MODEL = "openai/gpt-oss-20b"

try:
    from groq import Groq
except ImportError:
    Groq = None

# ==========================================
# 🛠️ FLET UYUMLULUK YARDIMCILARI
# ==========================================
def b_all(width, color):
    return ft.Border(
        top=ft.BorderSide(width, color),
        bottom=ft.BorderSide(width, color),
        left=ft.BorderSide(width, color),
        right=ft.BorderSide(width, color)
    )

def m_symmetric(horizontal=0, vertical=0):
    return ft.Margin(left=horizontal, top=vertical, right=horizontal, bottom=vertical)

def soft_shadow(blur=14, spread=0, opacity=0.10, color="#2E2A25"):
    return ft.BoxShadow(spread_radius=spread, blur_radius=blur, color=ft.Colors.with_opacity(opacity, color), offset=ft.Offset(0, 4))

# ==========================================
# 🎨 TASARIM SİSTEMİ
# ==========================================
PALETTE = {
    "bg": "#FAF6F0",
    "bg_soft": "#F2EAE0",
    "surface": "#FFFFFF",
    "surface_alt": "#FBF3E9",
    "border": "#EAE1D4",
    "border_strong": "#DCCEB9",
    "text": "#2E2A25",
    "text_soft": "#79705F",
    "text_faint": "#A79C8C",
    "primary": "#C1794C",
    "primary_dark": "#A05F39",
    "primary_soft": "#F0DAC3",
    "primary_bg": "#FBEEE0",
    "sage": "#7E9873",
    "sage_dark": "#54704B",
    "sage_bg": "#E9F1E3",
    "amber": "#C99A3C",
    "amber_bg": "#FBF1DC",
    "danger": "#C97361",
    "danger_bg": "#FBEAE5",
    "white": "#FFFFFF",
}

FONT_FAMILY = "Segoe UI"

RADIUS_SM = 10
RADIUS_MD = 16
RADIUS_LG = 20
RADIUS_XL = 26

# ==========================================
# 🌐 i18n & YARDIMCI FONKSİYONLAR
# ==========================================
def _uygulama_dizini():
    return os.path.dirname(os.path.abspath(__file__))

def _json_yukle(dosya_adi, varsayilan):
    yol = os.path.join(_uygulama_dizini(), dosya_adi)
    if os.path.exists(yol):
        try:
            with open(yol, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as err:
            print(f"[i18n] '{dosya_adi}' okunamadı: {err}")
    return varsayilan

LANG = _json_yukle("lang.json", {"tr": {}, "en": {}})
ING = _json_yukle("ingredients.json", {"categories": [], "ingredient_names": {}, "seasonal_out_of_season": []})
MEVSIM_DISI_MALZEMELER = set(ING.get("seasonal_out_of_season", []))

def translate(dil, key, **kwargs):
    def _walk(tree):
        node = tree
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return None
        return node

    metin = _walk(LANG.get(dil, {}))
    if metin is None:
        metin = _walk(LANG.get("tr", {}))
    if metin is None:
        metin = key

    if isinstance(metin, str) and kwargs:
        try:
            return metin.format(**kwargs)
        except Exception:
            return metin
    return metin

def ingredient_display_name(dil, tr_adi):
    girdi = ING.get("ingredient_names", {}).get(tr_adi)
    if not girdi:
        return tr_adi
    return girdi.get(dil, girdi.get("tr", tr_adi))

def category_label(dil, kategori):
    baslik = kategori.get("label", {}).get(dil, kategori.get("label", {}).get("tr", ""))
    return f"{kategori.get('icon', '')} {baslik}".strip()

def zamana_gore_selamlama_al(dil):
    saat = datetime.now().hour
    if 5 <= saat < 12:
        return translate(dil, "greetings.morning_text"), translate(dil, "greetings.morning_badge")
    elif 12 <= saat < 18:
        return translate(dil, "greetings.afternoon_text"), translate(dil, "greetings.afternoon_badge")
    elif 18 <= saat < 22:
        return translate(dil, "greetings.evening_text"), translate(dil, "greetings.evening_badge")
    else:
        return translate(dil, "greetings.night_text"), translate(dil, "greetings.night_badge")

def sayi_ayikla(metin, varsayilan=0):
    eslesme = re.search(r"\d+", str(metin))
    return int(eslesme.group()) if eslesme else varsayilan

# ==========================================
# 📂 DOSYA YÖNETİMİ & VERİ SAKLAMA
# ==========================================
def veri_dizini_al():
    try:
        return ft.get_app_storage_dir()
    except Exception:
        return os.path.dirname(__file__)

KAYIT_DIZINI = veri_dizini_al()
FAV_DOSYA = os.path.join(KAYIT_DIZINI, "favoriler.json")
alisveris_DOSYA = os.path.join(KAYIT_DIZINI, "alisveris_listesi.json")
menu_DOSYA = os.path.join(KAYIT_DIZINI, "haftalik_menu.json")
notlar_DOSYA = os.path.join(KAYIT_DIZINI, "tarif_notlari.json")
ayar_DOSYA = os.path.join(KAYIT_DIZINI, "ayarlar.json")
CHAT_DOSYA = os.path.join(KAYIT_DIZINI, "ai_sohbetler.json")

ISTATISTIKLER_VARSAYILAN = {
    "tamamlanan_tarifler": {},
    "toplam_tamamlanan": 0,
    "favoriye_eklenen": 0,
    "son_tamamlanan": "",
}

def tarif_zorlugu_hesapla(tarif):
    """Tarifte zorluk alanı yoksa süre/adım/malzeme sayısından yaklaşık seviye çıkarır."""
    mevcut = str(tarif.get("zorluk", "") or "").strip().lower()
    if mevcut:
        if mevcut in ("kolay", "easy", "1", "1/3"):
            return "Kolay"
        if mevcut in ("orta", "medium", "2", "2/3"):
            return "Orta"
        if mevcut in ("zor", "hard", "3", "3/3"):
            return "Zor"
    adim = len(tarif.get("hazirlanis", []) or [])
    malz = len(tarif.get("malzemeler", []) or [])
    sure_txt = str(tarif.get("sure", ""))
    sayilar = re.findall(r"\d+", sure_txt)
    sure = int(sayilar[0]) if sayilar else 0
    puan = (2 if adim >= 7 else 1 if adim >= 4 else 0) + (1 if malz >= 10 else 0) + (2 if sure >= 60 else 1 if sure >= 35 else 0)
    return "Zor" if puan >= 4 else "Orta" if puan >= 2 else "Kolay"


def json_tarifleri_yukle():
    json_yolu = os.path.join(_uygulama_dizini(), "tarifler.json")
    if os.path.exists(json_yolu):
        try:
            with open(json_yolu, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as err:
            print(f"JSON Okuma Hatası: {err}")
            return []
    return []

def veri_yukle(dosya_yolu):
    if os.path.exists(dosya_yolu):
        try:
            with open(dosya_yolu, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def veri_kaydet(dosya_yolu, veri):
    try:
        os.makedirs(os.path.dirname(dosya_yolu), exist_ok=True)
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
    except Exception as err:
        print(f"Kayıt Hatası: {err}")

# ==========================================
# 🚀 UYGULAMA ANA AKIŞI
# ==========================================
async def main(page: ft.Page):
    # =========================================================
    # 📱 WINDOWS TELEFON ÖNİZLEMESİ — 412 x 915
    # Pencere ayarlarını main()'in EN BAŞINDA uyguluyoruz.
    # Böylece uygulama içeriği oluşturulmadan önce boyut/kilit
    # ayarları uygulanmış olur.
    # =========================================================
    page.window.maximized = False
    page.window.full_screen = False
    page.window.resizable = False
    page.window.maximizable = False

    page.window.width = 412
    page.window.height = 915
    page.window.min_width = 412
    page.window.max_width = 412
    page.window.min_height = 915
    page.window.max_height = 915

    await page.window.center()

    mevcut_dizin = os.path.dirname(os.path.abspath(__file__))
    ico_yolu = os.path.join(mevcut_dizin, "icon.ico")
    page.window_icon = ico_yolu
    page.window.icon = ico_yolu

    kayitli_ayar = veri_yukle(ayar_DOSYA)
    aktif_dil = kayitli_ayar.get("dil", "tr") if isinstance(kayitli_ayar, dict) else "tr"
    kullanici_adi = kayitli_ayar.get("kullanici_adi", "") if isinstance(kayitli_ayar, dict) else ""
    kullanici_adi = str(kullanici_adi or "").strip()[:30]

    def _t(anahtar, **kwargs):
        return translate(aktif_dil, anahtar, **kwargs)

    def _ing(tr_adi):
        return ingredient_display_name(aktif_dil, tr_adi)

    async def ilk_acilis_isim_sor():
        """Splash tamamlandıktan sonra ilk açılışta kullanıcı adını sorar."""
        nonlocal kullanici_adi
        if kullanici_adi:
            return

        isim_girdisi = ft.TextField(
            label="İsminiz nedir?",
            hint_text="Adınızı yazın",
            autofocus=True,
            max_length=30,
            capitalization=ft.TextCapitalization.WORDS,
            border_color="#B8D0C3",
            focused_border_color="#DDEDE4",
            cursor_color="#DDEDE4",
            text_style=ft.TextStyle(color="#24352E", size=15, weight=ft.FontWeight.W_700),
            label_style=ft.TextStyle(color="#557064"),
            bgcolor="#FFFFFF",
        )

        isim_ekrani = ft.Container(
            width=412,
            height=915,
            bgcolor="#F7F0E5",
            alignment=ft.Alignment(0, 0),
            padding=ft.Padding(left=28, right=28, top=40, bottom=40),
            content=ft.Column([
                ft.Container(
                    width=72,
                    height=72,
                    bgcolor="#E8F1EB",
                    border_radius=36,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text("👋", size=34),
                ),
                ft.Text(
                    "Hoş geldin!",
                    size=27,
                    weight=ft.FontWeight.W_900,
                    color="#2F493D",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "İsminiz nedir?",
                    size=15,
                    color="#6F756F",
                    weight=ft.FontWeight.W_600,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=8),
                ft.Container(
                    padding=ft.Padding(left=18, right=18, top=18, bottom=18),
                    bgcolor="#EAF3ED",
                    border_radius=22,
                    shadow=soft_shadow(blur=24, opacity=0.16),
                    content=ft.Column([
                        isim_girdisi,
                        ft.Text(
                            "(İsteğe bağlı, isterseniz Ayarlar'dan daha sonra değiştirebilirsiniz.)",
                            size=11.5,
                            color="#6A7E73",
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ], spacing=10),
                ),
                ft.Container(height=4),
                ft.ElevatedButton(
                    "Mutfağa geç 🍳",
                    on_click=None,
                    style=ft.ButtonStyle(
                        bgcolor="#D79A68",
                        color="#FFFFFF",
                        padding=ft.Padding(left=28, right=28, top=14, bottom=14),
                        shape=ft.RoundedRectangleBorder(radius=16),
                    ),
                ),
                ft.TextButton(
                    "Daha sonra",
                    on_click=None,
                    style=ft.ButtonStyle(color="#6F756F"),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12),
        )

        # Buton referansları içerik oluşturulduktan sonra bağlanıyor.
        devam_butonu = isim_ekrani.content.controls[-2]
        daha_sonra_butonu = isim_ekrani.content.controls[-1]

        async def daha_sonra(_=None):
            await kaydet(None)

        async def kaydet(_=None):
            nonlocal kullanici_adi
            isim = str(isim_girdisi.value or "").strip()[:30]
            # İsim tamamen isteğe bağlıdır. Boş bırakılırsa hiçbir yerde isim gösterilmez.
            kullanici_adi = isim
            ayarlar = veri_yukle(ayar_DOSYA)
            if not isinstance(ayarlar, dict):
                ayarlar = {}
            ayarlar["dil"] = aktif_dil
            ayarlar["kullanici_adi"] = kullanici_adi
            veri_kaydet(ayar_DOSYA, ayarlar)

        # İsim ekranı kaybolurken yumuşakça solar; ardından ana menü tatlı bir geçişle gelir.
            isim_ekrani.opacity = 0.0
            isim_ekrani.scale = 0.985
            isim_ekrani.animate_opacity = ft.Animation(360, ft.AnimationCurve.EASE_IN_OUT)
            isim_ekrani.animate_scale = ft.Animation(420, ft.AnimationCurve.EASE_IN_OUT)
            page.update()
            await asyncio.sleep(0.30)

            isim_ekrani.visible = False
            ana_menu.visible = True
            ana_menu.opacity = 0.0
            ana_menu.offset = ft.Offset(0, 0.035)
            ana_menu.scale = 0.985
            ana_menu.animate_opacity = ft.Animation(520, ft.AnimationCurve.EASE_OUT)
            ana_menu.animate_offset = ft.Animation(520, ft.AnimationCurve.EASE_OUT_CUBIC)
            ana_menu.animate_scale = ft.Animation(520, ft.AnimationCurve.EASE_OUT_BACK)
            page.update()
            await asyncio.sleep(0.05)
            ana_menu.opacity = 1.0
            ana_menu.offset = ft.Offset(0, 0)
            ana_menu.scale = 1.0
            page.update()
            await asyncio.sleep(0.35)
            page.run_task(ana_menu_kartlarini_oynat)
            page.run_task(degerlendirme_istegi_goster)

        devam_butonu.on_click = kaydet
        daha_sonra_butonu.on_click = daha_sonra
        page.overlay.append(isim_ekrani)
        isim_ekrani.visible = True
        page.update()

        while isim_ekrani.visible:
            await asyncio.sleep(0.15)

    def yapilandir_etkilesim(kontrol, on_click=None, hover_scale=1.015, basma_scale=0.98,
                              temel_golge=None, hover_golge=None):
        kontrol.scale = 1.0
        kontrol.animate_scale = ft.Animation(140, ft.AnimationCurve.EASE_OUT)
        if temel_golge is not None:
            kontrol.shadow = temel_golge
            kontrol.animate = ft.Animation(160, ft.AnimationCurve.EASE_OUT)

        def _hover(e):
            hover_mi = e.data == "true"
            kontrol.scale = hover_scale if hover_mi else 1.0
            if hover_golge is not None and temel_golge is not None:
                kontrol.shadow = hover_golge if hover_mi else temel_golge
            page.update()

        kontrol.on_hover = _hover

        if on_click:
            async def _tikla(e):
                kontrol.scale = basma_scale
                page.update()
                await asyncio.sleep(0.06)
                kontrol.scale = hover_scale
                page.update()
                sonuc = on_click(e)
                if asyncio.iscoroutine(sonuc):
                    await sonuc

            kontrol.on_click = _tikla
        return kontrol

    def pill_button(metin, icon=None, on_click=None, dolgu=True, expand=False):
        renk_bg = PALETTE["primary"] if dolgu else PALETTE["surface"]
        renk_text = PALETTE["white"] if dolgu else PALETTE["primary"]
        kenar = b_all(0, PALETTE["primary"]) if dolgu else b_all(1.6, PALETTE["primary_soft"])

        icerik = [ft.Text(metin, size=13.5, weight=ft.FontWeight.W_800, color=renk_text)]
        if icon:
            icerik.insert(0, ft.Icon(icon, size=17, color=renk_text))

        kart = ft.Container(
            content=ft.Row(icerik, spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            padding=m_symmetric(horizontal=18, vertical=14),
            bgcolor=renk_bg,
            border=kenar,
            border_radius=RADIUS_MD,
            expand=expand,
            alignment=ft.alignment.Alignment(0, 0),
        )
        return yapilandir_etkilesim(
            kart, on_click=on_click,
            temel_golge=soft_shadow(12, 0, 0.16 if dolgu else 0.06, PALETTE["primary"]),
            hover_golge=soft_shadow(18, 0, 0.24 if dolgu else 0.10, PALETTE["primary"]),
        )

    page.title = _t("app.title")
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    page.bgcolor = PALETTE["bg"]
    page.theme = ft.Theme(font_family=FONT_FAMILY, color_scheme_seed=PALETTE["primary"])

    tarifler = json_tarifleri_yukle()
    secilen_malzemeler = set()

    favori_ids = veri_yukle(FAV_DOSYA)
    alisveris_listesi = set(veri_yukle(alisveris_DOSYA))
    haftalik_menu = veri_yukle(menu_DOSYA)
    tarif_notlari = veri_yukle(notlar_DOSYA)
    if not isinstance(tarif_notlari, dict):
        tarif_notlari = {}

    sadece_favoriler_mi = False
    fast_food_modu = False
    secilen_kalori_filtresi = "all"
    secilen_kategori_filtresi = "all"
    porsiyon_carpanlari = {}

    def bildirim_goster(metin, tur="info"):
        renkler = {"info": PALETTE["primary"], "success": PALETTE["sage_dark"], "warning": PALETTE["amber"]}
        page.snack_bar = ft.SnackBar(
            content=ft.Text(metin, color=PALETTE["white"], weight=ft.FontWeight.W_700, size=13),
            bgcolor=renkler.get(tur, PALETTE["primary"]),
        )
        page.snack_bar.open = True
        page.update()

    # SPLASH SCREEN
    splash_logo = ft.Container(
        width=150,
        height=150,
        content=ft.Stack([
            ft.Icon(ft.Icons.AUTO_AWESOME, size=90, color=PALETTE["primary_soft"]),
            ft.Container(
                content=ft.Icon(ft.Icons.RESTAURANT_MENU_ROUNDED, size=64, color=PALETTE["white"]),
                alignment=ft.alignment.Alignment(0, 0),
                width=150,
                height=150
            )
        ]),
        alignment=ft.alignment.Alignment(0, 0),
        bgcolor=PALETTE["primary"],
        border_radius=RADIUS_XL,
        scale=0.8,
        opacity=0.0,
        animate_scale=ft.Animation(650, ft.AnimationCurve.EASE_OUT_BACK),
        animate_opacity=ft.Animation(500, ft.AnimationCurve.EASE_IN),
        shadow=soft_shadow(30, 4, 0.28, PALETTE["primary"]),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS
    )

    splash_ekrani = ft.Container(
        content=ft.Column(
            [
                splash_logo,
                ft.Text(_t("app.title"), size=30, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                ft.Text(_t("app.tagline"), size=13, color=PALETTE["text_soft"], italic=True, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
                ft.Container(height=20),
                ft.ProgressRing(width=30, height=30, stroke_width=4, color=PALETTE["primary"])
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14
        ),
        alignment=ft.alignment.Alignment(0, 0),
        expand=True,
        gradient=ft.LinearGradient(
            begin=ft.alignment.Alignment(0, -1),
            end=ft.alignment.Alignment(0, 1),
            colors=[PALETTE["primary_soft"], PALETTE["bg"]]
        ),
        visible=True
    )

    # BUZDOLABI EKRANI
    kategori_listesi = ING.get("categories", [])

    header_baslik = ft.Text(_t("fridge.header_title"), size=23, weight=ft.FontWeight.W_900, color=PALETTE["text"])
    header_alt = ft.Text(_t("fridge.header_subtitle", count=len(tarifler)), size=12, color=PALETTE["text_soft"], weight=ft.FontWeight.W_700)

    header_kart = ft.Container(
        content=ft.Row([
            ft.Column([header_baslik, header_alt], expand=True, spacing=4),
            ft.Container(
                content=ft.Icon(ft.Icons.AUTO_AWESOME, size=28, color=PALETTE["primary_dark"]),
                padding=12,
                bgcolor=PALETTE["white"],
                border_radius=RADIUS_MD,
                border=b_all(1.4, PALETTE["primary_soft"]),
                shadow=soft_shadow(8, 1, 0.08),
            )
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=20,
        margin=m_symmetric(horizontal=16, vertical=12),
        gradient=ft.LinearGradient(
            begin=ft.alignment.Alignment(-1, -1),
            end=ft.alignment.Alignment(1, 1),
            colors=[PALETTE["primary_soft"], PALETTE["primary_bg"]]
        ),
        border_radius=RADIUS_LG,
        border=b_all(1.4, PALETTE["border_strong"]),
        shadow=soft_shadow(16, 1, 0.10)
    )

    ogun_secimi = ft.RadioGroup(
        value="aksam",
        content=ft.Row([
            ft.Radio(value="kahvalti", active_color=PALETTE["primary"],
                     label=_t("fridge.meal_breakfast"), label_style=ft.TextStyle(color=PALETTE["text"], weight=ft.FontWeight.W_700, size=12)),
            ft.Radio(value="ogle", active_color=PALETTE["primary"],
                     label=_t("fridge.meal_lunch"), label_style=ft.TextStyle(color=PALETTE["text"], weight=ft.FontWeight.W_700, size=12)),
            ft.Radio(value="aksam", active_color=PALETTE["primary"],
                     label=_t("fridge.meal_dinner"), label_style=ft.TextStyle(color=PALETTE["text"], weight=ft.FontWeight.W_700, size=12))
        ], alignment=ft.MainAxisAlignment.CENTER, wrap=True)
    )

    oneri_listesi = ft.Column(spacing=14)

    def ayarlar_penceresi_ac(e):
        dil_dropdown = ft.Dropdown(
            label=_t("settings_dialog.language_label"),
            value=aktif_dil,
            options=[
                ft.dropdown.Option("tr", "Türkçe 🇹🇷"),
                ft.dropdown.Option("en", "English 🇬🇧")
            ],
            border_color=PALETTE["border_strong"],
            border_width=1.6,
            text_style=ft.TextStyle(color=PALETTE["text"], size=13, weight=ft.FontWeight.W_700),
            label_style=ft.TextStyle(color=PALETTE["text_soft"], size=12, weight=ft.FontWeight.W_800),
            bgcolor=PALETTE["surface"],
            border_radius=RADIUS_SM
        )

        def ayari_kaydet_ve_kapat(_):
            nonlocal aktif_dil
            secilen_dil = dil_dropdown.value
            if secilen_dil:
                aktif_dil = secilen_dil
                ayarlar = veri_yukle(ayar_DOSYA)
                if not isinstance(ayarlar, dict):
                    ayarlar = {}
                ayarlar["dil"] = aktif_dil
                ayarlar["kullanici_adi"] = kullanici_adi
                veri_kaydet(ayar_DOSYA, ayarlar)
                dlg.open = False
                bildirim_goster(_t("settings_dialog.updated_toast"), "success")
                page.clean()
                page.run_task(main, page)

        def kullanici_adi_penceresi_ac(_):
            isim_duzenle = ft.TextField(
                label="Kullanıcı adı",
                value=kullanici_adi,
                hint_text="İsminizi yazın",
                max_length=30,
                capitalization=ft.TextCapitalization.WORDS,
                autofocus=True,
                border_color=PALETTE["border_strong"],
                focused_border_color=PALETTE["primary"],
                cursor_color=PALETTE["primary"],
                bgcolor=PALETTE["surface"],
            )

            def kullanici_adi_kaydet(_):
                nonlocal kullanici_adi
                yeni_isim = str(isim_duzenle.value or "").strip()[:30]
                kullanici_adi = yeni_isim
                ayarlar = veri_yukle(ayar_DOSYA)
                if not isinstance(ayarlar, dict):
                    ayarlar = {}
                ayarlar["dil"] = aktif_dil
                ayarlar["kullanici_adi"] = kullanici_adi
                veri_kaydet(ayar_DOSYA, ayarlar)
                isim_dlg.open = False
                page.update()

                # Kullanıcı adı değişikliğinin yeni hitaplarda devreye girmesi
                # için artık uygulamayı yeniden başlatmıyoruz. Kullanıcı
                # "Tamam" dediğinde uygulama tamamen kapanır; kullanıcı
                # uygulamayı yeniden açtığında yeni isim yüklenir.
                async def uygulamayi_kapat(_=None):
                    # Flet'te pencereyi doğrudan ve asenkron olarak yok et.
                    # os._exit() kullanmak event loop'u yarıda bıraktığı için
                    # pencerenin donmuş/Working... durumda kalmasına yol açabiliyor.
                    yeniden_baslat_dlg.open = False
                    page.update()
                    await page.window.destroy()

                yeniden_baslat_dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Kullanıcı adınız güncellendi", size=18, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                    content=ft.Text(
                        "Kullanıcı ismi değişikliğinin uygulanması için uygulamayı yeniden başlatmanız gerekmektedir.",
                        size=12, color=PALETTE["text_soft"]
                    ),
                    actions=[
                        ft.ElevatedButton(
                            "Tamam",
                            on_click=uygulamayi_kapat,
                            style=ft.ButtonStyle(bgcolor=PALETTE["primary"], color=PALETTE["white"])
                        )
                    ],
                    bgcolor=PALETTE["surface"],
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_LG),
                )
                page.overlay.append(yeniden_baslat_dlg)
                yeniden_baslat_dlg.open = True
                page.update()

            isim_dlg = ft.AlertDialog(
                title=ft.Text("Kullanıcı adım", size=18, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                content=ft.Container(
                    content=ft.Column([
                        ft.Text("İsterseniz isminizi belirleyebilir veya değiştirebilirsiniz.", size=11, color=PALETTE["text_soft"]),
                        isim_duzenle,
                    ], spacing=10),
                    width=320,
                ),
                actions=[
                    ft.TextButton("İptal", on_click=lambda _: (setattr(isim_dlg, "open", False), page.update())),
                    ft.ElevatedButton("Kullanıcı adı belirle", on_click=kullanici_adi_kaydet,
                                      style=ft.ButtonStyle(bgcolor=PALETTE["primary"], color=PALETTE["white"])),
                ],
                bgcolor=PALETTE["surface"],
                shape=ft.RoundedRectangleBorder(radius=RADIUS_LG),
            )
            page.overlay.append(isim_dlg)
            isim_dlg.open = True
            page.update()

        def hakkimizda_penceresi_ac(_):
            hakkimizda_dlg = ft.AlertDialog(
                title=ft.Row([
                    ft.Container(
                        content=ft.Icon(ft.Icons.RESTAURANT_MENU_ROUNDED, color=PALETTE["white"], size=22),
                        width=42, height=42,
                        alignment=ft.alignment.Alignment(0, 0),
                        bgcolor=PALETTE["primary"],
                        border_radius=12,
                    ),
                    ft.Text("Nöbetçi Ev", size=20, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                ], spacing=10),
                content=ft.Container(
                    content=ft.Column([
                        ft.Text("👨‍🍳 Nöbetçi Ev nedir?", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                        ft.Text(
                            "Her gün ne pişireceğim? derdini azaltmak ve mutfakta doğru seçeneği daha kolay bulmana yardımcı olmak için tasarlandı.",
                            size=11, color=PALETTE["text_soft"]
                        ),
                        ft.Divider(height=8, color=PALETTE["border"]),
                        ft.Text("💡 Neden yaptık?", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                        ft.Text(
                            "Dolabındaki malzemelerden tarif bulmayı, rastgele yemek seçmeyi ve haftalık menü oluşturmayı tek yerde toplamak için.",
                            size=11, color=PALETTE["text_soft"]
                        ),
                        ft.Divider(height=8, color=PALETTE["border"]),
                        ft.Text("🤖 Yemek Yardımcısı", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                        ft.Text(
                            "Yapay zekâ destekli yemek yardımcısı; tarif, fikir ve mutfak önerileri konusunda sana eşlik eder.",
                            size=11, color=PALETTE["text_soft"]
                        ),
                        ft.Divider(height=8, color=PALETTE["border"]),
                        ft.Text("📖 Tarif arşivi", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                        ft.Text(
                            "Uygulamadaki tarif arşivi, farklı malzeme ve öğün seçeneklerine göre yemek keşfetmeni sağlar.",
                            size=11, color=PALETTE["text_soft"]
                        ),
                        ft.Divider(height=8, color=PALETTE["border"]),
                        ft.Container(
                            content=ft.Column([
                                ft.Text("❤️ Bizi destekle", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                                ft.Text(
                                    "Nöbetçi Ev'i arkadaşlarınla ve çevrenle paylaşman bize verebileceğin en güzel desteklerden biri. ❤️",
                                    size=11, color=PALETTE["text_soft"]
                                ),
                            ], spacing=4),
                            padding=10,
                            bgcolor=PALETTE["primary_bg"],
                            border_radius=12,
                            border=b_all(1, PALETTE["primary_soft"]),
                        ),
                        ft.Container(height=2),
                        ft.Text("📱 Sürüm", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                        ft.Text("v1.0.0", size=11, color=PALETTE["text_soft"], weight=ft.FontWeight.W_700),
                    ], spacing=7, scroll=ft.ScrollMode.AUTO),
                    width=330,
                    height=430,
                ),
                actions=[
                    ft.TextButton(
                        "Kapat",
                        on_click=lambda _: (setattr(hakkimizda_dlg, "open", False), page.update()),
                        style=ft.ButtonStyle(color=PALETTE["primary_dark"])
                    )
                ],
                bgcolor=PALETTE["surface"],
                shape=ft.RoundedRectangleBorder(radius=RADIUS_LG)
            )
            page.overlay.append(hakkimizda_dlg)
            hakkimizda_dlg.open = True
            page.update()

        def bildirim_ayarlari_ac(_=None):
            mevcut = veri_yukle(ayar_DOSYA)
            if not isinstance(mevcut, dict): mevcut = {}
            bild = mevcut.get("bildirimler", {}) if isinstance(mevcut.get("bildirimler", {}), dict) else {}
            skt = ft.Switch(label="Yaklaşan malzeme uyarıları", value=bool(bild.get("skt", True)), active_color=PALETTE["primary"])
            gun = ft.Switch(label="Günün yemek önerisi", value=bool(bild.get("gunluk", True)), active_color=PALETTE["primary"])
            plan = ft.Switch(label="Haftalık plan hatırlatması", value=bool(bild.get("haftalik", True)), active_color=PALETTE["primary"])
            def kaydet(_):
                mevcut["bildirimler"] = {"skt": skt.value, "gunluk": gun.value, "haftalik": plan.value}
                veri_kaydet(ayar_DOSYA, mevcut); nd.open = False; page.update()
            nd = ft.AlertDialog(modal=True, title=ft.Text("🔔 Bildirimler", size=18, weight=ft.FontWeight.W_900), content=ft.Column([ft.Text("Uygulama içindeki akıllı hatırlatmaları buradan yönetebilirsin.", size=11.5, color=PALETTE["text_soft"]), skt, gun, plan], tight=True, spacing=6), actions=[ft.TextButton("Kapat", on_click=lambda e: (setattr(nd,"open",False),page.update())), ft.ElevatedButton("Kaydet", on_click=kaydet, style=ft.ButtonStyle(bgcolor=PALETTE["primary"], color=PALETTE["white"]))])
            page.overlay.append(nd); nd.open=True; page.update()

        def mutfak_temalari_ac(_=None):
            mevcut = ayarlari_oku()
            anim = ft.Switch(label="✨ Animasyonlar", value=bool(mevcut.get("animasyonlar", True)), active_color=PALETTE["primary"])
            ses = ft.Switch(label="🔊 Ses efektleri", value=bool(mevcut.get("ses_efektleri", True)), active_color=PALETTE["primary"])
            titre = ft.Switch(label="📳 Hafif titreşim", value=bool(mevcut.get("hafif_titresim", True)), active_color=PALETTE["primary"])
            mevsim = ft.Switch(label="🌦️ Mevsime göre ana ekran", value=bool(mevcut.get("mevsim_modu", True)), active_color=PALETTE["primary"])
            donem = ft.Dropdown(
                label="Dönemsel mutfak modu",
                value=mevcut.get("donem_modu", "auto"),
                options=[
                    ft.dropdown.Option("auto", "✨ Otomatik"),
                    ft.dropdown.Option("normal", "🍳 Normal"),
                    ft.dropdown.Option("ramazan", "🌙 Ramazan modu"),
                ],
                border_color=PALETTE["border_strong"], bgcolor=PALETTE["surface"]
            )
            def kaydet(_):
                mevcut.update({
                    "animasyonlar": bool(anim.value),
                    "ses_efektleri": bool(ses.value),
                    "hafif_titresim": bool(titre.value),
                    "mevsim_modu": bool(mevsim.value),
                    "donem_modu": donem.value or "auto",
                })
                veri_kaydet(ayar_DOSYA, mevcut)
                td.open=False; page.update()
                bildirim_goster("Mutfak deneyimi tercihleri kaydedildi.", "success")
            td = ft.AlertDialog(
                modal=True, title=ft.Text("🍳 Mutfak deneyimi", size=18, weight=ft.FontWeight.W_900),
                content=ft.Column([anim, ses, titre, mevsim, donem], tight=True, spacing=7),
                actions=[ft.TextButton("Kaydet", on_click=kaydet)],
                bgcolor=PALETTE["surface"], shape=ft.RoundedRectangleBorder(radius=RADIUS_LG)
            )
            page.overlay.append(td); td.open=True; page.update()

        dlg_baslik = ft.Text(_t("settings_dialog.title"), weight=ft.FontWeight.W_900, color=PALETTE["text"], size=18)

        dlg = ft.AlertDialog(
            title=dlg_baslik,
            content=ft.Container(
                content=ft.Column([
                    dil_dropdown,
                    ft.Container(height=8),
                    ft.TextButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.PERSON_OUTLINE_ROUNDED, color=PALETTE["primary_dark"], size=20),
                            ft.Column([
                                ft.Text("Kullanıcı adım", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                                ft.Text(kullanici_adi if kullanici_adi else "Henüz belirlenmedi", size=10.5, color=PALETTE["text_soft"]),
                            ], spacing=2, expand=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=PALETTE["text_faint"], size=20),
                        ], spacing=10),
                        on_click=kullanici_adi_penceresi_ac,
                        style=ft.ButtonStyle(padding=10, shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    ),
                    ft.Divider(height=1, color=PALETTE["border"]),
                    ft.TextButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.NOTIFICATIONS_NONE_ROUNDED, color=PALETTE["primary_dark"], size=20),
                            ft.Column([ft.Text("Bildirimler", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]), ft.Text("Akıllı hatırlatmaları yönet", size=10.5, color=PALETTE["text_soft"])], spacing=2, expand=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=PALETTE["text_faint"], size=20),
                        ], spacing=10), on_click=bildirim_ayarlari_ac, style=ft.ButtonStyle(padding=10, shape=ft.RoundedRectangleBorder(radius=RADIUS_SM))),
                    ft.Divider(height=1, color=PALETTE["border"]),
                    ft.TextButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, color=PALETTE["primary_dark"], size=20),
                            ft.Column([
                                ft.Text("Hakkımızda", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                                ft.Text("Nöbetçi Ev hakkında daha fazla bilgi", size=10.5, color=PALETTE["text_soft"]),
                            ], spacing=2, expand=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=PALETTE["text_faint"], size=20),
                        ], spacing=10),
                        on_click=hakkimizda_penceresi_ac,
                        style=ft.ButtonStyle(
                            padding=10,
                            shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                        ),
                    ),
                    ft.Divider(height=1, color=PALETTE["border"]),
                    ft.TextButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BAR_CHART_ROUNDED, color=PALETTE["primary_dark"], size=20),
                            ft.Column([ft.Text("Kişisel istatistikler", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                                       ft.Text("Mutfak maceranı ve başarılarını gör", size=10.5, color=PALETTE["text_soft"])], spacing=2, expand=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=PALETTE["text_faint"], size=20),
                        ], spacing=10), on_click=kisisel_istatistik_ac,
                        style=ft.ButtonStyle(padding=10, shape=ft.RoundedRectangleBorder(radius=RADIUS_SM))
                    ),
                    ft.TextButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.PALETTE_ROUNDED, color=PALETTE["primary_dark"], size=20),
                            ft.Column([ft.Text("Mutfak deneyimi", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                                       ft.Text("Animasyon, ses, titreşim, mevsim ve dönem modları", size=10.5, color=PALETTE["text_soft"])], spacing=2, expand=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=PALETTE["text_faint"], size=20),
                        ], spacing=10), on_click=mutfak_temalari_ac,
                        style=ft.ButtonStyle(padding=10, shape=ft.RoundedRectangleBorder(radius=RADIUS_SM))
                    ),
                    ft.Text(_t("settings_dialog.footer_note"), size=11, italic=True, color=PALETTE["text_soft"])
                ], spacing=8),
                width=320,
                height=390
            ),
            actions=[
                ft.TextButton(_t("common.close"), on_click=lambda _: (setattr(dlg, 'open', False), page.update()),
                               style=ft.ButtonStyle(color=PALETTE["text_soft"])),
                ft.ElevatedButton(_t("settings_dialog.save_button"), on_click=ayari_kaydet_ve_kapat,
                                   style=ft.ButtonStyle(bgcolor=PALETTE["primary"], color=PALETTE["white"],
                                                         shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)))
            ],
            bgcolor=PALETTE["surface"],
            shape=ft.RoundedRectangleBorder(radius=RADIUS_LG)
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def alisveris_listesini_goster(e):
        liste_view = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)

        def guncelle_gorunum():
            liste_view.controls.clear()
            if not alisveris_listesi:
                liste_view.controls.append(
                    ft.Text(_t("shopping_dialog.empty"), italic=True, color=PALETTE["text_soft"], weight=ft.FontWeight.W_500)
                )
            else:
                for item in sorted(list(alisveris_listesi)):
                    def sil_item(_, m=item):
                        alisveris_listesi.discard(m)
                        veri_kaydet(alisveris_DOSYA, list(alisveris_listesi))
                        guncelle_gorunum()
                        page.update()

                    liste_view.controls.append(
                        ft.Row([
                            ft.Text(f"• {_ing(item)}", size=14, weight=ft.FontWeight.W_700, color=PALETTE["text"], expand=True),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE_ROUNDED, icon_color=PALETTE["danger"],
                                          tooltip=_t("common.delete_tooltip"), on_click=sil_item)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                    )

        guncelle_gorunum()

        async def listeyi_kopyala(_):
            if not alisveris_listesi:
                return
            metin = _t("shopping_dialog.clipboard_header") + "\n" + "\n".join([f"• {_ing(item)}" for item in sorted(list(alisveris_listesi))])
            await ft.Clipboard().set(metin)
            bildirim_goster(_t("shopping_dialog.copied_toast"), "success")

        dlg = ft.AlertDialog(
            title=ft.Column([
                ft.Text(_t("shopping_dialog.title"), weight=ft.FontWeight.W_900, color=PALETTE["text"], size=16),
                ft.Text(_t("shopping_dialog.subtitle"), size=11, color=PALETTE["text_soft"], italic=True, weight=ft.FontWeight.W_600)
            ], spacing=2),
            content=ft.Container(
                content=ft.Column([
                    liste_view,
                    ft.Container(height=10),
                    ft.ElevatedButton(
                        _t("shopping_dialog.copy_button"),
                        icon=ft.Icons.COPY_ROUNDED,
                        on_click=listeyi_kopyala,
                        style=ft.ButtonStyle(bgcolor=PALETTE["primary"], color=PALETTE["white"], shape=ft.RoundedRectangleBorder(radius=RADIUS_SM))
                    )
                ], spacing=5),
                width=320,
                height=380
            ),
            actions=[ft.TextButton(_t("common.close"), on_click=lambda _: (setattr(dlg, 'open', False), page.update()),
                                    style=ft.ButtonStyle(color=PALETTE["text_soft"]))],
            bgcolor=PALETTE["surface"],
            shape=ft.RoundedRectangleBorder(radius=RADIUS_LG)
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def haftalik_menu_goster(e):
        menu_view = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)

        def menu_guncelle():
            menu_view.controls.clear()
            if not haftalik_menu:
                menu_view.controls.append(
                    ft.Text(_t("weekly_menu_dialog.empty"), italic=True, color=PALETTE["text_soft"], weight=ft.FontWeight.W_500)
                )
            else:
                for idx, m_adi in enumerate(haftalik_menu):
                    def sil_menu(_, i=idx):
                        haftalik_menu.pop(i)
                        veri_kaydet(menu_DOSYA, haftalik_menu)
                        menu_guncelle()
                        page.update()
                    menu_view.controls.append(
                        ft.Row([
                            ft.Text(f"📅 {m_adi}", size=13, color=PALETTE["text"], expand=True, weight=ft.FontWeight.W_700),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE_ROUNDED, icon_color=PALETTE["danger"],
                                          tooltip=_t("common.delete_tooltip"), on_click=sil_menu)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                    )

        menu_guncelle()

        dlg = ft.AlertDialog(
            title=ft.Text(_t("weekly_menu_dialog.title"), weight=ft.FontWeight.W_900, color=PALETTE["text"], size=16),
            content=ft.Container(content=menu_view, width=320, height=300),
            actions=[ft.TextButton(_t("common.close"), on_click=lambda _: (setattr(dlg, 'open', False), page.update()),
                                    style=ft.ButtonStyle(color=PALETTE["text_soft"]))],
            bgcolor=PALETTE["surface"],
            shape=ft.RoundedRectangleBorder(radius=RADIUS_LG)
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def menuye_ekle(tarif_adi):
        if tarif_adi not in haftalik_menu:
            haftalik_menu.append(tarif_adi)
            veri_kaydet(menu_DOSYA, haftalik_menu)
            bildirim_goster(_t("recipe_card.added_to_menu_toast", name=tarif_adi), "success")

    def ayarlari_oku():
        a = veri_yukle(ayar_DOSYA)
        return a if isinstance(a, dict) else {}

    def istatistikleri_oku():
        a = ayarlari_oku()
        st = a.get("istatistikler", {})
        if not isinstance(st, dict):
            st = {}
        return {
            "tamamlanan_tarifler": dict(st.get("tamamlanan_tarifler", {}) or {}),
            "toplam_tamamlanan": int(st.get("toplam_tamamlanan", 0) or 0),
            "favoriye_eklenen": int(st.get("favoriye_eklenen", 0) or 0),
            "son_tamamlanan": str(st.get("son_tamamlanan", "") or ""),
            "xp": int(st.get("xp", 0) or 0),
            "seviye": int(st.get("seviye", 1) or 1),
            "streak": int(st.get("streak", 0) or 0),
            "en_uzun_streak": int(st.get("en_uzun_streak", 0) or 0),
            "son_gorev_tarihi": str(st.get("son_gorev_tarihi", "") or ""),
            "gunluk_gorev_tarihi": str(st.get("gunluk_gorev_tarihi", "") or ""),
            "gunluk_gorev_tamamlandi": bool(st.get("gunluk_gorev_tamamlandi", False)),
            "gunluk_gorev_hedef": int(st.get("gunluk_gorev_hedef", 1) or 1),
            "gunluk_tamamlanan": int(st.get("gunluk_tamamlanan", 0) or 0),
            "xp_odul_seviyeleri": list(st.get("xp_odul_seviyeleri", []) or []),
            "tamamlanma_gunleri": dict(st.get("tamamlanma_gunleri", {}) or {}),
        }

    def istatistikleri_kaydet(st):
        a = ayarlari_oku()
        a["istatistikler"] = st
        veri_kaydet(ayar_DOSYA, a)

    def ses_efekti_cal(tur="tap"):
        a = ayarlari_oku()
        if not bool(a.get("ses_efektleri", True)):
            return
        # Windows önizlemesinde hafif sistem sesi; Android'de hata vermeden pas geçer.
        try:
            import winsound
            if tur == "success":
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

    async def hafif_titresim():
        a = ayarlari_oku()
        if not bool(a.get("hafif_titresim", True)):
            return
        # Flet masaüstü önizlemesinde gerçek titreşim API'si yoktur.
        # Android paketinde native titreşim bağlandığında bu ayar kullanılabilir.
        await asyncio.sleep(0)

    async def basari_animasyonu(mesaj="🎉 Harika!"):
        a = ayarlari_oku()
        if not bool(a.get("animasyonlar", True)):
            return
        dlg = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=ft.Column([
                    ft.Text("✨", size=54, text_align=ft.TextAlign.CENTER),
                    ft.Text(mesaj, size=20, weight=ft.FontWeight.W_900,
                            color=PALETTE["text"], text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                padding=20, bgcolor=PALETTE["surface"], border_radius=RADIUS_LG,
            ),
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()
        ses_efekti_cal("success")
        await hafif_titresim()
        await asyncio.sleep(1.05)
        dlg.open = False
        page.update()

    async def favori_animasyonu_goster(tarif_adi, eklendi):
        a = ayarlari_oku()
        if not bool(a.get("animasyonlar", True)):
            return
        await asyncio.sleep(0.08)
        await basari_animasyonu("❤️ Favorilere eklendi!" if eklendi else "💔 Favorilerden çıkarıldı")

    def tarif_tamamlandi_kaydet(tarif_adi):
        st = istatistikleri_oku()
        st["toplam_tamamlanan"] += 1
        st["tamamlanan_tarifler"][tarif_adi] = int(st["tamamlanan_tarifler"].get(tarif_adi, 0)) + 1
        st["son_tamamlanan"] = tarif_adi
        # Oyunlaştırma: +25 XP, streak, günlük görev ve rozetler.
        st, onceki_seviye, acilan = oyun_guncelle_tarif_tamamlandi(tarif_adi)
        istatistikleri_kaydet(st)
        ses_efekti_cal("success")
        if st["seviye"] > onceki_seviye:
            page.run_task(basari_animasyonu, f"🎁 Seviye atladın! Seviye {st['seviye']} · Ödül: {'🍳 Yeni Şef' if st['seviye'] == 2 else '🏅 Özel rozet'}")
        elif acilan:
            page.run_task(basari_animasyonu, f"🏅 Yeni rozet: {acilan[0][1]}")
        elif st.get("gunluk_gorev_tamamlandi"):
            page.run_task(basari_animasyonu, "🎯 Günlük görev tamamlandı! +25 XP")
        page.run_task(afiyet_olsun_ekrani, tarif_adi)

    async def afiyet_olsun_ekrani(tarif_adi):
        a = ayarlari_oku()
        if not bool(a.get("animasyonlar", True)):
            return
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("🎉 Afiyet olsun!", size=23, weight=ft.FontWeight.W_900,
                          color=PALETTE["text"], text_align=ft.TextAlign.CENTER),
            content=ft.Column([
                ft.Text(f"“{tarif_adi}” tamamlandı.", size=14, weight=ft.FontWeight.W_800,
                        color=PALETTE["primary_dark"], text_align=ft.TextAlign.CENTER),
                ft.Text("Mutfakta bir küçük başarı daha! 🍽️✨", size=12,
                        color=PALETTE["text_soft"], text_align=ft.TextAlign.CENTER),
            ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            actions=[ft.TextButton("Kapat", on_click=lambda e: (setattr(dlg, "open", False), page.update()))],
            bgcolor=PALETTE["surface"], shape=ft.RoundedRectangleBorder(radius=RADIUS_LG),
        )
        page.overlay.append(dlg); dlg.open = True; page.update()
        await hafif_titresim()
        await asyncio.sleep(1.7)
        if dlg.open:
            dlg.open = False
            page.update()

    def _seviye_bilgisi(xp):
        seviye = max(1, int(xp // 100) + 1)
        mevcut = xp % 100
        sonraki = 100
        return seviye, mevcut, sonraki

    def _bugun_tarih():
        return datetime.now().date().isoformat()

    def _hafta_anahtari(tarih=None):
        d = datetime.fromisoformat(tarih or _bugun_tarih()).date()
        yil, hafta, _ = d.isocalendar()
        return f"{yil}-W{hafta:02d}"

    def rozetleri_hesapla(st):
        toplam = int(st.get("toplam_tamamlanan", 0))
        streak = int(st.get("streak", 0))
        favori = int(st.get("favoriye_eklenen", 0))
        xp = int(st.get("xp", 0))
        gun_sayisi = len(st.get("tamamlanma_gunleri", {}) or {})
        rozetler = []
        if toplam >= 1: rozetler.append(("🍳", "İlk Tarif", "İlk tarifini tamamladın."))
        if toplam >= 5: rozetler.append(("🥄", "Mutfak Isınıyor", "5 tarif tamamladın."))
        if toplam >= 10: rozetler.append(("👨‍🍳", "Ev Şefi", "10 tarif tamamladın."))
        if toplam >= 25: rozetler.append(("🏆", "Usta Şef", "25 tarif tamamladın."))
        if toplam >= 50: rozetler.append(("👑", "Mutfak Efsanesi", "50 tarif tamamladın."))
        if streak >= 3: rozetler.append(("🔥", "Alev Aldı", "3 günlük seri yaptın."))
        if streak >= 7: rozetler.append(("🔥", "7 Günlük Şef", "7 gün üst üste mutfaktasın."))
        if favori >= 5: rozetler.append(("❤️", "Tarif Koleksiyoncusu", "5 tarif favoriledin."))
        if gun_sayisi >= 20: rozetler.append(("📅", "Düzenli Şef", "20 farklı günde tarif tamamladın."))
        if xp >= 500: rozetler.append(("⭐", "XP Ustası", "500 XP kazandın."))
        return rozetler

    def oyun_guncelle_tarif_tamamlandi(tarif_adi):
        st = istatistikleri_oku()
        bugun = _bugun_tarih()
        onceki_seviye = _seviye_bilgisi(st["xp"])[0]
        st["xp"] += 25
        st["seviye"] = _seviye_bilgisi(st["xp"])[0]
        gunler = st.setdefault("tamamlanma_gunleri", {})
        gunler[bugun] = int(gunler.get(bugun, 0)) + 1
        son_gun = str(st.get("son_gorev_tarihi", "") or "")
        if son_gun != bugun:
            if son_gun:
                try:
                    fark = (datetime.fromisoformat(bugun).date() - datetime.fromisoformat(son_gun).date()).days
                except Exception:
                    fark = 999
                st["streak"] = st["streak"] + 1 if fark == 1 else 1
            else:
                st["streak"] = 1
            st["son_gorev_tarihi"] = bugun
        st["en_uzun_streak"] = max(st["en_uzun_streak"], st["streak"])
        if st.get("gunluk_gorev_tarihi") != bugun:
            st["gunluk_gorev_tarihi"] = bugun
            st["gunluk_gorev_tamamlandi"] = False
            st["gunluk_tamamlanan"] = 0
            st["gunluk_gorev_hedef"] = 1
        st["gunluk_tamamlanan"] += 1
        if st["gunluk_tamamlanan"] >= st["gunluk_gorev_hedef"]:
            st["gunluk_gorev_tamamlandi"] = True
        yeni_rozetler = rozetleri_hesapla(st)
        eski_rozetler = st.get("kazanilan_rozetler", []) or []
        yeni_adi = [x[1] for x in yeni_rozetler]
        acilan = [r for r in yeni_rozetler if r[1] not in eski_rozetler]
        st["kazanilan_rozetler"] = yeni_adi
        st["gunluk_gorev_odulu_verildi"] = bool(st.get("gunluk_gorev_odulu_verildi", False))
        if st["gunluk_gorev_tamamlandi"] and not st["gunluk_gorev_odulu_verildi"]:
            st["xp"] += 25
            st["seviye"] = _seviye_bilgisi(st["xp"])[0]
            st["gunluk_gorev_odulu_verildi"] = True
        istatistikleri_kaydet(st)
        return st, onceki_seviye, acilan

    def mutfak_karnesi_ac(_=None):
        st = istatistikleri_oku()
        seviye, ilerleme, _ = _seviye_bilgisi(st["xp"])
        rozetler = rozetleri_hesapla(st)
        bugun = _bugun_tarih()
        hafta = _hafta_anahtari()
        hafta_sayisi = sum(v for k, v in st.get("tamamlanma_gunleri", {}).items() if _hafta_anahtari(k) == hafta)
        ay = bugun[:7]
        ay_sayisi = sum(v for k, v in st.get("tamamlanma_gunleri", {}).items() if k.startswith(ay))
        odul = {"2": "🥉 Mutfak Çırağı", "3": "🥈 Usta Yardımcısı", "4": "🥇 Ev Şefi"}.get(str(seviye), "👑 Mutfak Efsanesi" if seviye >= 5 else "🍳 Yeni Şef")
        kontroller = [
            ft.Text("🏆 Mutfak Karnen", size=20, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
            ft.Container(content=ft.Column([
                ft.Text(f"Seviye {seviye} · {odul}", size=15, weight=ft.FontWeight.W_900, color=PALETTE["primary_dark"]),
                ft.ProgressBar(value=ilerleme/100, color=PALETTE["primary"], bgcolor=PALETTE["border"]),
                ft.Text(f"⭐ {st['xp']} XP · Sonraki seviyeye {100-ilerleme} XP", size=11, color=PALETTE["text_soft"]),
            ], spacing=6), padding=12, bgcolor=PALETTE["primary_bg"], border_radius=RADIUS_MD),
            ft.Row([
                ft.Column([ft.Text(str(st["streak"]), size=23, weight=ft.FontWeight.W_900, color=PALETTE["primary_dark"]), ft.Text("🔥 Seri", size=10, color=PALETTE["text_soft"])], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Column([ft.Text(str(hafta_sayisi), size=23, weight=ft.FontWeight.W_900, color=PALETTE["primary_dark"]), ft.Text("🥇 Bu hafta", size=10, color=PALETTE["text_soft"])], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Column([ft.Text(str(ay_sayisi), size=23, weight=ft.FontWeight.W_900, color=PALETTE["primary_dark"]), ft.Text("📊 Bu ay", size=10, color=PALETTE["text_soft"])], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
            ft.Text(f"🎯 Günlük görev: {'Tamamlandı! +25 XP' if st.get('gunluk_gorev_tamamlandi') else '1 tarif tamamla · +25 XP'}", size=12, weight=ft.FontWeight.W_800, color=PALETTE["text"]),
            ft.Text(f"🏅 Rozetler ({len(rozetler)})", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
        ]
        if rozetler:
            for ikon, ad, aciklama in rozetler:
                kontroller.append(ft.Container(content=ft.Row([ft.Text(ikon, size=24), ft.Column([ft.Text(ad, size=11.5, weight=ft.FontWeight.W_900, color=PALETTE["text"]), ft.Text(aciklama, size=10, color=PALETTE["text_soft"])], spacing=1, expand=True)], spacing=8), padding=8, bgcolor=PALETTE["surface_alt"], border=b_all(1, PALETTE["border"]), border_radius=RADIUS_SM))
        else:
            kontroller.append(ft.Text("İlk rozetin için bir tarif tamamla! 🍳", size=11, color=PALETTE["text_soft"]))
        kontroller.append(ft.Text(f"🥇 Haftanın mutfak şampiyonu: {hafta_sayisi} tarifle sen!", size=11.5, weight=ft.FontWeight.W_800, color=PALETTE["primary_dark"]))
        kontroller.append(ft.Text(f"📊 {datetime.now().strftime('%B %Y')} özeti: {ay_sayisi} tarif tamamlandı.", size=11.5, color=PALETTE["text_soft"]))
        dlg = ft.AlertDialog(modal=True, content=ft.Container(content=ft.Column(kontroller, tight=True, spacing=8, scroll=ft.ScrollMode.AUTO), width=330, height=570), actions=[ft.TextButton("Kapat", on_click=lambda e: (setattr(dlg,"open",False), page.update()))], bgcolor=PALETTE["surface"], shape=ft.RoundedRectangleBorder(radius=RADIUS_LG))
        page.overlay.append(dlg); dlg.open=True; page.update()

    def kisisel_istatistik_ac(_=None):
        st = istatistikleri_oku()
        toplam = st["toplam_tamamlanan"]
        en_cok = sorted(st["tamamlanan_tarifler"].items(), key=lambda x: x[1], reverse=True)[:3]
        satirlar = [
            ft.Text("🏆 Kişisel Mutfak İstatistiklerin", size=19, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
            ft.Container(
                content=ft.Row([
                    ft.Column([ft.Text(str(toplam), size=25, weight=ft.FontWeight.W_900, color=PALETTE["primary_dark"]),
                               ft.Text("Tamamlanan tarif", size=10, color=PALETTE["text_soft"])], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Column([ft.Text(str(len(favori_ids)), size=25, weight=ft.FontWeight.W_900, color=PALETTE["primary_dark"]),
                               ft.Text("Favori tarif", size=10, color=PALETTE["text_soft"])], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
                padding=14, bgcolor=PALETTE["primary_bg"], border_radius=RADIUS_MD
            ),
            ft.Text("🔥 En çok yaptıkların", size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
        ]
        if en_cok:
            for ad, adet in en_cok:
                satirlar.append(ft.Text(f"• {ad}  ×{adet}", size=12, color=PALETTE["text_soft"], weight=ft.FontWeight.W_700))
        else:
            satirlar.append(ft.Text("Henüz tamamladığın tarif yok. İlk tarifini bitir! 🍳", size=11.5, color=PALETTE["text_soft"]))
        dlg = ft.AlertDialog(
            modal=True, content=ft.Container(content=ft.Column(satirlar, tight=True, spacing=9), width=320),
            actions=[ft.TextButton("Kapat", on_click=lambda e: (setattr(dlg, "open", False), page.update()))],
            bgcolor=PALETTE["surface"], shape=ft.RoundedRectangleBorder(radius=RADIUS_LG)
        )
        page.overlay.append(dlg); dlg.open=True; page.update()

    def favori_durumu_degistir(tarif_adi):
        nonlocal favori_ids
        eklendi = tarif_adi not in favori_ids
        if tarif_adi in favori_ids:
            favori_ids.remove(tarif_adi)
        else:
            favori_ids.append(tarif_adi)
        veri_kaydet(FAV_DOSYA, favori_ids)
        # Küçük favori animasyonu: liste yenilenmeden önce kartın durumunu güncelle.
        if eklendi:
            st = istatistikleri_oku()
            st["favoriye_eklenen"] += 1
            istatistikleri_kaydet(st)
            ses_efekti_cal("favorite")
        page.run_task(favori_animasyonu_goster, tarif_adi, eklendi)
        page.run_task(yemek_oner, None)

    def malzeme_degisti(e):
        if e.control.value:
            secilen_malzemeler.add(e.control.data)
        else:
            secilen_malzemeler.discard(e.control.data)

    def kalori_filtre_degisti(e):
        nonlocal secilen_kalori_filtresi
        secilen_kalori_filtresi = e.control.value
        page.run_task(yemek_oner, None)

    def kategori_filtre_degisti(e):
        nonlocal secilen_kategori_filtresi
        secilen_kategori_filtresi = e.control.value
        page.run_task(yemek_oner, None)

    def fast_food_modu_degisti(e):
        nonlocal fast_food_modu
        fast_food_modu = e.control.value
        buzdolabi_alani.visible = not fast_food_modu
        page.run_task(yemek_oner, None)

    def favori_filtre_degisti(e):
        nonlocal sadece_favoriler_mi
        sadece_favoriler_mi = e.control.value
        page.run_task(yemek_oner, None)

    async def rastgele_tarif_getir(e):
        """Şans butonu: kısa zar animasyonu ardından tarifi yumuşakça açar."""
        if not tarifler:
            return

        havuz = tarifler
        if fast_food_modu:
            havuz = [x for x in tarifler if "fastfood" in x.get("ogun", [])] or tarifler
        elif secilen_kategori_filtresi == "desserts":
            havuz = [x for x in tarifler if x.get("id", 0) > 120] or tarifler
        elif secilen_kategori_filtresi == "meals":
            havuz = [x for x in tarifler if x.get("id", 0) <= 120] or tarifler

        secilen = random.choice(havuz)

        zar = ft.Text("🎲", size=62, text_align=ft.TextAlign.CENTER)
        zar_alt = ft.Text(
            "Şansını deniyoruz..." if aktif_dil == "tr" else "Rolling the dice...",
            size=12, color=PALETTE["text_soft"], weight=ft.FontWeight.W_700,
            text_align=ft.TextAlign.CENTER,
        )

        zar_kutu = ft.Container(
            content=ft.Column([
                zar,
                zar_alt,
                ft.ProgressRing(width=22, height=22, stroke_width=3, color=PALETTE["primary"]),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            width=280, height=180,
            alignment=ft.alignment.Alignment(0, 0),
            scale=0.82, opacity=0.0,
            animate_scale=ft.Animation(180, ft.AnimationCurve.EASE_OUT_BACK),
            animate_opacity=ft.Animation(160, ft.AnimationCurve.EASE_IN_OUT),
        )

        def dialog_kapat(_):
            dialog.open = False
            page.update()

        dialog = ft.AlertDialog(
            title=ft.Text(
                _t("lucky_dialog.title"),
                size=17, weight=ft.FontWeight.W_900, color=PALETTE["text"]
            ),
            content=zar_kutu,
            actions=[],
            bgcolor=PALETTE["surface"],
            shape=ft.RoundedRectangleBorder(radius=RADIUS_LG),
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

        await asyncio.sleep(0.04)
        zar_kutu.scale = 1.0
        zar_kutu.opacity = 1.0
        page.update()

        zar_yuzleri = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅", "🎲"]
        for i in range(10):
            zar.value = zar_yuzleri[i % len(zar_yuzleri)]
            zar.scale = 1.12 if i % 2 == 0 else 0.90
            page.update()
            await asyncio.sleep(0.095)

        zar.value = "✨"
        zar.scale = 1.18
        zar_alt.value = (
            f"{secilen.get('ad', 'Tarif')} seçildi! 🍽️"
            if aktif_dil == "tr"
            else f"{secilen.get('ad', 'Recipe')} selected! 🍽️"
        )
        page.update()
        await asyncio.sleep(0.22)

        adimlari = [
            ft.Row([
                ft.Checkbox(fill_color=PALETTE["primary"]),
                ft.Text(adim, size=12, color=PALETTE["text"], weight=ft.FontWeight.W_600, expand=True)
            ], vertical_alignment=ft.CrossAxisAlignment.START)
            for adim in secilen.get("hazirlanis", [])
        ]

        kisi_sayisi_n = sayi_ayikla(secilen.get("kisi_sayisi", ""), 2)

        tarif_icerigi = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(
                        f"{_t('recipe_card.duration_label')}: {secilen.get('sure', '-')}",
                        size=11, color=PALETTE["text"], weight=ft.FontWeight.W_800
                    ),
                    ft.Text(
                        f"{_t('recipe_card.calories_label')}: {secilen.get('kalori', '-')} {_t('recipe_card.calories_unit')}",
                        size=11, color=PALETTE["text"], weight=ft.FontWeight.W_800
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text(
                    f"{_t('recipe_card.protein_label')}: {secilen.get('protein', '-')}  •  {_t('recipe_card.carbs_label')}: {secilen.get('karbonhidrat', '-')}",
                    size=11, color=PALETTE["text"], weight=ft.FontWeight.W_700
                ),
                ft.Text(
                    _t("recipe_card.servings_label", count=kisi_sayisi_n),
                    size=11, color=PALETTE["text"], weight=ft.FontWeight.W_700
                ),
                ft.Text(
                    f"{_t('recipe_card.ingredients_label')}: " +
                    ", ".join(_ing(m) for m in secilen.get("malzemeler", [])),
                    size=12, color=PALETTE["text"], weight=ft.FontWeight.W_600
                ),
                ft.Divider(height=10, color=PALETTE["border"]),
                ft.Text(_t("recipe_card.steps_title"), weight=ft.FontWeight.W_900, size=13, color=PALETTE["text"]),
                ft.Column(adimlari, spacing=8)
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            width=340, opacity=0.0, scale=0.90,
            animate_opacity=ft.Animation(260, ft.AnimationCurve.EASE_IN_OUT),
            animate_scale=ft.Animation(320, ft.AnimationCurve.EASE_OUT_BACK),
        )

        dialog.title = ft.Text(
            f"{_t('lucky_dialog.title')}\n{secilen['ad']}",
            size=17, weight=ft.FontWeight.W_900, color=PALETTE["text"]
        )
        dialog.content = tarif_icerigi
        async def tekrar_zar_at(_):
            dialog.open = False
            page.update()
            await asyncio.sleep(0.08)
            await rastgele_tarif_getir(None)

        dialog.actions = [
            ft.TextButton(
                "Tekrar At 🎲" if aktif_dil == "tr" else "Roll Again 🎲",
                on_click=lambda e: page.run_task(tekrar_zar_at, e),
                style=ft.ButtonStyle(color=PALETTE["primary_dark"])
            ),
            ft.TextButton(
                _t("lucky_dialog.confirm_button"),
                on_click=dialog_kapat,
                style=ft.ButtonStyle(color=PALETTE["text_soft"])
            )
        ]
        page.update()
        await asyncio.sleep(0.04)
        tarif_icerigi.opacity = 1.0
        tarif_icerigi.scale = 1.0
        page.update()

    async def yemek_oner(e):
        oneri_listesi.controls.clear()
        secilen_ogun = ogun_secimi.value
        eslesenler = []

        for t in tarifler:
            tarif_id = t.get("id", 0)
            tarif_adi = t["ad"]
            tarif_malz = set(t.get("malzemeler", []))
            tarif_ogunler = t.get("ogun", [])
            tarif_kalori = t.get("kalori", 300)

            if secilen_kategori_filtresi == "meals" and tarif_id > 120:
                continue
            if secilen_kategori_filtresi == "desserts" and tarif_id <= 120:
                continue

            if secilen_kalori_filtresi == "low_cal" and tarif_kalori >= 250:
                continue
            if secilen_kalori_filtresi == "high_protein" and sayi_ayikla(t.get("protein", "0g")) < 20:
                continue

            if sadece_favoriler_mi and tarif_adi not in favori_ids:
                continue

            if secilen_ogun and tarif_ogunler and secilen_ogun not in tarif_ogunler:
                continue

            sezon_uyari_var = bool(tarif_malz.intersection(MEVSIM_DISI_MALZEMELER))
            eksikler = tarif_malz - secilen_malzemeler
            eksik_sayisi = len(eksikler)

            if secilen_malzemeler:
                if len(secilen_malzemeler.intersection(tarif_malz)) == 0:
                    continue

            eslesenler.append({
                "ad": tarif_adi,
                "sure": t.get("sure", "-"),
                "kisi_sayisi": t.get("kisi_sayisi", "4 Kişilik"),
                "kalori": tarif_kalori,
                "protein": t.get("protein", "-"),
                "karbonhidrat": t.get("karbonhidrat", "-"),
                "tum_malzemeler": t.get("malzemeler", []),
                "hazirlanis": t.get("hazirlanis", []),
                "tam_mı": eksik_sayisi == 0,
                "eksikler": list(eksikler),
                "eksik_sayisi": eksik_sayisi,
                "sezon_uyari": sezon_uyari_var,
                "zorluk": tarif_zorlugu_hesapla(t)
            })

        if not fast_food_modu:
            eslesenler.sort(key=lambda x: (not x["tam_mı"], x["eksik_sayisi"]))

        yeni_kartlar = []

        if eslesenler:
            for i, t in enumerate(eslesenler):
                t_adi = t["ad"]
                is_fav = t_adi in favori_ids
                fav_icon = ft.Icons.FAVORITE_ROUNDED if is_fav else ft.Icons.FAVORITE_BORDER_ROUNDED
                fav_color = PALETTE["danger"] if is_fav else PALETTE["text_faint"]

                zorluk_renk = {"Kolay": (PALETTE["sage_bg"], PALETTE["sage_dark"]), "Orta": (PALETTE["amber_bg"], PALETTE["amber"]), "Zor": (PALETTE["danger_bg"], PALETTE["danger"])}
                z_bg, z_fg = zorluk_renk.get(t.get("zorluk", "Orta"), zorluk_renk["Orta"])

                current_porsiyon_katsayi = porsiyon_carpanlari.get(t_adi, 1.0)
                rozetler_kolonu = []

                if t["tam_mı"]:
                    rozetler_kolonu.append(
                        ft.Container(
                            content=ft.Text(_t("recipe_card.ready_badge"), size=11, weight=ft.FontWeight.W_800, color=PALETTE["sage_dark"]),
                            padding=m_symmetric(horizontal=10, vertical=5),
                            bgcolor=PALETTE["sage_bg"],
                            border_radius=RADIUS_SM,
                            border=b_all(1, PALETTE["sage"])
                        )
                    )
                else:
                    def alisverise_ekle_tikle(_, eksiks=t["eksikler"]):
                        for eksik in eksiks:
                            alisveris_listesi.add(eksik)
                        veri_kaydet(alisveris_DOSYA, list(alisveris_listesi))
                        bildirim_goster(_t("recipe_card.missing_added_toast"), "warning")

                    eksik_metin = _t("recipe_card.missing_badge", count=t['eksik_sayisi'], items=', '.join(_ing(m) for m in t['eksikler']))
                    rozetler_kolonu.append(
                        ft.Row([
                            ft.Container(
                                content=ft.Text(eksik_metin, size=11, color=PALETTE["primary_dark"], weight=ft.FontWeight.W_800),
                                padding=m_symmetric(horizontal=10, vertical=5),
                                bgcolor=PALETTE["primary_bg"],
                                border_radius=RADIUS_SM,
                                border=b_all(1, PALETTE["primary_soft"]),
                                expand=True
                            ),
                            ft.IconButton(
                                icon=ft.Icons.ADD_SHOPPING_CART_ROUNDED,
                                icon_color=PALETTE["primary"],
                                tooltip=_t("recipe_card.add_missing_tooltip"),
                                on_click=alisverise_ekle_tikle
                            )
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                    )

                if t["sezon_uyari"]:
                    rozetler_kolonu.append(
                        ft.Container(
                            content=ft.Text(_t("recipe_card.season_warning"), size=10, color=PALETTE["amber"], weight=ft.FontWeight.W_800),
                            padding=7,
                            bgcolor=PALETTE["amber_bg"],
                            border_radius=RADIUS_SM,
                            border=b_all(1, PALETTE["amber"])
                        )
                    )

                baslik_txt = ft.Text(f"🥘 {t_adi}", weight=ft.FontWeight.W_900, size=16, expand=True, color=PALETTE["text"])
                # Porsiyon sayısını her tarif kartında yerel olarak hesapla.
                # Önceki sürümde kisi_sayisi_n döngü içinde sonradan atanıyordu;
                # buton callback'leri oluşturulurken bu değişken tanımsız kalabiliyordu.
                kisi_sayisi_n = sayi_ayikla(t.get("kisi_sayisi", "4 Kişilik"), 4)
                mevcut_kisi = max(1, round(kisi_sayisi_n * current_porsiyon_katsayi))
                porsiyon_bilgi_txt = ft.Text(f"🍽️ {mevcut_kisi} kişilik", size=12, color=PALETTE["text"], weight=ft.FontWeight.W_800)

                def porsiyon_arttir(_, ad=t_adi, base_kisi=kisi_sayisi_n):
                    porsiyon_carpanlari[ad] = round(porsiyon_carpanlari.get(ad, 1.0) + (1.0 / max(1, base_kisi)), 3)
                    page.run_task(yemek_oner, None)

                def porsiyon_azalt(_, ad=t_adi, base_kisi=kisi_sayisi_n):
                    mevcut = porsiyon_carpanlari.get(ad, 1.0)
                    if mevcut > (1.0 / max(1, base_kisi)):
                        porsiyon_carpanlari[ad] = round(mevcut - (1.0 / max(1, base_kisi)), 3)
                        page.run_task(yemek_oner, None)

                duzenlenmis_malzemeler = [f"• {_ing(m)} (x{current_porsiyon_katsayi})" for m in t["tum_malzemeler"]]
                malz_txt = ft.Text(f"{_t('recipe_card.ingredients_label')}: {', '.join(duzenlenmis_malzemeler)}", size=12, color=PALETTE["text"], weight=ft.FontWeight.W_600)

                adim_kutulari = []
                tamamlandi_bildirildi = {"value": False}
                def adim_kontrol(e, ad=t_adi, kutular=adim_kutulari):
                    if all(bool(k.value) for k in kutular) and kutular and not tamamlandi_bildirildi["value"]:
                        tamamlandi_bildirildi["value"] = True
                        tarif_tamamlandi_kaydet(ad)
                for adim in t["hazirlanis"]:
                    cb = ft.Checkbox(fill_color=PALETTE["primary"], on_change=adim_kontrol)
                    adim_kutulari.append(cb)
                tarif_adimlari = [
                    ft.Row([cb, ft.Text(adim, size=12, color=PALETTE["text"], weight=ft.FontWeight.W_600, expand=True)],
                           vertical_alignment=ft.CrossAxisAlignment.START)
                    for cb, adim in zip(adim_kutulari, t["hazirlanis"])
                ]

                mevcut_not = tarif_notlari.get(t_adi, "")
                def not_kaydet(e, ad=t_adi):
                    tarif_notlari[ad] = e.control.value
                    veri_kaydet(notlar_DOSYA, tarif_notlari)

                not_kutusu = ft.TextField(
                    label=_t("recipe_card.note_label"),
                    value=mevcut_not,
                    on_change=not_kaydet,
                    dense=True,
                    border_radius=RADIUS_SM,
                    text_size=11,
                    border_color=PALETTE["border_strong"],
                    focused_border_color=PALETTE["primary"],
                    label_style=ft.TextStyle(color=PALETTE["text_soft"], size=10)
                )

                kart = ft.Container(
                    content=ft.Column([
                        ft.Row([
                            baslik_txt,
                            ft.IconButton(
                                icon=ft.Icons.CALENDAR_MONTH_ROUNDED,
                                icon_color=PALETTE["primary"],
                                tooltip=_t("recipe_card.add_to_menu_tooltip"),
                                on_click=lambda _, name=t_adi: menuye_ekle(name)
                            ),
                            ft.IconButton(
                                icon=fav_icon,
                                icon_color=fav_color,
                                tooltip=_t("recipe_card.favorite_remove_tooltip") if is_fav else _t("recipe_card.favorite_add_tooltip"),
                                on_click=lambda _, name=t_adi: favori_durumu_degistir(name)
                            )
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([
                            ft.Container(content=ft.Text(f"{_t('recipe_card.duration_label')} {t['sure']}", size=11, color=PALETTE["text"], weight=ft.FontWeight.W_800), padding=7, bgcolor=PALETTE["bg_soft"], border_radius=RADIUS_SM, border=b_all(1, PALETTE["border"])),
                            ft.Container(content=ft.Text(_t("recipe_card.servings_label", count=kisi_sayisi_n), size=11, color=PALETTE["text"], weight=ft.FontWeight.W_800), padding=7, bgcolor=PALETTE["bg_soft"], border_radius=RADIUS_SM, border=b_all(1, PALETTE["border"])),
                            ft.Container(content=ft.Text(f"{_t('recipe_card.calories_label')} {int(t['kalori']*current_porsiyon_katsayi)} {_t('recipe_card.calories_unit')}", size=11, color=PALETTE["text"], weight=ft.FontWeight.W_800), padding=7, bgcolor=PALETTE["bg_soft"], border_radius=RADIUS_SM, border=b_all(1, PALETTE["border"])),
                            ft.Container(content=ft.Text(f"{_t('recipe_card.protein_label')} {t['protein']}", size=11, color=PALETTE["text"], weight=ft.FontWeight.W_800), padding=7, bgcolor=PALETTE["bg_soft"], border_radius=RADIUS_SM, border=b_all(1, PALETTE["border"])),
                            ft.Container(content=ft.Text(f"👨‍🍳 {t.get('zorluk', 'Orta')}", size=11, color=z_fg, weight=ft.FontWeight.W_800), padding=7, bgcolor=z_bg, border_radius=RADIUS_SM, border=b_all(1, z_fg)),
                        ], spacing=6, wrap=True),
                        ft.Row([
                            porsiyon_bilgi_txt,
                            ft.Row([
                                ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE_ROUNDED, icon_size=18, icon_color=PALETTE["primary"], on_click=porsiyon_azalt, tooltip=_t("recipe_card.portion_decrease_tooltip")),
                                ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED, icon_size=18, icon_color=PALETTE["primary"], on_click=porsiyon_arttir, tooltip=_t("recipe_card.portion_increase_tooltip"))
                            ], spacing=0)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        malz_txt,
                        ft.Column(rozetler_kolonu, spacing=6),
                        ft.Divider(height=12, color=PALETTE["border"]),
                        ft.ExpansionTile(
                            title=ft.Text(_t("recipe_card.details_title"), size=13, color=PALETTE["text"], weight=ft.FontWeight.W_900),
                            controls=[
                                ft.Container(
                                    content=ft.Column([
                                        not_kutusu,
                                        ft.Container(height=5),
                                        ft.Text(_t("recipe_card.steps_title"), size=11, weight=ft.FontWeight.W_900, color=PALETTE["text_soft"]),
                                        ft.Column(tarif_adimlari, spacing=8)
                                    ], spacing=6),
                                    padding=m_symmetric(horizontal=4, vertical=8)
                                )
                            ]
                        )
                    ], spacing=8),
                    padding=16,
                    bgcolor=PALETTE["surface"],
                    border=b_all(1.4, PALETTE["sage"] if t["tam_mı"] else PALETTE["border"]),
                    border_radius=RADIUS_MD,
                    shadow=soft_shadow(10, 0, 0.08),
                    opacity=0.0,
                    offset=ft.Offset(0, 0.15),
                    scale=0.96,
                    animate=ft.Animation(380 + (min(i, 5) * 55), ft.AnimationCurve.EASE_OUT),
                    animate_opacity=ft.Animation(380 + (min(i, 5) * 55), ft.AnimationCurve.EASE_OUT),
                    animate_scale=ft.Animation(380 + (min(i, 5) * 55), ft.AnimationCurve.EASE_OUT_BACK),
                )

                yeni_kartlar.append(kart)
                oneri_listesi.controls.append(kart)
        else:
            oneri_listesi.controls.append(
                ft.Container(
                    content=ft.Text(_t("fridge.empty_state"), color=PALETTE["text_soft"], italic=True, weight=ft.FontWeight.W_700),
                    padding=15,
                    alignment=ft.alignment.Alignment(0, 0)
                )
            )

        page.update()

        if eslesenler:
            await asyncio.sleep(0.03)
            for k in yeni_kartlar:
                k.opacity = 1.0
                k.offset = ft.Offset(0, 0)
            page.update()

    kategori_elemanlari = ft.Column(spacing=8)

    for kategori in kategori_listesi:
        malzeme_listesi = kategori.get("items", [])
        malzeme_kartlari = ft.Column(spacing=6)

        for m in malzeme_listesi:
            cb = ft.Checkbox(visible=False, value=False, data=m, on_change=malzeme_degisti)

            kutu_ikon = ft.Icon(ft.Icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED, color=PALETTE["text_faint"], size=20)
            kutu_container = ft.Container(
                content=kutu_ikon,
                width=26, height=26,
                alignment=ft.alignment.Alignment(0, 0),
                bgcolor=ft.Colors.TRANSPARENT,
                border_radius=8,
                border=b_all(1.6, PALETTE["border_strong"]),
                animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT)
            )

            def kart_tikla(e, c=cb, ikon=kutu_ikon, kutu=kutu_container):
                c.value = not c.value
                malzeme_degisti(type('obj', (object,), {'control': c})())
                if c.value:
                    ikon.name = ft.Icons.CHECK_ROUNDED
                    ikon.color = PALETTE["white"]
                    kutu.bgcolor = PALETTE["primary"]
                    kutu.border = b_all(1.6, PALETTE["primary"])
                else:
                    ikon.name = ft.Icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED
                    ikon.color = PALETTE["text_faint"]
                    kutu.bgcolor = ft.Colors.TRANSPARENT
                    kutu.border = b_all(1.6, PALETTE["border_strong"])
                page.update()

            malz_kart = ft.Container(
                content=ft.Row([
                    ft.Text(_ing(m), size=13, weight=ft.FontWeight.W_700, color=PALETTE["text"], expand=True),
                    kutu_container,
                    cb
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=m_symmetric(horizontal=12, vertical=8),
                bgcolor=PALETTE["surface"],
                border_radius=RADIUS_SM,
                border=b_all(1.2, PALETTE["border"]),
            )
            yapilandir_etkilesim(
                malz_kart, on_click=kart_tikla, hover_scale=1.012, basma_scale=0.985,
                temel_golge=soft_shadow(6, 0, 0.04), hover_golge=soft_shadow(10, 0, 0.09, PALETTE["primary"])
            )
            malzeme_kartlari.controls.append(malz_kart)

        kat_exp = ft.ExpansionTile(
            title=ft.Text(category_label(aktif_dil, kategori), size=14, weight=ft.FontWeight.W_800, color=PALETTE["text"]),
            controls=[
                ft.Container(content=malzeme_kartlari, padding=m_symmetric(horizontal=8, vertical=4))
            ]
        )
        kategori_elemanlari.controls.append(kat_exp)

    buzdolabi_alani = ft.Container(
        content=ft.Column([
            ft.Text(_t("fridge.fridge_contents_title"), size=15, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
            kategori_elemanlari
        ], spacing=10),
        padding=14,
        bgcolor=PALETTE["surface"],
        border_radius=RADIUS_MD,
        border=b_all(1.4, PALETTE["border"])
    )

    kategori_secim_dropdown = ft.Dropdown(
        label=_t("fridge.category_filter_label"),
        value="all",
        options=[
            ft.dropdown.Option(key="all", text=_t("fridge.category_filter_all")),
            ft.dropdown.Option(key="meals", text=_t("fridge.category_filter_meals")),
            ft.dropdown.Option(key="desserts", text=_t("fridge.category_filter_desserts")),
        ],
        border_color=PALETTE["border_strong"],
        border_width=1.4,
        text_style=ft.TextStyle(color=PALETTE["text"], size=13, weight=ft.FontWeight.W_700),
        label_style=ft.TextStyle(color=PALETTE["text_soft"], size=12, weight=ft.FontWeight.W_800),
        bgcolor=PALETTE["surface"],
        border_radius=RADIUS_SM,
    )
    kategori_secim_dropdown.on_change = kategori_filtre_degisti

    kalori_dropdown = ft.Dropdown(
        label=_t("fridge.calorie_filter_label"),
        value="all",
        options=[
            ft.dropdown.Option(key="all", text=_t("fridge.calorie_filter_all")),
            ft.dropdown.Option(key="low_cal", text=_t("fridge.calorie_filter_low")),
            ft.dropdown.Option(key="high_protein", text=_t("fridge.calorie_filter_high_protein")),
        ],
        border_color=PALETTE["border_strong"],
        border_width=1.4,
        text_style=ft.TextStyle(color=PALETTE["text"], size=13, weight=ft.FontWeight.W_700),
        label_style=ft.TextStyle(color=PALETTE["text_soft"], size=12, weight=ft.FontWeight.W_800),
        bgcolor=PALETTE["surface"],
        border_radius=RADIUS_SM,
    )
    kalori_dropdown.on_change = kalori_filtre_degisti

    ogun_secimi_baslik = ft.Text(_t("fridge.meal_time_label"), size=15, weight=ft.FontWeight.W_900, color=PALETTE["text"])
    oneriler_baslik = ft.Text(_t("fridge.suggestions_title"), size=15, weight=ft.FontWeight.W_900, color=PALETTE["text"])
    ogun_konteyner = ft.Container(content=ogun_secimi, padding=8, bgcolor=PALETTE["surface"], border_radius=RADIUS_SM, border=b_all(1.4, PALETTE["border"]))

    async def ana_menuye_don(e):
        ana_sayfa_icerigi.opacity = 0.0
        ana_sayfa_icerigi.offset = ft.Offset(0.5, 0)
        asistan_ekrani.opacity = 0.0
        asistan_ekrani.offset = ft.Offset(0.5, 0)
        page.update()
        await asyncio.sleep(0.15)
        ana_sayfa_icerigi.visible = False
        asistan_ekrani.visible = False

        ana_menu.visible = True
        ana_menu.offset = ft.Offset(-0.3, 0)
        ana_menu.opacity = 0.0
        page.update()
        await asyncio.sleep(0.05)
        ana_menu.offset = ft.Offset(0, 0)
        ana_menu.opacity = 1.0
        page.update()

    ana_sayfa_icerigi = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK_ROUNDED,
                            icon_color=PALETTE["primary_dark"],
                            tooltip=_t("fridge.back_tooltip"),
                            on_click=lambda e: page.run_task(ana_menuye_don, e),
                        ),
                        ft.Text(_t("home.card_fridge_title"), size=15, weight=ft.FontWeight.W_900, color=PALETTE["text"], expand=True),
                    ], alignment=ft.MainAxisAlignment.START),
                    header_kart,
                    ft.Divider(height=5, color=PALETTE["border"], thickness=1.4),
                    ft.Row([
                        ft.Switch(label=_t("fridge.favorites_switch"), active_color=PALETTE["primary"],
                                  label_text_style=ft.TextStyle(color=PALETTE["text"], weight=ft.FontWeight.W_700, size=12),
                                  on_change=favori_filtre_degisti, value=False),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Container(
                        content=ft.Row([
                            pill_button(_t("fridge.lucky_button"), icon=ft.Icons.CASINO_ROUNDED, on_click=rastgele_tarif_getir, dolgu=False),
                        ], alignment=ft.MainAxisAlignment.START),
                        padding=m_symmetric(vertical=2)
                    ),
                    ft.Row([
                        ft.Switch(
                            label=_t("fridge.fastfood_switch"),
                            label_text_style=ft.TextStyle(color=PALETTE["text"], weight=ft.FontWeight.W_700, size=12),
                            on_change=fast_food_modu_degisti,
                            value=False,
                            active_color=PALETTE["primary"]
                        ),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                    kategori_secim_dropdown,
                    kalori_dropdown,
                    ogun_secimi_baslik,
                    ogun_konteyner,
                    ft.Container(height=5),
                    buzdolabi_alani,
                    ft.Container(
                        content=pill_button(_t("fridge.get_suggestions_button"), icon=ft.Icons.RESTAURANT_MENU_ROUNDED,
                                             on_click=lambda e: page.run_task(yemek_oner, e), expand=True),
                        margin=m_symmetric(vertical=10)
                    ),
                    oneriler_baslik,
                    oneri_listesi
                ], spacing=10),
                padding=16
            )
        ]),
        expand=True,
        visible=False,
        opacity=0.0,
        offset=ft.Offset(0.5, 0),
        animate=ft.Animation(350, ft.AnimationCurve.DECELERATE),
        animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT)
    )

    # ==========================================
    # 👨‍🍳 YEMEK YARDIMCISI (GERÇEK GROQ AI)
    # ==========================================
    chat_listesi = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO)

    # 🤖 Kalıcı AI sohbet geçmişi: ayrı konuşmalar halinde saklanır.
    kayitli_sohbetler = veri_yukle(CHAT_DOSYA)
    if not isinstance(kayitli_sohbetler, list):
        kayitli_sohbetler = []
    sohbetler = [x for x in kayitli_sohbetler if isinstance(x, dict) and isinstance(x.get("messages"), list)]
    aktif_sohbet_id = None
    aktif_sohbet = None

    def sohbetleri_kaydet():
        veri_kaydet(CHAT_DOSYA, sohbetler[-50:])

    def yeni_sohbet_verisi():
        import uuid
        return {"id": uuid.uuid4().hex, "title": "Yeni sohbet", "created": time.time(), "updated": time.time(), "messages": []}

    def aktif_sohbeti_sec(sohbet):
        nonlocal aktif_sohbet_id, aktif_sohbet
        aktif_sohbet = sohbet
        aktif_sohbet_id = sohbet.get("id")

    if sohbetler:
        aktif_sohbeti_sec(sohbetler[-1])
    else:
        aktif_sohbet = yeni_sohbet_verisi()
        aktif_sohbet_id = aktif_sohbet["id"]
        sohbetler.append(aktif_sohbet)
        sohbetleri_kaydet()

    def ai_gecmisi_al():
        return aktif_sohbet.get("messages", []) if aktif_sohbet else []

    def sohbet_basligi_guncelle(metin):
        if not aktif_sohbet:
            return
        if aktif_sohbet.get("title") in (None, "", "Yeni sohbet"):
            temiz = re.sub(r"\s+", " ", str(metin).strip())
            aktif_sohbet["title"] = (temiz[:38] + "…") if len(temiz) > 38 else (temiz or "Yeni sohbet")
        aktif_sohbet["updated"] = time.time()

    def sohbet_mesaji_ekle(role, content):
        if not aktif_sohbet:
            return
        aktif_sohbet.setdefault("messages", []).append({"role": role, "content": str(content)})
        # Token güvenliği: sonsuz geçmişi API'ye göndermiyoruz; diskte ise tamamı kalıyor.
        aktif_sohbet["messages"] = aktif_sohbet["messages"][-40:]
        aktif_sohbet["updated"] = time.time()
        sohbetleri_kaydet()

    # 🛡️ Yerel AI kötüye kullanım koruması: sunucu gerektirmez.
    AI_GUNLUK_LIMIT = 10
    AI_MIN_ARALIK = 10
    AI_GECICI_ENGEL = 60
    uygunsuz_kelimeler = {
        "amk", "aq", "siktir", "sikik", "orospu", "piç", "pic", "yarrak",
        "salak", "aptal", "gerizekali", "gerizekalı", "şerefsiz", "serefsiz",
        "haysiyetsiz", "ibne", "pezevenk"
    }
    _ai_kayit = kayitli_ayar.get("ai_kullanim", {}) if isinstance(kayitli_ayar, dict) else {}
    if not isinstance(_ai_kayit, dict):
        _ai_kayit = {}
    ai_kullanim = {
        "gun": str(_ai_kayit.get("gun", datetime.now().date().isoformat())),
        "adet": int(_ai_kayit.get("adet", 0) or 0),
        "son": float(_ai_kayit.get("son", 0) or 0),
        "engel_son": 0.0,
        "seri_spam": 0,
    }

    def ai_koruma_kontrol(metin):
        simdi = time.time()
        bugun = datetime.now().date().isoformat()
        if ai_kullanim["gun"] != bugun:
            ai_kullanim.update({"gun": bugun, "adet": 0, "son": 0.0, "engel_son": 0.0, "seri_spam": 0})
        if simdi < ai_kullanim["engel_son"]:
            kalan = max(1, int(ai_kullanim["engel_son"] - simdi))
            return False, f"🛡️ Çok hızlı kullanım algılandı. Lütfen {kalan} saniye bekle."
        if ai_kullanim["adet"] >= AI_GUNLUK_LIMIT:
            return False, f"🛡️ Günlük AI kullanım sınırına ulaştın ({AI_GUNLUK_LIMIT} soru). Yarın tekrar deneyebilirsin."
        if simdi - ai_kullanim["son"] < AI_MIN_ARALIK:
            ai_kullanim["seri_spam"] += 1
            if ai_kullanim["seri_spam"] >= 3:
                ai_kullanim["engel_son"] = simdi + AI_GECICI_ENGEL
                ai_kullanim["seri_spam"] = 0
                return False, "🛡️ Çok sık istek gönderildi. AI kullanımı 60 saniyeliğine durduruldu."
            kalan = max(1, int(AI_MIN_ARALIK - (simdi - ai_kullanim["son"])))
            return False, f"⏳ Lütfen {kalan} saniye bekleyip tekrar dene."
        temiz = re.sub(r"[^a-zA-ZçğıöşüÇĞİÖŞÜ0-9\s]", " ", metin.lower())
        kelimeler = set(temiz.split())
        if kelimeler.intersection(uygunsuz_kelimeler):
            return False, "⚠️ Bu ifade uygun değil. Lütfen daha saygılı bir şekilde tekrar yaz."
        if len(metin) > 2000:
            return False, "⚠️ Mesaj çok uzun. Lütfen 2.000 karakterden kısa bir soru yaz."
        ai_kullanim["adet"] += 1
        ai_kullanim["son"] = simdi
        ai_kullanim["seri_spam"] = 0
        ayarlar = veri_yukle(ayar_DOSYA)
        if not isinstance(ayarlar, dict):
            ayarlar = {}
        ayarlar["ai_kullanim"] = {"gun": ai_kullanim["gun"], "adet": ai_kullanim["adet"], "son": ai_kullanim["son"]}
        veri_kaydet(ayar_DOSYA, ayarlar)
        return True, ""

    def tarif_katalogu_olustur():
        # Groq TPM sınırı nedeniyle tüm tarif arşivini API isteğine göndermiyoruz.
        return ""

    AI_TARIF_KATALOGU = ""

    def ai_sistem_mesaji():
        dil_adi = "Türkçe" if aktif_dil == "tr" else "English"
        return (
            "Sen Nöbetçi Ev uygulamasının yemek asistanısın. "
            "Kullanıcıya kısa, doğal ve faydalı cevap ver. "
            f"Dil: {dil_adi}."
        )

    def groq_client_al():
        if Groq is None:
            raise RuntimeError(
                "Groq kütüphanesi yüklü değil. Terminalde 'pip install groq' çalıştır."
            )

        if not GROQ_API_KEY or GROQ_API_KEY.strip() == "your api key":
            raise RuntimeError(
                "GROQ_API_KEY ortam değişkeni ayarlanmamış. CMD'de setx GROQ_API_KEY \"ANAHTARIN\" komutunu çalıştır."
            )

        return Groq(api_key=GROQ_API_KEY.strip())

    def ai_cevabi_senkron_uret(soru, gecmis=None):
        """Aktif sohbetin son bölümünü bağlam olarak Groq'a gönderir."""
        client = groq_client_al()

        soru = str(soru or "").strip()
        if not soru:
            raise RuntimeError("Boş soru gönderilemez.")

        system_prompt = (
            "Sen Nöbetçi Ev uygulamasının yemek asistanısın. "
            "Kullanıcının sorusunu doğrudan ve faydalı şekilde cevapla. "
            "Soru açıksa tekrar 'nasıl yardımcı olabilirim' diye sorma. "
            "Merhaba/naber gibi sohbet mesajlarına doğal cevap ver. "
            "Tarif istenirse malzemeleri ve kısa yapılışını ver. "
            "Beslenme önerisi istenirse genel ve temkinli öneriler ver. "
            "Kullanıcı ne istiyorsa onu yap; soruyu görmezden gelme. "
            "Önemli güvenlik, sağlık, alerji, gıda güvenliği, saklama, bozulma, "
            "hamilelik, çocuk beslenmesi veya özel diyet konularında kesin konuşma; "
            "belirsiz veya kişiye özel durumlarda güvenilir bir uzmana ve güncel kaynağa "
            "başvurulmasını belirt. "
            "Asla 'ben kesinlikle hata yapmam' gibi bir güvence verme. "
            f"Dil: {'Türkçe' if aktif_dil == 'tr' else 'English'}."
        )

        messages = [{"role": "system", "content": system_prompt}]
        kaynak = list(gecmis or [])[-8:]
        for item in kaynak:
            if item.get("role") in ("user", "assistant") and item.get("content"):
                messages.append({"role": item["role"], "content": str(item["content"])[:1600]})
        if not kaynak or kaynak[-1].get("content") != soru:
            messages.append({"role": "user", "content": soru[:2000]})

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_completion_tokens=700,
        )

        if not completion.choices:
            raise RuntimeError("Groq hiç cevap seçeneği döndürmedi.")

        msg = completion.choices[0].message
        cevap = getattr(msg, "content", None)
        if not cevap or not str(cevap).strip():
            finish_reason = getattr(completion.choices[0], "finish_reason", None)
            raise RuntimeError(
                f"Groq metin cevabı döndürmedi (finish_reason={finish_reason})."
            )

        return str(cevap).strip()

    def mesaj_balonu_olustur(metin, gonderen_kullanici_mi=False):
        renk_bg = PALETTE["primary_bg"] if gonderen_kullanici_mi else PALETTE["surface"]
        renk_border = PALETTE["primary_soft"] if gonderen_kullanici_mi else PALETTE["border"]
        hizalama = ft.MainAxisAlignment.END if gonderen_kullanici_mi else ft.MainAxisAlignment.START

        return ft.Row([
            ft.Container(
                content=ft.Text(
                    metin,
                    size=12.5,
                    color=PALETTE["text"],
                    weight=ft.FontWeight.W_600,
                    selectable=True,
                ),
                padding=m_symmetric(horizontal=14, vertical=10),
                bgcolor=renk_bg,
                border_radius=RADIUS_MD,
                border=b_all(1.2, renk_border),
                shadow=soft_shadow(6, 0, 0.05),
                width=300,
            )
        ], alignment=hizalama)

    # Başlangıç karşılama mesajı. Kullanıcının adı ilk açılışta alındıysa
    # asistan sohbetinin ilk mesajında doğal şekilde kullanılır.
    if kullanici_adi and aktif_dil == "tr":
        asistan_hosgeldin = (
            f"Merhaba {kullanici_adi}! Ben senin dijital mutfak şefinim. "
            "Tarif soruları, püf noktaları veya malzeme alternatifleri hakkında "
            "bana dilediğini sorabilirsin! 🍳✨"
        )
    elif kullanici_adi:
        asistan_hosgeldin = (
            f"Hello {kullanici_adi}! I'm your digital kitchen chef. "
            "Ask me anything about recipes, cooking tips, or ingredient alternatives! 🍳✨"
        )
    else:
        asistan_hosgeldin = _t("assistant.welcome_message")

    chat_listesi.controls.append(
        mesaj_balonu_olustur(asistan_hosgeldin, False)
    )

    # Kullanıcının sık sorduğu sorular için kişisel hızlı kısayollar.
    kayitli_kisayollar = kayitli_ayar.get("ai_hizli_sorular", []) if isinstance(kayitli_ayar, dict) else []
    if not isinstance(kayitli_kisayollar, list):
        kayitli_kisayollar = []
    hizli_soru_kisayollari = [str(x).strip()[:120] for x in kayitli_kisayollar if str(x).strip()][:8]

    def hizli_sorulari_kaydet():
        ayarlar = veri_yukle(ayar_DOSYA)
        if not isinstance(ayarlar, dict):
            ayarlar = {}
        ayarlar["dil"] = aktif_dil
        ayarlar["kullanici_adi"] = kullanici_adi
        ayarlar["ai_hizli_sorular"] = hizli_soru_kisayollari[:8]
        veri_kaydet(ayar_DOSYA, ayarlar)

    def hizli_soru_butonlarini_yenile():
        hizli_sorular.controls.clear()
        for soru in hizli_soru_kisayollari:
            soru_kutu = ft.Container(
                content=ft.Row([
                    ft.Text(
                        soru, size=11.5, weight=ft.FontWeight.W_700,
                        color=PALETTE["primary_dark"], expand=True, max_lines=2
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED, icon_size=15,
                        icon_color=PALETTE["text_faint"],
                        tooltip="Hızlı soruyu kaldır",
                        on_click=lambda e, q=soru: hızlı_soru_sil(e, q),
                    ),
                ], spacing=3),
                padding=m_symmetric(horizontal=10, vertical=2),
                bgcolor=PALETTE["primary_bg"],
                border=b_all(1, PALETTE["border"]),
                border_radius=RADIUS_MD,
                on_click=lambda e, q=soru: hızlı_soru_tiklandi(e, q),
            )
            hizli_sorular.controls.append(soru_kutu)
        hizli_sorular.controls.append(
            ft.OutlinedButton(
                "＋ Hızlı soru ekle",
                icon=ft.Icons.ADD_ROUNDED,
                on_click=lambda e: hızlı_soru_ekle_dialogu_ac(),
                style=ft.ButtonStyle(color=PALETTE["primary_dark"])
            )
        )
        page.update()

    def hızlı_soru_sil(_, soru):
        if soru in hizli_soru_kisayollari:
            hizli_soru_kisayollari.remove(soru)
            hizli_soru_kaydet()
            hizli_soru_butonlarini_yenile()

    async def hizli_soru_kaydet(_=None):
        soru = str(yeni_hizli_soru.value or "").strip()[:120]
        if not soru:
            yeni_hizli_soru.error_text = "Bir soru yaz."
            page.update()
            return
        if soru in hizli_soru_kisayollari:
            yeni_hizli_soru.error_text = "Bu soru zaten ekli."
            page.update()
            return
        if len(hizli_soru_kisayollari) >= 8:
            yeni_hizli_soru.error_text = "En fazla 8 hızlı soru ekleyebilirsin."
            page.update()
            return
        hizli_soru_kisayollari.append(soru)
        hizli_soru_kaydet()
        hizli_soru_dialogu.open = False
        hizli_soru_butonlarini_yenile()

    yeni_hizli_soru = ft.TextField(
        label="Hızlı soru",
        hint_text="Sık sorduğun bir soruyu yaz",
        autofocus=True,
        max_length=120,
        border_color=PALETTE["border_strong"],
        focused_border_color=PALETTE["primary"],
    )
    hizli_soru_dialogu = ft.AlertDialog(
        modal=True,
        title=ft.Text("⚡ Hızlı soru ekle", size=18, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
        content=ft.Column([
            ft.Text("Sık sorduğun soruyu ekle. Üstteki butona dokununca soru otomatik olarak yapay zekâya gönderilir.",
                    size=11.5, color=PALETTE["text_soft"], weight=ft.FontWeight.W_600),
            yeni_hizli_soru,
        ], tight=True, spacing=10),
        actions=[
            ft.TextButton("Vazgeç", on_click=lambda e: setattr(hizli_soru_dialogu, "open", False)),
            ft.ElevatedButton(
                "Ekle", on_click=hizli_soru_kaydet,
                style=ft.ButtonStyle(bgcolor=PALETTE["primary"], color=PALETTE["white"],
                                     shape=ft.RoundedRectangleBorder(radius=RADIUS_SM))
            )
        ],
        bgcolor=PALETTE["surface"],
        shape=ft.RoundedRectangleBorder(radius=RADIUS_LG),
    )

    def hızlı_soru_ekle_dialogu_ac():
        yeni_hizli_soru.value = ""
        yeni_hizli_soru.error_text = None
        page.overlay.append(hizli_soru_dialogu) if hizli_soru_dialogu not in page.overlay else None
        hizli_soru_dialogu.open = True
        page.update()

    # AI güvenlik uyarısı: kullanıcı yapay zekâ cevabını kesin kaynak olarak görmesin.
    ai_uyari_metni = (
        "⚠️ Yapay zekâ hata yapabilir. Özellikle sağlık, alerji ve gıda güvenliği "
        "gibi önemli konulardaki bilgileri güvenilir kaynaklardan kontrol et."
        if aktif_dil == "tr" else
        "⚠️ AI can make mistakes. For health, allergies and food safety, verify "
        "important information with reliable sources."
    )
    chat_listesi.controls.append(
        ft.Container(
            content=ft.Text(
                ai_uyari_metni,
                size=10.5,
                color=PALETTE["text_soft"],
                weight=ft.FontWeight.W_600,
            ),
            padding=m_symmetric(horizontal=12, vertical=8),
            bgcolor=PALETTE["surface"],
            border=b_all(1, PALETTE["border"]),
            border_radius=RADIUS_MD,
        )
    )

    chat_input = ft.TextField(
        hint_text=_t("assistant.input_placeholder"),
        expand=True,
        dense=True,
        border_radius=RADIUS_MD,
        border_color=PALETTE["border_strong"],
        focused_border_color=PALETTE["primary"],
        text_size=12,
        content_padding=m_symmetric(horizontal=14, vertical=10),
        multiline=False,
        on_submit=lambda e: page.run_task(mesaj_gonder, None),
    )

    async def mesaj_gonder(soru_metni=None):
        metin = soru_metni or chat_input.value

        if not metin or not metin.strip():
            return

        metin = metin.strip()

        izin, koruma_mesaji = ai_koruma_kontrol(metin)
        if not izin:
            if not soru_metni:
                chat_input.value = ""
            chat_listesi.controls.append(mesaj_balonu_olustur(koruma_mesaji, False))
            page.update()
            return

        if not soru_metni:
            chat_input.value = ""

        # Kullanıcı mesajını göster.
        chat_listesi.controls.append(mesaj_balonu_olustur(metin, True))

        # AI düşünürken animasyonlu "yazıyor..." balonu.
        dusunuyor_metin = ft.Text(
            "👨‍🍳 " + ("Düşünüyorum" if aktif_dil == "tr" else "Thinking"),
            size=12.5, color=PALETTE["text"], weight=ft.FontWeight.W_600,
        )
        dusunuyor_mesaji = ft.Row([
            ft.Container(
                content=dusunuyor_metin,
                padding=m_symmetric(horizontal=14, vertical=10),
                bgcolor=PALETTE["surface"],
                border_radius=RADIUS_MD,
                border=b_all(1.2, PALETTE["border"]),
                shadow=soft_shadow(6, 0, 0.05),
                width=180,
            )
        ], alignment=ft.MainAxisAlignment.START)
        chat_listesi.controls.append(dusunuyor_mesaji)
        page.update()

        async def ai_yaziyor_animasyonu():
            taban = "👨‍🍳 " + ("Düşünüyorum" if aktif_dil == "tr" else "Thinking")
            noktalar = ["", ".", "..", "..."]
            idx = 0
            try:
                while True:
                    dusunuyor_metin.value = taban + noktalar[idx % len(noktalar)]
                    dusunuyor_metin.opacity = 0.72 if idx % 2 else 1.0
                    idx += 1
                    page.update()
                    await asyncio.sleep(0.38)
            except asyncio.CancelledError:
                return

        yaziyor_task = asyncio.create_task(ai_yaziyor_animasyonu())

        # Kalıcı sohbet geçmişine ekle.
        sohbet_basligi_guncelle(metin)
        aktif_sohbet_baslik.value = aktif_sohbet.get("title", "Yeni sohbet") if aktif_sohbet else "Yeni sohbet"
        sohbet_mesaji_ekle("user", metin)
        gecmis_kopya = list(ai_gecmisi_al())

        try:
            yanit = await asyncio.to_thread(ai_cevabi_senkron_uret, metin, gecmis_kopya)
            sohbet_mesaji_ekle("assistant", yanit)

            # Geçici "düşünüyorum" balonunu gerçek cevapla değiştir.
            if dusunuyor_mesaji in chat_listesi.controls:
                index = chat_listesi.controls.index(dusunuyor_mesaji)
                chat_listesi.controls[index] = mesaj_balonu_olustur(yanit, False)
            else:
                chat_listesi.controls.append(mesaj_balonu_olustur(yanit, False))

        except Exception as err:
            # Hata durumunda kullanıcıya anlaşılır mesaj göster.
            print(f"[GROQ HATASI] {type(err).__name__}: {err}")

            hata_metni = (
                "AI bağlantısında bir sorun oluştu. "
                "API anahtarını ve internet bağlantını kontrol et."
                if aktif_dil == "tr"
                else
                "There was a problem connecting to the AI. "
                "Please check your API key and internet connection."
            )

            if dusunuyor_mesaji in chat_listesi.controls:
                index = chat_listesi.controls.index(dusunuyor_mesaji)
                chat_listesi.controls[index] = mesaj_balonu_olustur(hata_metni, False)
            else:
                chat_listesi.controls.append(mesaj_balonu_olustur(hata_metni, False))

            # Başarısız isteği geçmişten çıkar ki sonraki isteklerde tekrar
            # bozuk bir bağlam olarak gönderilmesin.
            if aktif_sohbet and aktif_sohbet.get("messages") and aktif_sohbet["messages"][-1].get("role") == "user":
                aktif_sohbet["messages"].pop()
                sohbetleri_kaydet()

        if not yaziyor_task.done():
            yaziyor_task.cancel()
            try:
                await yaziyor_task
            except asyncio.CancelledError:
                pass

        page.update()

    def hızlı_soru_tiklandi(e, q_text):
        page.run_task(mesaj_gonder, q_text)

    hizli_sorular = ft.Row([], scroll=ft.ScrollMode.AUTO, spacing=8)
    hizli_soru_butonlarini_yenile()

    aktif_sohbet_baslik = ft.Text("Yeni sohbet", size=10.5, color=PALETTE["text_soft"], weight=ft.FontWeight.W_600)

    def sohbet_ekranini_yukle():
        chat_listesi.controls.clear()
        if not aktif_sohbet or not aktif_sohbet.get("messages"):
            chat_listesi.controls.append(mesaj_balonu_olustur(asistan_hosgeldin, False))
        else:
            for m in aktif_sohbet["messages"]:
                chat_listesi.controls.append(mesaj_balonu_olustur(m.get("content", ""), m.get("role") == "user"))
        aktif_sohbet_baslik.value = aktif_sohbet.get("title", "Yeni sohbet") if aktif_sohbet else "Yeni sohbet"
        page.update()

    def yeni_sohbet_baslat():
        nonlocal aktif_sohbet_id, aktif_sohbet
        aktif_sohbet = yeni_sohbet_verisi()
        aktif_sohbet_id = aktif_sohbet["id"]
        sohbetler.append(aktif_sohbet)
        sohbetleri_kaydet()
        sohbet_ekranini_yukle()

    def sohbet_sil(s):
        nonlocal aktif_sohbet_id, aktif_sohbet
        if s in sohbetler:
            sohbetler.remove(s)
        if not sohbetler:
            aktif_sohbet = yeni_sohbet_verisi()
            aktif_sohbet_id = aktif_sohbet["id"]
            sohbetler.append(aktif_sohbet)
        elif aktif_sohbet is s:
            aktif_sohbeti_sec(sohbetler[-1])
        sohbetleri_kaydet()
        sohbet_ekranini_yukle()

    def sohbet_gecmisi_ac():
        liste = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO)
        dlg = ft.AlertDialog(modal=True, title=ft.Text("💬 Sohbet geçmişi", size=18, weight=ft.FontWeight.W_900, color=PALETTE["text"]), bgcolor=PALETTE["surface"], shape=ft.RoundedRectangleBorder(radius=RADIUS_LG))
        def yenile():
            liste.controls.clear()
            sirali = sorted(sohbetler, key=lambda x: x.get("updated", 0), reverse=True)
            for s in sirali:
                baslik = s.get("title", "Yeni sohbet") or "Yeni sohbet"
                liste.controls.append(ft.Container(content=ft.Row([ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED, size=18, color=PALETTE["primary_dark"]), ft.Text(baslik, size=12, weight=ft.FontWeight.W_700, color=PALETTE["text"], expand=True, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS), ft.IconButton(icon=ft.Icons.DELETE_OUTLINE_ROUNDED, icon_size=17, icon_color=PALETTE["text_faint"], on_click=lambda e, x=s: (sohbet_sil(x), dlg.open and yenile(), page.update()))], spacing=8), padding=9, bgcolor=PALETTE["primary_bg"] if s is aktif_sohbet else PALETTE["surface_alt"], border=b_all(1, PALETTE["border"]), border_radius=RADIUS_SM, on_click=lambda e, x=s: (aktif_sohbeti_sec(x), sohbet_ekranini_yukle(), setattr(dlg, "open", False), page.update())))
            if not liste.controls:
                liste.controls.append(ft.Text("Henüz sohbet yok.", size=11.5, color=PALETTE["text_soft"]))
        yenile()
        dlg.content = ft.Container(content=liste, width=340, height=390)
        dlg.actions = [ft.TextButton("+ Yeni sohbet", on_click=lambda e: (yeni_sohbet_baslat(), setattr(dlg, "open", False), page.update())), ft.TextButton("Kapat", on_click=lambda e: (setattr(dlg, "open", False), page.update()))]
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    asistan_ekrani = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK_ROUNDED, icon_color=PALETTE["primary_dark"], tooltip=_t("assistant.back_tooltip"), on_click=lambda e: page.run_task(ana_menuye_don, e)),
                ft.Column([
                    ft.Text(_t("assistant.title"), size=16, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                    aktif_sohbet_baslik
                ], spacing=1, expand=True),
                ft.IconButton(icon=ft.Icons.HISTORY_ROUNDED, icon_color=PALETTE["primary_dark"], tooltip="Sohbet geçmişi", on_click=lambda e: sohbet_gecmisi_ac()),
                ft.IconButton(icon=ft.Icons.ADD_COMMENT_ROUNDED, icon_color=PALETTE["primary_dark"], tooltip="Yeni sohbet", on_click=lambda e: yeni_sohbet_baslat()),
            ]),
            ft.Divider(height=10, color=PALETTE["border"]),
            hizli_sorular,
            ft.Container(
                content=chat_listesi,
                expand=True,
                padding=m_symmetric(vertical=6)
            ),
            ft.Row([
                chat_input,
                ft.IconButton(
                    icon=ft.Icons.SEND_ROUNDED,
                    icon_color=PALETTE["white"],
                    bgcolor=PALETTE["primary"],
                    on_click=lambda e: page.run_task(mesaj_gonder, None)
                )
            ], spacing=8)
        ], spacing=10),
        padding=16,
        expand=True,
        visible=False,
        opacity=0.0,
        offset=ft.Offset(0.5, 0),
        animate=ft.Animation(350, ft.AnimationCurve.DECELERATE),
        animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT)
    )

    # ♻️ Her tür yiyecek için akıllı kurtarıcı
    # Kullanıcı aynı ürünü farklı durumda (ör. çiğ + pişmiş tavuk) ayrı ayrı tanımlayabilir.
    KURTARICI_DURUMLARI = [
        ("Pişmiş / hazır", "🟢"),
        ("Çiğ", "🔴"),
        ("Dondurulmuş", "❄️"),
        ("Çözülmüş", "💧"),
        ("Açılmış", "📦"),
        ("Kapalı paket", "📦"),
        ("Konserve / kavanoz", "🥫"),
        ("Kurutulmuş", "🌾"),
        ("Artan yemek", "♻️"),
        ("Emin değilim", "❓"),
    ]

    kurtarici_urunler = []
    kurtarici_liste = ft.Column(spacing=7, scroll=ft.ScrollMode.AUTO)
    kurtarici_sonuc = ft.Column(spacing=7, scroll=ft.ScrollMode.AUTO)

    def kurtarici_durum_dropdown():
        return ft.Dropdown(
            value="Emin değilim",
            options=[ft.dropdown.Option(ad) for ad, _ in KURTARICI_DURUMLARI],
            dense=True,
            text_size=11,
            width=145,
            border_color=PALETTE["border_strong"],
            focused_border_color=PALETTE["primary"],
        )

    def kurtarici_satir_ekle(_=None, isim=""):
        ad = ft.TextField(
            value=isim,
            hint_text="Örn. tavuk, pilav, süt",
            dense=True,
            text_size=12,
            expand=True,
            border_color=PALETTE["border_strong"],
            focused_border_color=PALETTE["primary"],
        )
        durum = kurtarici_durum_dropdown()
        miktar = ft.TextField(
            hint_text="Miktar (ops.)",
            dense=True,
            text_size=11,
            width=92,
            border_color=PALETTE["border_strong"],
        )
        satir = ft.Container(
            content=ft.Column([
                ft.Row([ad, miktar, ft.IconButton(ft.Icons.DELETE_OUTLINE_ROUNDED, icon_size=18, icon_color=PALETTE["danger"], tooltip="Kaldır")], spacing=5),
                durum,
            ], spacing=4),
            padding=8,
            bgcolor=PALETTE["surface_alt"],
            border=b_all(1, PALETTE["border"]),
            border_radius=RADIUS_SM,
        )
        satir.content.controls[0].controls[-1].on_click = lambda e, c=satir: kurtarici_satir_sil(c)
        kurtarici_urunler.append((ad, durum, miktar, satir))
        kurtarici_liste.controls.append(satir)
        page.update()

    def kurtarici_satir_sil(satir):
        for i, item in enumerate(list(kurtarici_urunler)):
            if item[3] is satir:
                kurtarici_urunler.pop(i)
                break
        if satir in kurtarici_liste.controls:
            kurtarici_liste.controls.remove(satir)
        page.update()

    def kurtarici_durum_bilgi(durum):
        bilgiler = {
            "Pişmiş / hazır": "Hazır tüketim veya kısa ısıtma gerektiren tarifleri öne çıkar.",
            "Çiğ": "Çiğ ürünün güvenli şekilde pişirilmesini gerektiren tarifleri öne çıkar.",
            "Dondurulmuş": "Önce çözündürme gerekip gerekmediğini kontrol et; uygun tarifleri öne çıkar.",
            "Çözülmüş": "Tekrar dondurmadan önce güvenli kullanım/saklama koşullarını kontrol et.",
            "Açılmış": "Açıldıktan sonra saklama süresi önemli; önce kullanmayı tercih et.",
            "Kapalı paket": "Paket üzerindeki son tüketim/tavsiye edilen tüketim tarihini kontrol et.",
            "Konserve / kavanoz": "Açılmamışsa etiket ve kapak durumunu kontrol et; açıldıysa hızlı kullan.",
            "Kurutulmuş": "Kuru ürünler için tariflerde doğrudan veya ıslatılarak kullanım önerilebilir.",
            "Artan yemek": "Saklama koşulları uygunsa yeniden değerlendirmeye öncelik ver.",
            "Emin değilim": "Durumdan emin değilsen tüketmeden önce görünüş/koku ve güvenli saklama koşullarını kontrol et.",
        }
        return bilgiler.get(durum, bilgiler["Emin değilim"])

    def kurtarici_normalize(metin):
        cevir = {
            "yoğurt": "yogurt", "peynir": "peynir", "kaşar": "kasar", "kıyma": "kiyma",
            "şeker": "seker", "süt": "sut", "çilek": "cilek", "biber": "biber",
            "tavuk": "tavuk", "pilav": "pilav", "makarna": "makarna", "patates": "patates",
        }
        x = str(metin or "").strip().lower()
        for a, b in cevir.items():
            x = x.replace(a, b)
        return x

    def kurtarici_bul(_=None):
        girilen = []
        for ad_kontrol, durum_kontrol, miktar_kontrol, _satir in kurtarici_urunler:
            ad = str(ad_kontrol.value or "").strip()
            if ad:
                girilen.append({
                    "ad": ad,
                    "norm": kurtarici_normalize(ad),
                    "durum": durum_kontrol.value or "Emin değilim",
                    "miktar": str(miktar_kontrol.value or "").strip(),
                })

        kurtarici_sonuc.controls.clear()
        if not girilen:
            kurtarici_sonuc.controls.append(ft.Text("En az bir yiyecek/malzeme ekle. İstersen çiğ, pişmiş, dondurulmuş gibi durumunu da seç.", size=11.5, color=PALETTE["text_soft"]))
            page.update(); return

        # Tarif kataloğundaki malzemeleri her ürünle karşılaştır. Durum bilgisi tarifte
        # bulunmadığı için durum, eşleşmeyi cezalandırmak yerine sonuç açıklamasını ve
        # öncelik/safety notlarını etkiler; böylece çiğ/pişmiş aynı ürün birbirine karışmaz.
        eslesen = []
        for tarif in tarifler:
            malzemeler = [str(x) for x in (tarif.get("malzemeler", []) or [])]
            mal_norm = [kurtarici_normalize(x) for x in malzemeler]
            ad_norm = kurtarici_normalize(tarif.get("ad", ""))
            kullanilan = []
            durumlar = []
            puan = 0.0
            for urun in girilen:
                n = urun["norm"]
                es = any(n in m or m in n for m in mal_norm) or n in ad_norm
                if es:
                    kullanilan.append(urun["ad"])
                    durumlar.append(urun["durum"])
                    puan += 1.0
                    # Artan/pişmiş ürünleri, tarifin yeniden uzun pişirme gerektirmesi
                    # kesin bilinmediği için yalnızca küçük bir öncelik farkıyla ele al.
                    if urun["durum"] in ("Artan yemek", "Pişmiş / hazır"):
                        puan += 0.08
            if kullanilan:
                oran = len(kullanilan) / max(1, len(girilen))
                puan += oran
                eslesen.append((puan, len(kullanilan), tarif, kullanilan, durumlar))

        eslesen.sort(key=lambda x: (-x[0], -x[1], x[2].get("ad", "")))
        if eslesen:
            # Öncelik: bozulma riski yüksek olabilecek durumları kullanıcıya görünür kıl.
            oncelik = [u for u in girilen if u["durum"] in ("Pişmiş / hazır", "Artan yemek", "Çözülmüş", "Açılmış")]
            if oncelik:
                isimler = ", ".join(u["ad"] for u in oncelik[:4])
                kurtarici_sonuc.controls.append(ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Text("🚨", size=18), ft.Text("Önce bunları değerlendirmeyi düşün", size=12.5, weight=ft.FontWeight.W_900, color=PALETTE["text"])], spacing=6),
                        ft.Text(isimler, size=11.5, color=PALETTE["primary_dark"]),
                        ft.Text("Saklama koşulları ve ürünün tarihini kontrol et. Şüpheli/bozulmuş gıdayı tüketme.", size=10.5, color=PALETTE["text_soft"]),
                    ], spacing=3), padding=9, bgcolor=PALETTE["primary_bg"], border_radius=RADIUS_SM, border=b_all(1, PALETTE["primary_soft"])
                ))
            kurtarici_sonuc.controls.append(ft.Text(f"♻️ {len(eslesen)} uygun tarif bulundu", size=11.5, weight=ft.FontWeight.W_800, color=PALETTE["text"]))
            for puan, adet, tarif, kullanilan, durumlar in eslesen[:8]:
                oran_txt = "Çok uygun" if adet >= max(1, len(girilen)) else "Uygun" if adet >= 2 else "Kısmen uygun"
                durum_txt = ", ".join(dict.fromkeys(durumlar))
                kurtarici_sonuc.controls.append(ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text("🍲", size=20),
                            ft.Column([
                                ft.Text(tarif.get("ad", ""), size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"], expand=True),
                                ft.Text(f"♻️ {oran_txt} · Kullanılacak: {', '.join(kullanilan[:4])}", size=10.5, color=PALETTE["primary_dark"]),
                                ft.Text(f"Durum: {durum_txt}", size=10, color=PALETTE["text_soft"]),
                            ], spacing=2, expand=True)
                        ], spacing=7),
                        ft.Text(f"⏱ {tarif.get('sure','-')} · 👨‍🍳 {tarif_zorlugu_hesapla(tarif)} · 🍽️ {tarif.get('kisi_sayisi','4 Kişilik')}", size=10.5, color=PALETTE["text_soft"]),
                    ], spacing=4), padding=10, bgcolor=PALETTE["surface_alt"], border=b_all(1, PALETTE["border"]), border_radius=RADIUS_SM
                ))
        else:
            kurtarici_sonuc.controls.append(ft.Text("Bunlarla eşleşen tarif bulamadım. Malzemeleri farklı adlarla da deneyebilirsin.", size=11.5, color=PALETTE["text_soft"]))

        # Kullanıcının seçtiği durumlara göre kısa rehber.
        for urun in girilen:
            if urun["durum"] != "Emin değilim":
                ikon = dict(KURTARICI_DURUMLARI).get(urun["durum"], "❓")
                kurtarici_sonuc.controls.append(ft.Container(
                    content=ft.Row([ft.Text(ikon, size=15), ft.Column([ft.Text(urun["ad"], size=10.5, weight=ft.FontWeight.W_800, color=PALETTE["text"]), ft.Text(kurtarici_durum_bilgi(urun["durum"]), size=9.5, color=PALETTE["text_soft"])], spacing=1, expand=True)], spacing=7),
                    padding=7, bgcolor=PALETTE["surface_alt"], border_radius=RADIUS_SM
                ))
        page.update()

    def artan_yemek_kurtarici_ac(_=None):
        kurtarici_urunler.clear()
        kurtarici_liste.controls.clear()
        kurtarici_sonuc.controls.clear()
        kurtarici_satir_ekle()
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("♻️ Evdeki yiyecek kurtarıcı", size=18, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
            content=ft.Column([
                ft.Text("Evdeki yenebilir yiyecekleri ekle. Her ürünün durumunu ayrı seçebilirsin; örneğin aynı anda çiğ ve pişmiş tavuk eklemek mümkün.", size=11.5, color=PALETTE["text_soft"]),
                ft.Row([ft.Text("Ürünler", size=12, weight=ft.FontWeight.W_900, color=PALETTE["text"], expand=True), ft.TextButton("＋ Ürün ekle", on_click=kurtarici_satir_ekle)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                kurtarici_liste,
                ft.ElevatedButton("En iyi tarifleri bul 🔎", on_click=kurtarici_bul, style=ft.ButtonStyle(bgcolor=PALETTE["primary"], color=PALETTE["white"])),
                kurtarici_sonuc,
            ], tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
            actions=[ft.TextButton("Kapat", on_click=lambda e: setattr(dlg, "open", False))],
            bgcolor=PALETTE["surface"], shape=ft.RoundedRectangleBorder(radius=RADIUS_LG)
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    # ANA MENÜ
    # Sağ üst ayar çarkı: tıklanınca olduğu yerde kısa bir tur atar.
    ayarlar_carki = ft.Icon(
        ft.Icons.SETTINGS_ROUNDED,
        size=22,
        color=PALETTE["primary_dark"],
        rotate=ft.Rotate(angle=0),
        animate_rotation=ft.Animation(420, ft.AnimationCurve.EASE_OUT),
    )

    async def ayarlar_carki_tiklandi(e):
        ayarlar_carki.rotate = ft.Rotate(angle=6.283185307179586)
        page.update()
        await asyncio.sleep(0.20)
        ayarlar_carki.rotate = ft.Rotate(angle=0)
        page.update()
        ayarlar_penceresi_ac(e)

    ayarlar_butonu = ft.Container(
        content=ayarlar_carki,
        width=42, height=42,
        alignment=ft.alignment.Alignment(0, 0),
        on_click=ayarlar_carki_tiklandi,
        tooltip=_t("home.settings_tooltip"),
    )

    def yardim_penceresi_ac(e):
        def yardim_satiri(icon, baslik, aciklama):
            return ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Icon(icon, size=22, color=PALETTE["primary_dark"]),
                        width=46, height=46,
                        alignment=ft.alignment.Alignment(0, 0),
                        bgcolor=PALETTE["primary_bg"],
                        border_radius=RADIUS_SM + 2,
                    ),
                    ft.Column([
                        ft.Text(baslik, size=13, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                        ft.Text(aciklama, size=10.5, color=PALETTE["text_soft"], weight=ft.FontWeight.W_500, max_lines=4, overflow=ft.TextOverflow.ELLIPSIS),
                    ], spacing=3, expand=True),
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=12,
                bgcolor=PALETTE["surface"],
                border_radius=RADIUS_MD,
                border=b_all(1, PALETTE["border"]),
            )

        yardim_liste = ft.Column([
            yardim_satiri(ft.Icons.KITCHEN_ROUNDED, _t("help_dialog.fridge_title"), _t("help_dialog.fridge_desc")),
            yardim_satiri(ft.Icons.CASINO_ROUNDED, _t("help_dialog.random_title"), _t("help_dialog.random_desc")),
            yardim_satiri(ft.Icons.SHOPPING_CART_ROUNDED, _t("help_dialog.shopping_title"), _t("help_dialog.shopping_desc")),
            yardim_satiri(ft.Icons.CALENDAR_MONTH_ROUNDED, _t("help_dialog.weekly_title"), _t("help_dialog.weekly_desc")),
            yardim_satiri(ft.Icons.SETTINGS_ROUNDED, _t("help_dialog.settings_title"), _t("help_dialog.settings_desc")),
        ], spacing=9, scroll=ft.ScrollMode.AUTO)

        dlg = ft.AlertDialog(
            title=ft.Column([
                ft.Text(_t("help_dialog.title"), size=22, weight=ft.FontWeight.W_900, color=PALETTE["text"]),
                ft.Text(_t("help_dialog.subtitle"), size=11, color=PALETTE["text_soft"], weight=ft.FontWeight.W_600)
            ], spacing=3),
            content=ft.Container(content=yardim_liste, width=390, height=430),
            actions=[ft.TextButton(_t("help_dialog.close_button"), on_click=lambda _: (setattr(dlg, "open", False), page.update()),
                                    style=ft.ButtonStyle(color=PALETTE["primary_dark"]))],
            bgcolor=PALETTE["surface"],
            shape=ft.RoundedRectangleBorder(radius=RADIUS_LG),
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    async def buzdolabi_menu_tiklandi(e):
        ana_menu.opacity = 0.0
        ana_menu.offset = ft.Offset(-0.3, 0)
        page.update()
        await asyncio.sleep(0.15)
        ana_menu.visible = False

        ana_sayfa_icerigi.visible = True
        ana_sayfa_icerigi.offset = ft.Offset(0.5, 0)
        ana_sayfa_icerigi.opacity = 0.0
        page.update()
        await asyncio.sleep(0.05)
        ana_sayfa_icerigi.offset = ft.Offset(0, 0)
        ana_sayfa_icerigi.opacity = 1.0
        page.update()

    async def asistan_menu_tiklandi(e):
        ana_menu.opacity = 0.0
        ana_menu.offset = ft.Offset(-0.3, 0)
        page.update()
        await asyncio.sleep(0.15)
        ana_menu.visible = False

        asistan_ekrani.visible = True
        asistan_ekrani.offset = ft.Offset(0.5, 0)
        asistan_ekrani.opacity = 0.0
        page.update()
        await asyncio.sleep(0.05)
        asistan_ekrani.offset = ft.Offset(0, 0)
        asistan_ekrani.opacity = 1.0
        page.update()

    menu_logo = ft.Container(
        width=64, height=64,
        content=ft.Icon(ft.Icons.RESTAURANT_MENU_ROUNDED, size=34, color=PALETTE["white"]),
        alignment=ft.alignment.Alignment(0, 0),
        bgcolor=PALETTE["primary"],
        border_radius=RADIUS_LG,
        shadow=soft_shadow(16, 1, 0.22, PALETTE["primary"]),
    )

    menu_baslik = ft.Text(_t("home.title"), size=25, weight=ft.FontWeight.W_900, color=PALETTE["text"])
    menu_alt = ft.Text(_t("home.subtitle"), size=12, color=PALETTE["text_soft"], weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER)

    selamlama_metni, selamlama_rozet = zamana_gore_selamlama_al(aktif_dil)
    if kullanici_adi:
        menu_hero_baslik = ft.Text(
            f"{selamlama_metni}, {kullanici_adi}!" if aktif_dil == "tr" else f"{selamlama_metni}, {kullanici_adi}!",
            size=14, weight=ft.FontWeight.W_900, color=PALETTE["text"]
        )
    else:
        menu_hero_baslik = ft.Text(selamlama_metni, size=14, weight=ft.FontWeight.W_900, color=PALETTE["text"])
    # Mevsimsel / dönemsel ana ekran mesajı
    ay = datetime.now().month
    mevsim_mesaji = _t("home.hero_subtitle")
    if bool(kayitli_ayar.get("mevsim_modu", True)):
        if ay in (12, 1, 2):
            mevsim_mesaji = "❄️ Kış mutfağı zamanı — sıcak, doyurucu tarifler seni bekliyor."
        elif ay in (3, 4, 5):
            mevsim_mesaji = "🌸 Bahar mutfağı zamanı — daha ferah tariflere göz at."
        elif ay in (6, 7, 8):
            mevsim_mesaji = "☀️ Yaz mutfağı zamanı — hafif ve pratik bir şeyler seç."
        else:
            mevsim_mesaji = "🍂 Sonbahar mutfağı zamanı — sıcacık ev yemekleri için güzel bir gün."
    if kayitli_ayar.get("donem_modu") == "ramazan":
        mevsim_mesaji = "🌙 Ramazan mutfağı modu — iftar ve sahur için ilham burada."
    menu_hero_alt = ft.Text(mevsim_mesaji, size=11, color=PALETTE["text_soft"], weight=ft.FontWeight.W_600)
    menu_tarif_sayisi = ft.Text(_t("home.archive_line", count=len(tarifler)), size=11.5, color=PALETTE["primary_dark"], weight=ft.FontWeight.W_800)

    def menu_kart_olustur(icon, baslik, aciklama, tiklama, rozet=None, vurgu=False):
        rozet_kutu = ft.Container()
        if rozet:
            rozet_kutu = ft.Container(
                content=ft.Text(rozet, size=10, weight=ft.FontWeight.W_800, color=PALETTE["white"]),
                padding=m_symmetric(horizontal=8, vertical=3),
                bgcolor=PALETTE["primary"],
                border_radius=10,
            )

        kart_bg = PALETTE["primary_bg"] if vurgu else PALETTE["surface"]
        kart_border = PALETTE["primary_soft"] if vurgu else PALETTE["border"]
        icon_bg = PALETTE["primary"] if vurgu else PALETTE["primary_bg"]
        icon_color = PALETTE["white"] if vurgu else PALETTE["primary_dark"]

        k = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(icon, size=23, color=icon_color),
                    width=46, height=46,
                    alignment=ft.alignment.Alignment(0, 0),
                    bgcolor=icon_bg,
                    border_radius=RADIUS_SM + 2,
                ),
                ft.Column([
                    ft.Row([
                        ft.Text(baslik, size=14, weight=ft.FontWeight.W_900, color=PALETTE["text"], expand=True),
                        rozet_kutu
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text(aciklama, size=11, color=PALETTE["text_soft"], weight=ft.FontWeight.W_500, max_lines=2),
                ], spacing=2, expand=True),
                ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=PALETTE["text_faint"], size=22)
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=14,
            bgcolor=kart_bg,
            border_radius=RADIUS_MD + 2,
            border=b_all(1.4, kart_border),
        )
        k.opacity = 0.0
        k.offset = ft.Offset(0.10, 0)
        k.animate_opacity = ft.Animation(260, ft.AnimationCurve.EASE_OUT)
        k.animate_offset = ft.Animation(320, ft.AnimationCurve.EASE_OUT_CUBIC)
        return yapilandir_etkilesim(
            k, on_click=tiklama, hover_scale=1.02, basma_scale=0.97,
            temel_golge=soft_shadow(8, 0, 0.06), hover_golge=soft_shadow(16, 1, 0.14, PALETTE["primary"])
        )

    menu_kartlari = ft.Column([
        menu_kart_olustur(ft.Icons.KITCHEN_ROUNDED, _t("home.card_fridge_title"), _t("home.card_fridge_subtitle"), buzdolabi_menu_tiklandi, rozet=_t("home.card_fridge_badge"), vurgu=True),
        menu_kart_olustur(ft.Icons.CASINO_ROUNDED, _t("home.card_random_title"), _t("home.card_random_subtitle"), rastgele_tarif_getir),
        menu_kart_olustur(ft.Icons.RECYCLING_ROUNDED, "Artan yemek kurtarıcı", "Evde kalan malzemeyi çöpe gitmeden değerlendir.", artan_yemek_kurtarici_ac, rozet="YENİ"),
        menu_kart_olustur(ft.Icons.SHOPPING_CART_ROUNDED, _t("home.card_shopping_title"), _t("home.card_shopping_subtitle"), alisveris_listesini_goster),
        menu_kart_olustur(ft.Icons.CALENDAR_MONTH_ROUNDED, _t("home.card_menu_title"), _t("home.card_menu_subtitle"), haftalik_menu_goster),
        menu_kart_olustur(ft.Icons.SUPPORT_AGENT_ROUNDED, _t("home.card_assistant_title"), _t("home.card_assistant_subtitle"), asistan_menu_tiklandi, rozet=_t("home.card_assistant_badge")),
    ], spacing=10)

    ana_menu = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.IconButton(
                    icon=ft.Icons.EMOJI_EVENTS_ROUNDED,
                    icon_size=22,
                    icon_color=PALETTE["primary_dark"],
                    tooltip="Başarımlar",
                    on_click=mutfak_karnesi_ac,
                ),
                ft.Column([menu_logo, menu_baslik, menu_alt], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([
                    ft.IconButton(icon=ft.Icons.HELP_OUTLINE_ROUNDED, icon_size=22, icon_color=PALETTE["primary_dark"], tooltip=_t("home.help_tooltip"), on_click=yardim_penceresi_ac),
                    ayarlar_butonu,
                ], spacing=0)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Container(height=4),
            ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Text(selamlama_rozet, size=11, color=PALETTE["white"], weight=ft.FontWeight.W_800),
                        padding=m_symmetric(horizontal=10, vertical=4),
                        bgcolor=PALETTE["primary"],
                        border_radius=12,
                    ),
                    ft.Column([menu_hero_baslik, menu_hero_alt, menu_tarif_sayisi], spacing=3, expand=True),
                ], spacing=12),
                padding=14, bgcolor=PALETTE["primary_bg"], border_radius=RADIUS_LG,
                border=b_all(1.2, PALETTE["primary_soft"]),
            ),
            ft.Container(height=2),
            menu_kartlari,
            ft.Container(height=2),
            ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=13, color=PALETTE["primary"]),
                ft.Text(_t("app.footer_tagline"), size=9.5, color=PALETTE["text_faint"], weight=ft.FontWeight.W_700),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=4),
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, scroll=ft.ScrollMode.AUTO),
        padding=18, expand=True, bgcolor=PALETTE["bg"], visible=False, opacity=0.0,
        offset=ft.Offset(0, 0),
        animate=ft.Animation(300, ft.AnimationCurve.DECELERATE),
        animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT)
    )

    sohbet_ekranini_yukle()
    page.add(splash_ekrani, ana_menu, ana_sayfa_icerigi, asistan_ekrani)

    async def akilli_bildirimleri_goster():
        ayarlar = veri_yukle(ayar_DOSYA)
        if not isinstance(ayarlar, dict): ayarlar = {}
        bild = ayarlar.get("bildirimler", {}) if isinstance(ayarlar.get("bildirimler", {}), dict) else {}
        if not bild.get("gunluk", True): return
        bugun = datetime.now().date().isoformat()
        son = ayarlar.get("son_akilli_bildirim", "")
        if son == bugun: return
        # İlk açılışta küçük bir akıllı öneri kartı göster.
        uygun = tarifler[:]
        if not uygun: return
        import random
        tarif = random.choice(uygun)
        dlg = ft.AlertDialog(modal=True, title=ft.Text("🔔 Bugünün mutfak notu", size=18, weight=ft.FontWeight.W_900), content=ft.Column([ft.Text(f"Bugün şunu deneyebilirsin: {tarif.get('ad','Bir tarif')}", size=13, weight=ft.FontWeight.W_800), ft.Text("İstersen tarif arşivinden açıp hemen başlayabilirsin. 🍳", size=11.5, color=PALETTE["text_soft"])], tight=True, spacing=7), actions=[ft.TextButton("Daha sonra", on_click=lambda e: (setattr(dlg,"open",False), page.update())), ft.ElevatedButton("Tamam", on_click=lambda e: (ayarlar.__setitem__("son_akilli_bildirim", bugun), veri_kaydet(ayar_DOSYA, ayarlar), setattr(dlg,"open",False), page.update()), style=ft.ButtonStyle(bgcolor=PALETTE["primary"], color=PALETTE["white"]))])
        page.overlay.append(dlg); dlg.open=True; page.update()

    async def degerlendirme_istegi_goster():
        # Kullanıcıyı sıkmadan, uygulama açılışlarında ara sıra değerlendirme ister.
        import random
        ayarlar = veri_yukle(ayar_DOSYA)
        if not isinstance(ayarlar, dict):
            ayarlar = {}
        try:
            son = float(ayarlar.get("son_degerlendirme_istegi", 0) or 0)
        except Exception:
            son = 0
        simdi = time.time()
        # En az 7 gün ara; ayrıca her uygun açılışta %35 olasılık.
        if simdi - son < 7 * 24 * 3600 or random.random() > 0.35:
            return

        puan = {"value": 0}
        yildizlar = ft.Row(spacing=2, alignment=ft.MainAxisAlignment.CENTER)
        for i in range(1, 6):
            btn = ft.IconButton(icon=ft.Icons.STAR_BORDER_ROUNDED, icon_size=30, tooltip=f"{i} yıldız")
            def sec(e, n=i):
                puan["value"] = n
                for j, c in enumerate(yildizlar.controls, 1):
                    c.icon = ft.Icons.STAR_ROUNDED if j <= n else ft.Icons.STAR_BORDER_ROUNDED
                page.update()
            btn.on_click = sec
            yildizlar.controls.append(btn)

        async def sonra(e):
            ayarlar["son_degerlendirme_istegi"] = time.time()
            veri_kaydet(ayar_DOSYA, ayarlar)
            degerlendirme_dialogu.open = False
            page.update()

        async def gonder(e):
            if not puan["value"]:
                return
            ayarlar["son_degerlendirme_istegi"] = time.time()
            ayarlar["son_degerlendirme_puani"] = puan["value"]
            veri_kaydet(ayar_DOSYA, ayarlar)
            degerlendirme_dialogu.open = False
            page.update()

        degerlendirme_dialogu = ft.AlertDialog(
            modal=True,
            title=ft.Text("❤️ Nöbetçi Ev'i değerlendirir misin?", size=18, weight=ft.FontWeight.W_900),
            content=ft.Column([
                ft.Text("Uygulamayı geliştirmemize yardımcı olmak için deneyimini puanlayabilirsin.", size=12, text_align=ft.TextAlign.CENTER),
                yildizlar,
            ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            actions=[
                ft.TextButton("Daha sonra", on_click=sonra),
                ft.ElevatedButton("Gönder", on_click=gonder),
            ],
        )
        page.overlay.append(degerlendirme_dialogu)
        degerlendirme_dialogu.open = True
        page.update()

    async def ana_menu_kartlarini_oynat():
        await asyncio.sleep(0.05)
        for kart in menu_kartlari.controls:
            kart.offset = ft.Offset(0, 0)
            kart.opacity = 1.0
            page.update()
            await asyncio.sleep(0.075)

    await asyncio.sleep(0.1)
    splash_logo.scale = 1.0
    splash_logo.opacity = 1.0
    page.update()

    await asyncio.sleep(2.2)

    splash_ekrani.visible = False
    # İlk açılışta sürprizi bozmamak için ana menü isim girilene kadar görünmez.
    if kullanici_adi:
        ana_menu.visible = True
        ana_menu.opacity = 1.0
        page.update()
        page.run_task(ana_menu_kartlarini_oynat)
        page.run_task(degerlendirme_istegi_goster)
    else:
        page.update()
        await ilk_acilis_isim_sor()

# Uygulama Başlatıcı
if __name__ == "__main__":
    ft.run(main)