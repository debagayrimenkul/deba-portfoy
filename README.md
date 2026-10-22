# Deba Portföy

Mobil uyumlu ofis içi gayrimenkul portföy yönetimi MVP'si.

## Kurulum
1. Python 3.10+ kurulu olmalı.
2. Bu klasörde terminal açın.
3. `pip install -r requirements.txt`
4. `python app.py`
5. Tarayıcıda `http://127.0.0.1:5000`

## İlk giriş
- Kullanıcı: `admin`
- Şifre: `Deba2026!`

İlk girişten sonra üretim kullanımı öncesi admin şifresini kod/veritabanı üzerinden değiştirmek ve güçlü bir SECRET_KEY tanımlamak gerekir. İnternete açmadan önce HTTPS, düzenli yedek, CSRF koruması, parola sıfırlama ve sunucu yapılandırması eklenmelidir.

## Özellikler
- Admin / danışman girişi
- Satılık / kiralık ayrı ekranlar
- Mobil kart görünümü
- Filtreleme
- Daire / villa / iş yeri / arsa formları
- Danışmanın yalnızca kendi portföyünü değiştirmesi
- Portföyden çıkarma nedeni ve arşiv
- Kullanıcı oluşturma
