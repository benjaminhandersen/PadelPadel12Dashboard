# Padel Dashboard

Et simpelt dashboard der henter data fra rankedin.com og viser statistik
for jeres padelhold — win/loss pr. spiller, makkerpar, kampdetaljer og puljestilling.

## Installation

```bash
# 1. Opret et virtual environment (anbefalet)
python -m venv .venv

# Aktivér det
# På macOS / Linux:
source .venv/bin/activate
# På Windows:
.venv\Scripts\activate

# 2. Installer afhængigheder
pip install -r requirements.txt
```

## Kør

**Kommandolinje-version** (printer tabeller i terminalen):

```bash
python padel_pipeline.py
```

**Interaktivt dashboard** i browseren:

```bash
streamlit run dashboard.py
```

Åbner automatisk på <http://localhost:8501>.

## Konfiguration

### Bødekassen

Hele appen kræver adgang ved indgangen, inklusive Holdforslag og direkte links
til Bødekassen. Holdet ønsker én fælles adgangskode. Aktivér dette i Streamlit
Community Cloud under appens **Settings → Secrets**:

```toml
[access]
password = "VÆLG-JERES-EGEN-FÆLLES-KODE"

[supabase]
secret_key = "sb_secret_INDSÆT-SERVERNØGLEN-HER"
```

Hent servernøglen under Supabase **Settings → API Keys → Secret keys**.
Hvis `[supabase]` allerede findes i Secrets, tilføjes `secret_key` i den
eksisterende sektion. Koden og servernøglen må kun gemmes i Secrets eller
miljøvariablerne `APP_PASSWORD`/`SUPABASE_SECRET_KEY`; de sendes ikke til browseren
eller GitHub. Der er ingen standardkode. Begge værdier kræves for at aktivere
fælles adgang. Indtil opsætningen er udført, bruges den eksisterende kontologin.
Delvis opsætning blokerer adgang i stedet for at åbne appen.

Alle med fælleskoden kan se data, give/fortryde bøder og ændre satser. Ingen skal
oprette en personlig bruger eller oplyse e-mail. Handlinger er fælles og kan
ikke henføres til den person, der udførte dem. Kodeændring kræver nyt login i
eksisterende sessioner. Databasen er fortsat lukket for offentlige klienter;
Python-serveren kontrollerer adgang før hver databasehandling. Bødekassen har
ikke et separat login. Importerede bøder og spiller-id'er bevares.

Find fanen **Bødekassen** i dashboardet, eller brug den separate side i menuen
(den virker også, hvis Rankedin er utilgængelig). Vælg bødetype og tryk på en
spiller. Overblik viser stillingen; Historik giver fortryd/gendan og CSV-eksport.
Overblik henter automatisk friske bøder hvert 15. sekund, mens siden er åben.
Kun overblikket opdateres; Rankedin, tildelingsknapper og indstillinger genkøres
ikke af timeren. Filtre og sortering bevares. Egne tildelinger vises straks.
Indstillinger lader jer ændre satser for fremtidige bøder.
Spillere hentes fra Rankedin (holdopstilling og holdets kampe i valgt sæson).
Spillere kan ikke tilføjes manuelt. Uden spillerdata blokeres nye bøder,
mens overblik og historik bevares, også for tidligere spillere.
Satser følger inspirationsarket. Den 26. oktober 2026 blev 31 registreringer
importeret i Supabase: 58 aktive bøder på 1.310 kr. og 6 annullerede registreringer.
Historiske antal bevares samlet, og ukendte datoer vises som ukendte.

Bødekassen gemmes fælles og varigt i Supabase. I den tidligere kontotilstand
(når fælleskoden ikke er konfigureret) bruges din egen holdkonto under
**Opret konto**, bekræft e-mailen, og log ind. En konto giver kun adgang, når
dens bekræftede e-mail er godkendt i `padel_members`. Kun administratoren må
ændre satser og synkronisere spillerlisten; holdmedlemmer må give og fortryde
bøder. Ingen offentlig læse- eller skriveadgang. Registreringers beløb kan ikke
ændres fra appen, og eksisterende beløb bevares ved satsændringer.

`supabase_public.json` indeholder kun projektets URL og en **publishable key**,
som er beregnet til offentlige klienter. Fælleskodetilstanden bruger derudover
en servernøgle fra Secrets, mens kontotilstanden bruger RLS og personligt login.
URL/publishable key kan tilsidesættes med
`SUPABASE_URL`/`SUPABASE_PUBLISHABLE_KEY` eller følgende Streamlit Secrets:

```toml
[supabase]
url = "https://DIT-PROJEKT.supabase.co"
publishable_key = "sb_publishable_..."
```

Administratoradgang tildeles af projektejeren i Supabase, eksempelvis:

```sql
insert into public.padel_members(email, role)
values ('spiller@example.com', 'member')
on conflict(email) do update set role=excluded.role;
```

Sæt **Authentication → URL Configuration → Site URL** til onlineappens URL,
så bekræftelseslinks fører tilbage til appen. Supabases standard-mailservice
har begrænsninger; almindelig holdtilmelding kræver egen SMTP eller en
konfigureret OAuth-udbyder. Der sendes ikke invitationer automatisk ved godkendelse.
Login gemmes kun i den enkelte Streamlit-session; genindlæsning kan kræve nyt login.

SQL-versioner ligger i `supabase/migrations`. Importforberedelse køres med
`python prepare_fines_import.py` mod de lokale filer i `data/`; det skriver
kun en SQL-fil. Importens kilde-id'er forhindrer dubletter ved gentagelse.
Personlige importdata ligger uden for Git. Kontrollér altid spillermapping
og totalsum før import. Fremtidige registreringer skal ske i appen; arket
synkroniseres ikke løbende.

Til lokale tests kan `PADEL_FINES_DB` pege på en separat SQLite-fil. Der er
ingen automatisk lokal reserve, hvis Supabase fejler. Bødesaldo er tildelte
bøder, ikke indbetalinger. Kassen er fælles på tværs af sæsonvalg.

Rediger øverst i `padel_pipeline.py`:

```python
OUR_TEAM_ID = 2701885        # jeres hold-ID
OUR_POOL_ID = 11353          # puljens ID
```

ID'erne findes i Rankedin-URL'en når I er inde på holdsiden
(fx `rankedin.com/en/team/homepage/2701885` → team-ID er `2701885`).

## Vigtigt — bekræft URL'erne

Fire endpoints bruges. **Kun den første er bekræftet fra browser-testning** —
de andre tre er kvalificerede gæt baseret på Rankedins navnekonvention.

Hvis du får `404 Not Found` ved kørsel, så åbn DevTools (F12) i din browser,
gå til fanen Network → Fetch/XHR, og bekræft de faktiske URL'er. Opdatér
funktionerne `url_team_match_details`, `url_team_match_lineup` og
`url_pool_standings` i `padel_pipeline.py`.

## Caching

Alle HTTP-svar caches lokalt i `cache/`-mappen så du ikke belaster
Rankedins servere under udvikling. For at hente friske data:

- Klik **🔄 Opdater fra Rankedin** i Streamlit-sidebaren, eller
- Slet `cache/`-mappen manuelt, eller
- Kald `build_dataset(refresh=True)` direkte fra kode.

## Filstruktur

```
padel_dashboard/
├── padel_pipeline.py   # data-fetching, parsing, statistik
├── dashboard.py        # Streamlit UI
├── requirements.txt    # pandas, requests, streamlit
├── README.md           # denne fil
└── cache/              # HTTP-cache (oprettes automatisk)
```

## Juridisk

Rankedins Terms of Use begrænser systematisk download af deres indhold.
Kontakt support@rankedin.com og bed om officiel tilladelse hvis dashboardet
skal bruges kommercielt eller til andet end privat klubbrug.

### Holdforslagenes styrkevurdering
Forslagene sorterer hvert rundes tre par efter vurderet styrke: stærkest på bane 1.
Hver historisk kamp giver 100 ved sejr eller 0 ved nederlag, plus gameforskel
begrænset til ±10 og banetillæg +20/0/−20 for bane 1/2/3 (også ved nederlag).
Baner udledes som en antagelse af Rankedin-kamppladserne 1–3 og 4–6 ved
MatchOrder=1; manglende/ukendt rækkefølge og en syvende kamp får intet tillæg.
Uspillede kamppladser bevares ved udledning af banen.
Spillerscoren er gennemsnittet med to neutrale kampe på 50 som udgangspunkt.
Nye makkerpar får gennemsnittet af spillernes scores og markeres tydeligt.
Kendte pars fælles resultater blandes med individvurderingen, der vægter som
fire kampe. Uden individuel historik bruges 50. Den samlede opstillingsscore
er summen af seks parvurderinger plus 5 % af spillerscoren pr. deltagelse.
Vægtene er heuristiske, ikke en beregnet vinderchance; alle sæsoner tilføjet dashboardet bruges og vægter ens.

Holdforslag og den kompakte sammenligning viser makkerpar på enkle kort. Kendte par viser sejre/kampe fordelt på bane 1, 2 og 3; ukendt bane indgår kun i den samlede historik. Nye par markeres fortsat tydeligt.

### Holdoverblik
Hovedsiden hedder Holdoverblik i navigationen. Sæsonens nøgletal, næste kamp,
seneste fem resultater og puljestilling vises grafisk. Spillere, makkerpar og
kampe har responsive kort; detaljerede tabeller kan fortsat åbnes.
Oversigten bruger den valgte sæson, mens Holdforslag bruger alle tilføjede sæsoner.
