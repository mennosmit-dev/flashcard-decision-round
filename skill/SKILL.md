---
name: vragenronde
description: "Stelt je een rij korte vragen achter elkaar als flashcards in een klein browservenster, die je met de cijfertoetsen in seconden beantwoordt. Daarna gaat de agent verder met jouw antwoorden. Gebruik dit als er 5 of meer keuzes tegelijk te maken zijn (bijvoorbeeld bij de grote schoonmaak: welke breadcrumbs weg, wat samenvoegen), in plaats van ze één voor één in de chat te vragen."
date: 2026-06-28
tags:
  - vragenronde
---

# vragenronde

In plaats van traag heen-en-weer in de chat, of de agent laten gokken: de agent zet een rijtje keuzes klaar als flashcards in een klein browservenster. Jij beantwoordt ze met de cijfertoetsen, en de agent rent daarna door met jouw antwoorden. De agent doet de bulk; jij maakt alleen de oordelen die alleen jij kunt maken.

## Wanneer

- Er zijn **5 of meer** keuzes tegelijk te maken. Bij minder vraag je het gewoon in de chat.
- Vooral handig bij de grote schoonmaak van een dossier: per breadcrumb "weg, houden of samenvoegen", in één snelle flow in plaats van twintig keer heen en weer.

## Hoe je het aanroept

Draai het script in één keer en geef de vragen als JSON mee via stdin (geen tijdelijk bestand, dat kost een extra ronde):

```bash
python "<map van deze skill>/scripts/vragenronde.py" - <<'EOF'
{"options": ["weg", "houden", "samenvoegen"], "questions": [{"id": "bc1", "q": "Breadcrumb 12 jan (opdracht gestart): weg, houden of samenvoegen?"}]}
EOF
```

Het script blokkeert tot je in het venster op verzenden drukt en geeft dan de antwoorden als JSON terug. Lees die en ga verder. Exitcode 1 = geannuleerd of time-out: val terug op losse vragen in de chat, niet opnieuw proberen.

## Invoer

Geef bij voorkeur één set `options` op batch-niveau, zodat dezelfde cijfertoets de hele ronde hetzelfde betekent (dat is wat het snel en intuïtief maakt). Een vraag mag een eigen `options` hebben als die echt afwijkt.

```json
{
  "options": ["weg", "houden", "samenvoegen"],
  "questions": [
    {"id": "bc1", "q": "Breadcrumb 12 jan: opdracht gestart. Weg?"},
    {"id": "bc2", "q": "Breadcrumb 30 mei: klant levert data. Open loop?"},
    {"id": "focus", "q": "Waar mag het diepst gesnoeid worden?", "options": ["overzicht", "status", "rode draad"]}
  ]
}
```

`options` is optioneel; standaard `["ja", "nee"]`. Een optie mag ook `{"value", "label", "hint"}` zijn. Per vraag optioneel `kop` (kleine regel erboven) en `meta` (labels; `{"text", "tone": "warn"}` voor rood). `skip` op batch-niveau hernoemt de overslaanknop (spatie of backtick). Maximaal 9 opties per vraag. Antwoorden gaan per stuk naar het script; time-out standaard 3600 s en geeft de antwoorden tot dan terug. Alle `id`-waarden uniek.

## Toetsen

- `1`–`9`: kies een optie (1 = eerste optie, enzovoort)
- `a`: typ een vrij antwoord of nuance. Een tekstveld opent; Enter verzendt, Esc terug naar de opties
- spatie of `` ` `` (backtick, links van de 1): sla de vraag over, het antwoord is leeg
- `←`: terug naar de vorige vraag
- Enter op het overzicht aan het eind: verzenden

## Uitvoer

Eén JSON-object op stdout, met per vraag-id het antwoord. Overgeslagen vragen worden leeg. Een vrij antwoord (de `a`-toets) komt terug als de getypte tekst.

```json
{"bc1": "weg", "bc2": "houden", "focus": "status"}
```

## Tips

- Alleen platte tekst, geen opmaak. Heeft een vraag context nodig, zet die in de vraagtekst zelf.
- Houd de optieset over gelijksoortige vragen hetzelfde: dat de cijfertoetsen steeds hetzelfde betekenen is juist de kracht. Plak er geen losse "anders"- of "overslaan"-optie bij: de `a`-toets (vrij antwoord) en spatie of `` ` `` (overslaan) zitten er al in.
- Houd vragen kort en op zichzelf staand. Zet vragen die op elkaar voortbouwen later in de rij.
