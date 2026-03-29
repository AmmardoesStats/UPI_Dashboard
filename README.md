# India UPI State-Level Digitisation Analysis

33 months of NPCI transaction data (May 2023 – Jan 2026) combined with MOSPI GDP data and Census 2011 population projections, analysed at the state level across all 34 states.

**[→ View interactive dashboard](https://yourusername.github.io/upi-digitisation-india/upi_dashboard_final.html)**

## Key findings

- A **7× per capita gap** separates Delhi (22.5 transactions/person/month) from Bihar (3.2) — a divide invisible in aggregate volume rankings
- Average transaction sizes are **falling in every state**, a signature of mass-market adoption spreading into lower-income segments
- The top 5 states' share of national UPI value fell **6.6 percentage points** over 33 months — but depth gaps between states are not narrowing
- **Telangana** (134% UPI intensity) and **Ladakh** (119%) transact more through UPI than their GSDP per capita — the clearest outliers above the income-digitisation diagonal
- **Gujarat** (44% intensity) is the most striking under-performer relative to its income level

## Repository structure

```
upi-digitisation-india/
│
├── README.md
├── requirements.txt
│
├── npci_scraper.py          # Scrapes raw NPCI Excel files (undetected-chromedriver)
├── generate_dashboard.py    # Builds the self-contained HTML dashboard from data
├── upi_dashboard_final.html # Pre-built dashboard (ready to deploy)
│
├── notebooks/
│   └── analysis.ipynb       # Full analysis pipeline: clean → GSDP → intensity → charts
│
└── data/                    # Not tracked in git (see Data section below)
    ├── npci_statewise_master.csv
    ├── npci_statewise_clean.csv
    ├── gsdp_clean.csv
    ├── npci_intensity_panel.csv
    ├── npci_intensity_summary.csv
    ├── MOSPI_Table21_GSDP.xlsx
    └── analysis_*.csv
```

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Scrape NPCI data

```bash
python npci_scraper.py
```

Downloads one Excel file per month into `npci_statewise_data/`. Requires Chrome. Uses `undetected-chromedriver` to handle NPCI's bot detection. Run once — subsequent runs skip already-downloaded months.

### 3. Run the analysis notebook

Open `notebooks/analysis.ipynb` and run all cells in order. You will also need to place the MOSPI GSDP Excel file at `data/MOSPI_Table21_GSDP.xlsx` — see Data Sources below.

### 4. Regenerate the dashboard

```bash
python generate_dashboard.py              # writes upi_dashboard_final.html
python generate_dashboard.py --open       # also opens in browser
python generate_dashboard.py --out my.html
```

## Data sources

| Source | What | Where |
|--------|------|-------|
| NPCI Ecosystem Statistics | State-wise UPI transaction volume and value, monthly | [npci.org.in](https://www.npci.org.in/product/ecosystem-statistics/upi) |
| MOSPI National Accounts | Table 21 — GSDP at Current Prices, Base 2011-12 | [mospi.gov.in](https://mospi.gov.in/national-accounts-statistics) |
| Census of India 2011 | State-level population (projected to 2024 using decadal growth rates) | [censusindia.gov.in](https://censusindia.gov.in) |

The `data/` directory is excluded from version control (see `.gitignore`). Raw NPCI files are ~1–2 MB per month; the MOSPI Excel is publicly available from the link above.

## Methodology

**Per capita figures** use the average of the last 12 months of the dataset (Feb 2025 – Jan 2026). Population denominator: Census 2011 projected to 2024 using state-specific decadal growth rates, consistent with MOSPI methodology.

**Growth trajectory** compares average monthly volume in Year 1 (May 2023 – Apr 2024) vs Year 2 (Feb 2025 – Jan 2026). Categories: Accelerating >30%, Steady Growth 10–30%, Plateauing <10%, Declining.

**UPI intensity** = annual UPI value per capita / GSDP per capita × 100. GSDP mapped to fiscal year: Apr–Mar. FY2025-26 GSDP extrapolated via state-specific 5-year CAGR (MOSPI data not yet published for that year).

**Ticket size** = (Monthly Value Cr / Monthly Volume Mn) × 10 = Rs per transaction.

**Two important caveats:**
1. NPCI records the sending bank account's registered state, not the location of the transaction. States with large migrant populations (UP, Bihar, Jharkhand) may be understated in local digitisation terms.
2. ~30% of national UPI volume is unclassified by NPCI and excluded from all state-level analysis. National headline KPIs use full totals; state rankings use the classified pool only.

## Dashboard deployment (GitHub Pages)

1. Push this repository to GitHub
2. Go to **Settings → Pages → Deploy from branch → main / root**
3. Your dashboard will be live at `https://yourusername.github.io/upi-digitisation-india/upi_dashboard_final.html`

## License

Code: MIT  
Data: NPCI and MOSPI data are publicly available under their respective terms of use.
