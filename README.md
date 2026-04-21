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
