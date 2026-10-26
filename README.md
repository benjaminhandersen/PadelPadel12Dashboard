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

Hele appen kræver login med en godkendt holdkonto. Det gælder dashboardet,
Holdforslag og direkte links til Bødekassen. Login kontrolleres før Rankedin-data
hentes eller vises. Den samme konto og session bruges på alle sider; bødekassen
har ikke et separat login. E-mailen behøver ikke være den samme som på Rankedin.

Find fanen **Bødekassen** i dashboardet, eller brug den separate side i menuen
(den virker også, hvis Rankedin er utilgængelig). Vælg bødetype og tryk på en
spiller. Overblik viser stillingen; Historik giver fortryd/gendan og CSV-eksport.
Indstillinger lader jer ændre satser for fremtidige bøder.
Spillere hentes fra Rankedin (holdopstilling og holdets kampe i valgt sæson).
Spillere kan ikke tilføjes manuelt. Uden spillerdata blokeres nye bøder,
mens overblik og historik bevares, også for tidligere spillere.
Satser følger inspirationsarket. Den 26. oktober 2026 blev 31 registreringer
importeret i Supabase: 58 aktive bøder på 1.310 kr. og 6 annullerede registreringer.
Historiske antal bevares samlet, og ukendte datoer vises som ukendte.

Bødekassen gemmes fælles og varigt i Supabase. Brug din egen holdkonto under
**Opret konto**, bekræft e-mailen, og log ind. En konto giver kun adgang, når
dens bekræftede e-mail er godkendt i `padel_members`. Kun administratoren må
ændre satser og synkronisere spillerlisten; holdmedlemmer må give og fortryde
bøder. Ingen offentlig læse- eller skriveadgang. Registreringers beløb kan ikke
ændres fra appen, og eksisterende beløb bevares ved satsændringer.

`supabase_public.json` indeholder kun projektets URL og en **publishable key**,
som er beregnet til offentlige klienter. Ingen service-nøgle bruges. RLS og
brugerens Supabase-login beskytter alle data. URL/nøgle kan tilsidesættes med
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
