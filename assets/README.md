# Icoon

`icon.svg` is een **origineel ontwerp** voor dit project (november 2026). Het is niet afgeleid van het KNMI-logo, het Home Assistant-logo of een ander bestaand logo of merk.

- Afgeronde driehoek met drie kleurbanden (geel, oranje, rood) voor de waarschuwingscodes
- Wolk als algemeen weersymbool
- Locatiespeld voor "waarschuwingen voor jouw locatie"

Alleen generieke vormen (driehoek, cirkels, rechthoeken), geen tekst en geen merknamen.
Valt onder dezelfde [MIT-licentie](../LICENSE) als de code.

De PNG's in `custom_components/knmi_waarschuwingen/brand/` zijn hieruit gerenderd (bijgesneden, vierkant, 256 en 512 px):

```bash
rsvg-convert -w 1024 -h 1024 assets/icon.svg -o /tmp/icon.png   # daarna bijsnijden en schalen
```
