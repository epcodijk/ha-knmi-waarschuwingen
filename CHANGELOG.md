# Changelog

## 0.1.4

- Eigen icoon (origineel ontwerp, geen bestaand logo) in `brand/`, zichtbaar in Home Assistant 2026.3+ en de Marketplace. Bron: `assets/icon.svg`.

## 0.1.3

- Duidelijk vermeld dat dit een **onofficiële** integratie is: in de naam, het configuratieformulier, de apparaatinfo en de attributie van de sensoren.
- Uitgebreide disclaimer in de README (geen garantie, geen aansprakelijkheid, niet voor veiligheidskritisch gebruik, bronvermelding KNMI CC BY 4.0, privacy).

## 0.1.2

- **Eigen API-key verplicht.** De ingebouwde anonieme KNMI-key werkte niet. Bij het toevoegen vul je nu je eigen gratis Open Data API-key in. Het formulier linkt naar het KNMI Developer Portal.
- Bestaande installaties zonder key krijgen automatisch een melding om een key in te vullen (herauthenticatie).
- README bijgewerkt met de stappen om een key aan te vragen en uitleg over het quotum.

## 0.1.1

- Het configuratieformulier toont nu de echte foutoorzaak (HTTP-status, DNS, time-out) in plaats van alleen "Could not connect", en schrijft die ook naar de log.
- Een ongeldige of verlopen key wordt altijd als key-fout gemeld.
- Tests voor de API-client toegevoegd.

## 0.1.0

- Eerste versie: KNMI-weerwaarschuwingen uit de dataset `KNMI-public-weather-warnings` (flexibele gebieden sinds 2 november 2026), getoetst aan je exacte locatie.
