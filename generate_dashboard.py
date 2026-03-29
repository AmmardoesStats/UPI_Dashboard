"""
generate_dashboard.py
=====================
Generates the India UPI State-Level Digitisation Dashboard as a self-contained HTML file.

Data sources
------------
- NPCI Ecosystem Statistics: State-wise UPI Product Statistics (May 2023 – Jan 2026)
  https://www.npci.org.in/what-we-do/upi/product-statistics
- MOSPI National Accounts: Table 21, GSDP at Current Prices, Base 2011-12
  https://mospi.gov.in/national-accounts-statistics
- Population: Census of India 2011 projected to 2024 using state-specific decadal
  growth rates (consistent with MOSPI methodology)

Methodological notes
--------------------
- ~30% of national UPI volume is unclassified by NPCI and excluded from state analysis.
  National headline KPIs use full totals; all state rankings use the classified pool.
- NPCI records the sending bank account's state, not transaction location. States with
  large migrant populations (UP, Bihar, Jharkhand) may be understated in local adoption.
- Per capita figures use Feb 2025 – Jan 2026 average (last 12 months of dataset).
- Growth trajectory compares May 2023 – Apr 2024 (Year 1) vs Feb 2025 – Jan 2026 (Year 2).
- UPI intensity = annual UPI value per capita / GSDP per capita × 100.
- GSDP FY2024-25 extrapolated via state-specific 5-year CAGR from MOSPI data.

Usage
-----
    python generate_dashboard.py                    # writes upi_dashboard.html
    python generate_dashboard.py --out my_file.html # custom output path
    python generate_dashboard.py --open             # open in browser after generating
    python generate_dashboard.py --embeds           # also generate 7 single-chart embed files
    python generate_dashboard.py --embeds-dir embeds/ --embeds  # custom embed output dir
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio


# ── Colour palette ─────────────────────────────────────────────────────────────
C = {
    "bg":      "#f5f2ed",
    "card":    "#fff",
    "border":  "#e8e3db",
    "dark":    "#1c2533",
    "mid":     "#4a5568",
    "lite":    "#8a9bb0",
    "red":     "#c8401a",
    "blue":    "#1d6fa4",
    "green":   "#1e7d52",
    "purple":  "#6b4c9a",
    "orange":  "#e8a87c",
    "slate":   "#94a3b8",
}

FONT_MONO = "DM Mono, monospace"
FONT_DISP = "Syne, sans-serif"

PLOTLY_CFG = {"responsive": True, "displayModeBar": False}

HIGH_INCOME_THRESHOLD_LAKH = 2.5  # GSDP per capita threshold for colour coding


# ══════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════

def get_per_capita_data() -> dict:
    """Per capita UPI transactions (Feb 2025 – Jan 2026 average) for all 34 states."""
    # [state_name, txns_per_capita, annual_spend_K_rs, rank]
    rows = [
        ("Bihar",               3.2,  57.0, 34),
        ("Tripura",             3.3,  53.5, 33),
        ("Meghalaya",           3.7,  60.5, 32),
        ("Chhattisgarh",        4.1,  64.1, 31),
        ("West Bengal",         4.2,  74.7, 29),
        ("Jharkhand",           4.2,  66.8, 29),
        ("Manipur",             4.2, 103.6, 29),
        ("Uttar Pradesh",       4.3,  68.3, 27),
        ("Jammu And Kashmir",   5.0,  79.2, 25),
        ("Madhya Pradesh",      5.0,  81.2, 25),
        ("Assam",               5.4,  72.8, 24),
        ("Odisha",              5.9,  92.0, 22),
        ("Nagaland",            5.9, 109.7, 22),
        ("Rajasthan",           6.3, 112.4, 21),
        ("Punjab",              6.4, 130.8, 20),
        ("Gujarat",             6.7, 120.9, 19),
        ("Himachal Pradesh",    7.3, 112.4, 18),
        ("Mizoram",             8.1, 148.8, 17),
        ("Tamil Nadu",          9.0, 164.4, 15),
        ("Uttarakhand",         9.0, 136.1, 15),
        ("Andaman & Nicobar",   9.4, 178.2, 14),
        ("Andhra Pradesh",     10.0, 206.0, 13),
        ("Puducherry",         10.6, 176.4, 12),
        ("Arunachal Pradesh",  10.8, 171.7, 11),
        ("Kerala",             11.0, 184.6, 10),
        ("Sikkim",             11.6, 186.2,  9),
        ("Ladakh",             12.0, 255.4,  8),
        ("Haryana",            12.3, 210.0,  7),
        ("Karnataka",          15.2, 250.7,  6),
        ("Maharashtra",        15.6, 220.8,  5),
        ("Telangana",          20.5, 388.0,  4),
        ("Chandigarh",         20.6, 310.6,  3),
        ("Goa",                21.4, 367.5,  2),
        ("Delhi",              22.5, 340.6,  1),
    ]
    states      = [r[0] for r in rows]
    txns        = [r[1] for r in rows]
    spend       = [r[2] for r in rows]
    ranks       = [r[3] for r in rows]

    # Colour: bottom 11 red, middle 11 purple, top 12 blue
    colours = (
        [C["red"]] * 11 +
        [C["purple"]] * 11 +
        [C["blue"]] * 12
    )

    return {"states": states, "txns": txns, "spend": spend,
            "ranks": ranks, "colours": colours}


def get_concentration_data() -> dict:
    """Top-5 states' share of national UPI value, monthly, May 2023 – Jan 2026."""
    months = [
        "May 2023","Jun 2023","Jul 2023","Aug 2023","Sep 2023","Oct 2023",
        "Nov 2023","Dec 2023","Jan 2024","Feb 2024","Mar 2024","Apr 2024",
        "May 2024","Jun 2024","Jul 2024","Aug 2024","Sep 2024","Oct 2024",
        "Nov 2024","Dec 2024","Jan 2025","Feb 2025","Mar 2025","Apr 2025",
        "May 2025","Jun 2025","Jul 2025","Aug 2025","Sep 2025","Oct 2025",
        "Nov 2025","Dec 2025","Jan 2026",
    ]
    share = [
        39.7,40.7,40.0,39.6,39.6,38.4,38.3,36.2,35.4,34.8,34.9,35.0,
        34.5,35.1,34.9,35.6,35.6,35.1,34.8,35.0,34.3,34.2,34.7,34.5,
        34.3,34.0,33.5,33.2,33.2,33.3,33.2,33.1,33.1,
    ]
    avg = round(sum(share) / len(share), 1)
    return {"months": months, "share": share, "avg": avg}


def get_growth_data() -> dict:
    """Year-on-year growth in avg monthly volume: Year1 (May 23–Apr 24) vs Year2 (Feb 25–Jan 26)."""
    # [state, status, y1_mn, y2_mn, pct_growth, abs_added_mn]
    rows = [
        ("Madhya Pradesh",    "Steady Growth",   491,  523,   6.5,  32),
        ("Maharashtra",       "Plateauing",      1935, 2122,  9.6, 187),
        ("Telangana",         "Steady Growth",    763,  842, 10.4,  79),
        ("Delhi",             "Steady Growth",    414,  484, 16.9,  70),
        ("Rajasthan",         "Steady Growth",    471,  556, 18.0,  85),
        ("Karnataka",         "Steady Growth",    951, 1125, 18.4, 175),
        ("Odisha",            "Steady Growth",    243,  296, 22.1,  54),
        ("Chandigarh",        "Steady Growth",     22,   27, 23.3,   5),
        ("Bihar",             "Accelerating",     349,  453, 30.0, 105),
        ("Uttarakhand",       "Accelerating",      87,  114, 30.8,  27),
        ("Chhattisgarh",      "Accelerating",     102,  137, 34.7,  35),
        ("Punjab",            "Accelerating",     153,  210, 37.5,  57),
        ("Haryana",           "Accelerating",     282,  395, 40.1, 113),
        ("Himachal Pradesh",  "Accelerating",      41,   59, 41.6,  17),
        ("Uttar Pradesh",     "Accelerating",     768, 1088, 41.7, 320),
        ("Goa",               "Accelerating",      24,   35, 41.8,  10),
        ("Andhra Pradesh",    "Accelerating",     396,  563, 42.2, 167),
        ("West Bengal",       "Accelerating",     317,  452, 42.7, 135),
        ("Tamil Nadu",        "Accelerating",     537,  785, 46.1, 248),
        ("Gujarat",           "Accelerating",     350,  513, 46.4, 162),
        ("Jharkhand",         "Accelerating",     121,  179, 47.1,  57),
        ("Puducherry",        "Accelerating",      12,   18, 49.3,   6),
        ("Kerala",            "Accelerating",     261,  391, 49.6, 130),
        ("Assam",             "Accelerating",     122,  205, 68.6,  84),
        ("Andaman & Nicobar", "Accelerating",       2,    4, 74.1,   2),
        ("Tripura",           "Accelerating",       8,   14, 79.4,   6),
        ("Ladakh",            "Accelerating",       2,    4, 80.2,   2),
        ("Sikkim",            "Accelerating",       4,    8, 91.5,   4),
        ("Arunachal Pradesh", "Accelerating",      10,   20, 96.7,  10),
        ("Nagaland",          "Accelerating",       6,   12, 99.5,   6),
        ("Jammu And Kashmir", "Accelerating",      41,   82,100.5,  41),
        ("Meghalaya",         "Accelerating",       7,   15,131.0,   9),
        ("Mizoram",           "Accelerating",       5,   12,132.1,   7),
        ("Manipur",           "Accelerating",       5,   14,213.5,  10),
    ]

    STATUS_COLOUR = {
        "Declining":    C["slate"],
        "Plateauing":   C["red"],
        "Steady Growth":C["blue"],
        "Accelerating": C["green"],
    }

    return {
        "states":  [r[0] for r in rows],
        "status":  [r[1] for r in rows],
        "y1":      [r[2] for r in rows],
        "y2":      [r[3] for r in rows],
        "pct":     [r[4] for r in rows],
        "added":   [r[5] for r in rows],
        "colours": [STATUS_COLOUR[r[1]] for r in rows],
    }


def get_archetype_data() -> list[dict]:
    """Market archetype scatter data (volume growth vs value growth, annualised)."""
    return [
        {
            "name":   "Mass Adoption",
            "colour": C["red"],
            "states": ["Assam", "West Bengal"],
            "x":      [33.0, 21.4],
            "y":      [14.5, 11.8],
        },
        {
            "name":   "Mature Markets",
            "colour": C["slate"],
            "states": [
                "Andhra Pradesh","Bihar","Chandigarh","Chhattisgarh","Delhi",
                "Haryana","Karnataka","Madhya Pradesh","Maharashtra","Odisha",
                "Punjab","Rajasthan","Telangana","Uttar Pradesh","Uttarakhand",
            ],
            "x":      [21.2,15.4,12.1,17.6, 8.9,20.2, 9.6,-2.8, 5.2,11.5,19.0, 9.5, 5.5,20.9,15.7],
            "y":      [12.5, 8.9, 7.8,13.6, 5.0,15.7, 8.4,-4.8,-2.5, 5.0,16.7, 6.0, 1.1,15.1,11.1],
        },
        {
            "name":   "Premiumisation",
            "colour": C["purple"],
            "states": ["Goa", "Himachal Pradesh"],
            "x":      [21.0, 20.9],
            "y":      [20.4, 17.4],
        },
        {
            "name":   "Scale Leaders",
            "colour": C["green"],
            "states": [
                "Andaman & Nicobar","Arunachal Pradesh","Gujarat","Jammu And Kashmir",
                "Jharkhand","Kerala","Ladakh","Manipur","Meghalaya","Mizoram",
                "Nagaland","Puducherry","Sikkim","Tamil Nadu","Tripura",
            ],
            "x":      [35.3,44.6,23.1,46.1,23.4,24.6,37.9,86.5,57.9,58.3,45.8,24.4,42.5,23.0,37.6],
            "y":      [23.5,27.4,17.5,36.6,18.3,21.6,22.8,57.1,36.8,30.9,18.4,21.0,24.4,18.0,23.1],
        },
    ]


def get_ticket_data() -> dict:
    """Average transaction size decline: early (May 23–Apr 24) vs recent (Feb 25–Jan 26)."""
    # [state, early_rs, recent_rs, decline_pct]
    rows = [
        ("Goa",               1438, 1423,  1.0),
        ("Punjab",            1730, 1710,  1.1),
        ("Karnataka",         1394, 1370,  1.8),
        ("Madhya Pradesh",    1371, 1342,  2.1),
        ("Rajasthan",         1545, 1501,  2.8),
        ("Himachal Pradesh",  1337, 1299,  2.9),
        ("Chhattisgarh",      1355, 1301,  4.0),
        ("Delhi",             1316, 1261,  4.2),
        ("Haryana",           1498, 1435,  4.2),
        ("Kerala",            1452, 1389,  4.3),
        ("Puducherry",        1447, 1384,  4.4),
        ("Chandigarh",        1329, 1266,  4.8),
        ("Uttarakhand",       1333, 1268,  4.9),
        ("Uttar Pradesh",     1414, 1343,  5.0),
        ("Jharkhand",         1414, 1342,  5.1),
        ("Gujarat",           1598, 1508,  5.6),
        ("Telangana",         1676, 1576,  6.0),
        ("Tamil Nadu",        1625, 1521,  6.4),
        ("Bihar",             1590, 1474,  7.3),
        ("Odisha",            1404, 1292,  8.0),
        ("Jammu And Kashmir", 1483, 1362,  8.2),
        ("West Bengal",       1693, 1511, 10.8),
        ("Andhra Pradesh",    1941, 1730, 10.8),
        ("Maharashtra",       1346, 1196, 11.1),
        ("Andaman & Nicobar", 1819, 1601, 12.0),
        ("Tripura",           1605, 1386, 13.7),
        ("Ladakh",            2148, 1829, 14.9),
        ("Arunachal Pradesh", 1606, 1343, 16.4),
        ("Sikkim",            1654, 1370, 17.2),
        ("Meghalaya",         1685, 1391, 17.4),
        ("Assam",             1409, 1147, 18.6),
        ("Manipur",           2727, 2140, 21.5),
        ("Mizoram",           2081, 1585, 23.8),
        ("Nagaland",          2151, 1617, 24.8),
    ]
    colours = (
        [C["green"]]  * 13 +
        [C["orange"]] *  8 +
        [C["red"]]    * 13
    )
    return {
        "states":  [r[0] for r in rows],
        "early":   [r[1] for r in rows],
        "recent":  [r[2] for r in rows],
        "decline": [r[3] for r in rows],
        "colours": colours,
    }


def get_intensity_data() -> dict:
    """
    UPI adoption vs economic development scatter.

    Colour logic (based on 45° diagonal analysis):
    - Green (#1e7d52):  UPI value per capita > GSDP per capita (above diagonal — over-indexed)
    - Red (#c8401a):    GSDP >= 2.5L but UPI value < GSDP (high income, under-digitised)
    - Grey (#8a9bb0):   GSDP <  2.5L and UPI value < GSDP (low income, expected low adoption)
    """
    # [state, gsdp_lakh, upi_val_lakh, txns_per_month, intensity_pct]
    rows = [
        ("Bihar",               0.55, 0.57,  3.2, 103.7),
        ("Uttar Pradesh",       1.02, 0.68,  4.3,  66.9),
        ("Assam",               1.20, 0.73,  5.4,  60.6),
        ("Jharkhand",           1.32, 0.67,  4.2,  50.6),
        ("Manipur",             1.38, 1.04,  4.2,  75.0),
        ("Meghalaya",           1.42, 0.61,  3.7,  42.6),
        ("Jammu And Kashmir",   1.45, 0.79,  5.0,  54.6),
        ("Tripura",             1.48, 0.53,  3.3,  36.1),
        ("Chhattisgarh",        1.50, 0.64,  4.1,  42.7),
        ("Madhya Pradesh",      1.54, 0.81,  5.0,  52.8),
        ("Nagaland",            1.58, 1.10,  5.9,  69.4),
        ("West Bengal",         1.58, 0.75,  4.2,  47.3),
        ("Rajasthan",           1.68, 1.12,  6.3,  66.9),
        ("Odisha",              1.68, 0.92,  5.9,  54.7),
        ("Andhra Pradesh",      2.05, 2.06, 10.0, 100.5),
        ("Mizoram",             2.10, 1.49,  8.1,  70.9),
        ("Ladakh",              2.15, 2.55, 12.0, 118.8),
        ("Punjab",              2.22, 1.31,  6.4,  58.9),
        ("Himachal Pradesh",    2.28, 1.12,  7.3,  49.3),
        ("Arunachal Pradesh",   2.31, 1.72, 10.8,  74.3),
        ("Uttarakhand",         2.36, 1.36,  9.0,  57.7),
        ("Tamil Nadu",          2.40, 1.64,  9.0,  68.5),
        ("Maharashtra",         2.56, 2.21, 15.6,  86.3),
        ("Kerala",              2.62, 1.85, 11.0,  70.4),
        ("Puducherry",          2.64, 1.76, 10.6,  66.8),
        ("Karnataka",           2.68, 2.51, 15.2,  93.5),
        ("Gujarat",             2.75, 1.21,  6.7,  44.0),
        ("Andaman & Nicobar",   2.85, 1.78,  9.4,  62.5),
        ("Telangana",           2.89, 3.88, 20.5, 134.3),
        ("Haryana",             2.94, 2.10, 12.3,  71.4),
        ("Chandigarh",          3.68, 3.11, 20.6,  84.4),
        ("Sikkim",              4.50, 1.86, 11.6,  41.4),
        ("Delhi",               4.82, 3.41, 22.5,  70.7),
        ("Goa",                 5.01, 3.67, 21.4,  73.3),
    ]

    def _colour(gsdp: float, upi: float) -> str:
        if upi > gsdp:
            return C["green"]
        if gsdp >= HIGH_INCOME_THRESHOLD_LAKH:
            return C["red"]
        return C["slate"]

    return {
        "states":    [r[0] for r in rows],
        "gsdp":      [r[1] for r in rows],
        "upi_val":   [r[2] for r in rows],
        "txns":      [r[3] for r in rows],
        "intensity": [r[4] for r in rows],
        "colours":   [_colour(r[1], r[2]) for r in rows],
    }


def get_map_data() -> list[dict]:
    """State data for choropleth map."""
    return [
        {"state": "DELHI",              "state_title": "Delhi",              "txns_per_capita": 22.5, "val_per_capita_yr": 340598, "rank":  1, "growth_type": "Steady Growth"},
        {"state": "GOA",                "state_title": "Goa",                "txns_per_capita": 21.4, "val_per_capita_yr": 367475, "rank":  2, "growth_type": "Accelerating"},
        {"state": "CHANDIGARH",         "state_title": "Chandigarh",         "txns_per_capita": 20.6, "val_per_capita_yr": 310648, "rank":  3, "growth_type": "Steady Growth"},
        {"state": "TELANGANA",          "state_title": "Telangana",          "txns_per_capita": 20.5, "val_per_capita_yr": 387986, "rank":  4, "growth_type": "Steady Growth"},
        {"state": "MAHARASHTRA",        "state_title": "Maharashtra",        "txns_per_capita": 15.6, "val_per_capita_yr": 220842, "rank":  5, "growth_type": "Plateauing"},
        {"state": "KARNATAKA",          "state_title": "Karnataka",          "txns_per_capita": 15.2, "val_per_capita_yr": 250661, "rank":  6, "growth_type": "Steady Growth"},
        {"state": "HARYANA",            "state_title": "Haryana",            "txns_per_capita": 12.3, "val_per_capita_yr": 210025, "rank":  7, "growth_type": "Accelerating"},
        {"state": "LADAKH",             "state_title": "Ladakh",             "txns_per_capita": 12.0, "val_per_capita_yr": 255368, "rank":  8, "growth_type": "Accelerating"},
        {"state": "SIKKIM",             "state_title": "Sikkim",             "txns_per_capita": 11.6, "val_per_capita_yr": 186250, "rank":  9, "growth_type": "Accelerating"},
        {"state": "KERALA",             "state_title": "Kerala",             "txns_per_capita": 11.0, "val_per_capita_yr": 184565, "rank": 10, "growth_type": "Accelerating"},
        {"state": "ARUNACHAL PRADESH",  "state_title": "Arunachal Pradesh",  "txns_per_capita": 10.8, "val_per_capita_yr": 171741, "rank": 11, "growth_type": "Accelerating"},
        {"state": "PUDUCHERRY",         "state_title": "Puducherry",         "txns_per_capita": 10.6, "val_per_capita_yr": 176437, "rank": 12, "growth_type": "Accelerating"},
        {"state": "ANDHRA PRADESH",     "state_title": "Andhra Pradesh",     "txns_per_capita": 10.0, "val_per_capita_yr": 206012, "rank": 13, "growth_type": "Accelerating"},
        {"state": "ANDAMAN & NICOBAR",  "state_title": "Andaman & Nicobar",  "txns_per_capita":  9.4, "val_per_capita_yr": 178201, "rank": 14, "growth_type": "Accelerating"},
        {"state": "TAMIL NADU",         "state_title": "Tamil Nadu",         "txns_per_capita":  9.0, "val_per_capita_yr": 164394, "rank": 15, "growth_type": "Accelerating"},
        {"state": "UTTARAKHAND",        "state_title": "Uttarakhand",        "txns_per_capita":  9.0, "val_per_capita_yr": 136141, "rank": 15, "growth_type": "Accelerating"},
        {"state": "MIZORAM",            "state_title": "Mizoram",            "txns_per_capita":  8.1, "val_per_capita_yr": 148797, "rank": 17, "growth_type": "Accelerating"},
        {"state": "HIMACHAL PRADESH",   "state_title": "Himachal Pradesh",   "txns_per_capita":  7.3, "val_per_capita_yr": 112443, "rank": 18, "growth_type": "Accelerating"},
        {"state": "GUJARAT",            "state_title": "Gujarat",            "txns_per_capita":  6.7, "val_per_capita_yr": 120941, "rank": 19, "growth_type": "Accelerating"},
        {"state": "PUNJAB",             "state_title": "Punjab",             "txns_per_capita":  6.4, "val_per_capita_yr": 130799, "rank": 20, "growth_type": "Accelerating"},
        {"state": "RAJASTHAN",          "state_title": "Rajasthan",          "txns_per_capita":  6.3, "val_per_capita_yr": 112396, "rank": 21, "growth_type": "Steady Growth"},
        {"state": "NAGALAND",           "state_title": "Nagaland",           "txns_per_capita":  5.9, "val_per_capita_yr": 109664, "rank": 22, "growth_type": "Accelerating"},
        {"state": "ODISHA",             "state_title": "Odisha",             "txns_per_capita":  5.9, "val_per_capita_yr":  91954, "rank": 22, "growth_type": "Steady Growth"},
        {"state": "ASSAM",              "state_title": "Assam",              "txns_per_capita":  5.4, "val_per_capita_yr":  72763, "rank": 24, "growth_type": "Accelerating"},
        {"state": "MADHYA PRADESH",     "state_title": "Madhya Pradesh",     "txns_per_capita":  5.0, "val_per_capita_yr":  81244, "rank": 25, "growth_type": "Declining"},
        {"state": "JAMMU AND KASHMIR",  "state_title": "Jammu And Kashmir",  "txns_per_capita":  5.0, "val_per_capita_yr":  79189, "rank": 25, "growth_type": "Accelerating"},
        {"state": "UTTAR PRADESH",      "state_title": "Uttar Pradesh",      "txns_per_capita":  4.3, "val_per_capita_yr":  68257, "rank": 27, "growth_type": "Accelerating"},
        {"state": "MANIPUR",            "state_title": "Manipur",            "txns_per_capita":  4.2, "val_per_capita_yr": 103563, "rank": 29, "growth_type": "Accelerating"},
        {"state": "JHARKHAND",          "state_title": "Jharkhand",          "txns_per_capita":  4.2, "val_per_capita_yr":  66772, "rank": 29, "growth_type": "Accelerating"},
        {"state": "WEST BENGAL",        "state_title": "West Bengal",        "txns_per_capita":  4.2, "val_per_capita_yr":  74707, "rank": 29, "growth_type": "Accelerating"},
        {"state": "CHHATTISGARH",       "state_title": "Chhattisgarh",       "txns_per_capita":  4.1, "val_per_capita_yr":  64051, "rank": 31, "growth_type": "Accelerating"},
        {"state": "MEGHALAYA",          "state_title": "Meghalaya",          "txns_per_capita":  3.7, "val_per_capita_yr":  60519, "rank": 32, "growth_type": "Accelerating"},
        {"state": "TRIPURA",            "state_title": "Tripura",            "txns_per_capita":  3.3, "val_per_capita_yr":  53491, "rank": 33, "growth_type": "Accelerating"},
        {"state": "BIHAR",              "state_title": "Bihar",              "txns_per_capita":  3.2, "val_per_capita_yr":  57028, "rank": 34, "growth_type": "Accelerating"},
    ]


# ══════════════════════════════════════════════════════════════════════════════
# CHART BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def _base_layout(**kwargs) -> dict:
    """Base Plotly layout shared across all charts."""
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_MONO, color=C["dark"], size=11),
        hoverlabel=dict(
            bgcolor=C["dark"],
            bordercolor=C["blue"],
            font=dict(family=FONT_MONO, color="#fff", size=11),
        ),
    )
    base.update(kwargs)
    return base


def build_pc_bar(d: dict) -> dict:
    fig = go.Figure(go.Bar(
        x=d["txns"],
        y=d["states"],
        orientation="h",
        marker=dict(color=d["colours"], line=dict(width=0)),
        customdata=list(zip(d["states"], d["txns"], d["spend"], d["ranks"])),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Transactions per person per month: %{customdata[1]}<br>"
            "Annual UPI spend per person: Rs %{customdata[2]}K<br>"
            "Rank: #%{customdata[3]} of 34<extra></extra>"
        ),
    ))
    fig.update_layout(_base_layout(
        height=740,
        bargap=0.2,
        margin=dict(l=180, r=60, t=56, b=40),
        title=dict(
            text=(
                "How many UPI transactions does the average person make each month?<br>"
                "<sup style='font-size:10px;color:#8a9bb0'>"
                "Based on Feb 2025 – Jan 2026 · Population: Census 2011 projected to 2024"
                "</sup>"
            ),
            font=dict(family=FONT_DISP, size=13, color=C["dark"]),
            x=0,
        ),
        xaxis=dict(
            title=dict(text="Transactions per person per month",
                       font=dict(color=C["lite"], size=10)),
            tickfont=dict(color=C["mid"], size=9),
            gridcolor=C["border"],
            zeroline=False,
        ),
        yaxis=dict(
            tickfont=dict(color=C["dark"], size=9),
            gridcolor="rgba(0,0,0,0)",
            automargin=False,
            autorange=True,
        ),
    ))
    return json.loads(pio.to_json(fig))


def build_concentration(d: dict) -> dict:
    fig = go.Figure(go.Scatter(
        x=d["months"],
        y=d["share"],
        mode="lines+markers",
        line=dict(color=C["blue"], width=2.5, shape="spline"),
        marker=dict(color=C["blue"], size=6, line=dict(color="#fff", width=2)),
        fill="tozeroy",
        fillcolor="rgba(29,111,164,0.09)",
        hovertemplate="<b>%{x}</b><br>Top 5 states' share: %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(_base_layout(
        height=460,
        showlegend=False,
        margin=dict(l=16, r=70, t=64, b=110),
        title=dict(
            text=(
                "Are smaller states catching up to the big five?<br>"
                "<sup style='font-size:10px;color:#8a9bb0'>"
                "Share of national UPI value held by the top 5 states each month "
                "· May 2023 – Jan 2026"
                "</sup>"
            ),
            font=dict(family=FONT_DISP, size=13, color=C["dark"]),
            x=0,
        ),
        xaxis=dict(
            type="category",
            tickfont=dict(color=C["lite"], size=9),
            gridcolor=C["border"],
            tickangle=-45,
            zeroline=False,
            tickvals=["May 2023","Aug 2023","Nov 2023","Feb 2024","May 2024",
                      "Aug 2024","Nov 2024","Feb 2025","May 2025","Aug 2025","Nov 2025"],
        ),
        yaxis=dict(
            title=dict(text="% of national UPI value",
                       font=dict(color=C["lite"], size=10)),
            tickfont=dict(color=C["mid"]),
            gridcolor=C["border"],
            zeroline=False,
            range=[28, 44],
        ),
        annotations=[
            dict(text="39.7%", x="May 2023", y=40.5, showarrow=False,
                 font=dict(size=11, color=C["red"], family=FONT_DISP)),
            dict(text="33.1%", x="Jan 2026", y=31.9, showarrow=False,
                 font=dict(size=11, color=C["green"], family=FONT_DISP)),
            dict(text=f"Average {d['avg']}%", x=1, xanchor="right",
                 xref="x domain", y=d["avg"], yanchor="top", yref="y",
                 showarrow=False, font=dict(size=9, color=C["lite"])),
        ],
        shapes=[dict(
            type="line", x0=0, x1=1, xref="x domain",
            y0=d["avg"], y1=d["avg"], yref="y",
            line=dict(color=C["border"], dash="dot", width=1.5),
        )],
    ))
    return json.loads(pio.to_json(fig))


def build_intensity_scatter(d: dict) -> dict:
    max_val = max(max(d["gsdp"]), max(d["upi_val"])) * 1.08
    fig = go.Figure(go.Scatter(
        x=d["gsdp"],
        y=d["upi_val"],
        mode="markers+text",
        text=d["states"],
        textposition="top center",
        textfont=dict(size=7.5, color=C["mid"], family=FONT_MONO),
        marker=dict(
            color=d["colours"],
            size=11,
            line=dict(color="#fff", width=1.5),
            opacity=0.9,
        ),
        customdata=list(zip(
            d["states"], d["gsdp"], d["upi_val"], d["txns"], d["intensity"]
        )),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "GSDP per capita: ₹%{customdata[1]:.2f}L<br>"
            "Annual UPI value per capita: ₹%{customdata[2]:.2f}L<br>"
            "UPI Intensity (val/GSDP): %{customdata[4]:.1f}%<br>"
            "Txns per person/month: %{customdata[3]}<extra></extra>"
        ),
        name="",
    ))
    fig.update_layout(_base_layout(
        height=580,
        showlegend=False,
        margin=dict(l=60, r=40, t=80, b=80),
        title=dict(
            text=(
                "UPI adoption vs economic development — is digitisation tracking income?<br>"
                "<sup style='font-size:10px;color:#8a9bb0'>"
                "Annual UPI value per capita (Rs Lakh) vs GSDP per capita (Rs Lakh) "
                "· Feb 2025 – Jan 2026"
                "</sup>"
            ),
            font=dict(family=FONT_DISP, size=13, color=C["dark"]),
            x=0,
        ),
        xaxis=dict(
            title=dict(text="GSDP per capita (Rs Lakh, FY2024-25 est.)",
                       font=dict(color=C["lite"], size=10)),
            gridcolor=C["border"],
            tickfont=dict(color=C["mid"]),
            zeroline=False,
            tickprefix="₹",
            ticksuffix="L",
        ),
        yaxis=dict(
            title=dict(text="Annual UPI value per capita (Rs Lakh)",
                       font=dict(color=C["lite"], size=10)),
            gridcolor=C["border"],
            tickfont=dict(color=C["mid"]),
            zeroline=False,
            tickprefix="₹",
            ticksuffix="L",
        ),
        shapes=[
            # 45° diagonal
            dict(type="line", x0=0, y0=0, x1=max_val, y1=max_val,
                 line=dict(color=C["border"], dash="dot", width=1.5)),
            # Income threshold vertical
            dict(type="line", x0=HIGH_INCOME_THRESHOLD_LAKH, x1=HIGH_INCOME_THRESHOLD_LAKH,
                 y0=0, y1=1, xref="x", yref="paper",
                 line=dict(color=C["border"], dash="dot", width=1)),
            # Adoption threshold horizontal
            dict(type="line", x0=0, x1=1, y0=1.5, y1=1.5, xref="paper", yref="y",
                 line=dict(color=C["border"], dash="dot", width=1)),
        ],
        annotations=[
            dict(x=max_val * 0.95, y=max_val * 0.92,
                 text="45° line = UPI intensity 100%",
                 showarrow=False, font=dict(color=C["lite"], size=9),
                 xanchor="right"),
            dict(x=4.5, y=3.6, text="HIGH INCOME · HIGH ADOPTION",
                 showarrow=False,
                 font=dict(color=C["lite"], family=FONT_MONO, size=8),
                 xanchor="right"),
            dict(x=0.6, y=0.45, text="LOW INCOME · LOW ADOPTION",
                 showarrow=False,
                 font=dict(color=C["lite"], family=FONT_MONO, size=8),
                 xanchor="left"),
            dict(x=4.5, y=0.35, text="HIGH INCOME · UNDER-DIGITISED",
                 showarrow=False,
                 font=dict(color=C["red"], family=FONT_MONO, size=8),
                 xanchor="right"),
            dict(x=2.9, y=3.5, text="ABOVE DIAGONAL · OVER-INDEXED",
                 showarrow=False,
                 font=dict(color=C["green"], family=FONT_MONO, size=8),
                 xanchor="left"),
        ],
    ))
    return json.loads(pio.to_json(fig))


def build_growth_bar(d: dict) -> dict:
    fig = go.Figure(go.Bar(
        x=d["pct"],
        y=d["states"],
        orientation="h",
        marker=dict(color=d["colours"], line=dict(width=0)),
        customdata=list(zip(
            d["states"], d["status"], d["y1"], d["y2"], d["pct"], d["added"]
        )),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Status: %{customdata[1]}<br>"
            "Year 1 avg: %{customdata[2]:.0f} Mn transactions/month<br>"
            "Year 2 avg: %{customdata[3]:.0f} Mn transactions/month<br>"
            "Growth rate: %{customdata[4]:.1f}%<br>"
            "Absolute volume added: %{customdata[5]:.0f} Mn txns/month<extra></extra>"
        ),
    ))
    fig.update_layout(_base_layout(
        height=740,
        bargap=0.2,
        margin=dict(l=180, r=80, t=80, b=40),
        title=dict(
            text=(
                "Which states grew fastest? — Year-on-Year Growth Rate<br>"
                "<sup style='font-size:10px;color:#8a9bb0'>"
                "% change in avg monthly transactions: May 2023 – Apr 2024 vs "
                "Feb 2025 – Jan 2026 · Hover for absolute volumes"
                "</sup>"
            ),
            font=dict(family=FONT_DISP, size=13, color=C["dark"]),
            x=0,
        ),
        xaxis=dict(
            title=dict(text="% change in avg monthly transactions (Year 2 vs Year 1)",
                       font=dict(color=C["lite"], size=10)),
            tickfont=dict(color=C["mid"], size=9),
            gridcolor=C["border"],
            zeroline=True,
            zerolinecolor=C["border"],
            zerolinewidth=1.5,
            ticksuffix="%",
        ),
        yaxis=dict(
            tickfont=dict(color=C["dark"], size=9),
            gridcolor="rgba(0,0,0,0)",
            automargin=True,
            autorange=True,
        ),
        shapes=[dict(
            type="line", x0=0, x1=0, xref="x", y0=0, y1=1, yref="y domain",
            line=dict(color=C["border"], width=1.5),
        )],
    ))
    return json.loads(pio.to_json(fig))


def build_archetype_scatter(data: list[dict]) -> dict:
    fig = go.Figure()
    for grp in data:
        fig.add_trace(go.Scatter(
            x=grp["x"],
            y=grp["y"],
            mode="markers+text",
            name=grp["name"],
            text=grp["states"],
            textposition="top center",
            textfont=dict(color=C["mid"], family=FONT_MONO, size=7.5),
            marker=dict(
                color=grp["colour"],
                size=11,
                line=dict(color="#fff", width=1.5),
                opacity=0.9,
            ),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Volume growth: %{x:.1f}% per year<br>"
                "Value growth: %{y:.1f}% per year<extra></extra>"
            ),
        ))
    fig.update_layout(_base_layout(
        height=560,
        margin=dict(l=60, r=40, t=80, b=100),
        title=dict(
            text=(
                "Are states growing in number of transactions, total value, or both?<br>"
                "<sup style='font-size:10px;color:#8a9bb0'>"
                "Annualised growth rate using 12-month smoothed averages "
                "· May 2023 – Jan 2026"
                "</sup>"
            ),
            font=dict(family=FONT_DISP, size=13, color=C["dark"]),
            x=0,
        ),
        xaxis=dict(
            title=dict(text="Annual transaction volume growth (%)",
                       font=dict(color=C["lite"], size=10)),
            tickfont=dict(color=C["mid"]),
            gridcolor=C["border"],
            zeroline=False,
            range=[0, 94.5],
        ),
        yaxis=dict(
            title=dict(text="Annual transaction value growth (%)",
                       font=dict(color=C["lite"], size=10)),
            tickfont=dict(color=C["mid"]),
            gridcolor=C["border"],
            zeroline=False,
            range=[0, 65.1],
        ),
        legend=dict(
            font=dict(color=C["mid"], size=10),
            bgcolor="rgba(0,0,0,0)",
            bordercolor=C["border"],
            orientation="h",
            y=-0.18,
            x=0,
        ),
        shapes=[
            dict(type="rect", layer="below", line=dict(width=0),
                 fillcolor="rgba(30,125,82,0.06)",
                 x0=21.3, x1=94.5, y0=17.0, y1=65.1),
            dict(type="rect", layer="below", line=dict(width=0),
                 fillcolor="rgba(148,163,184,0.06)",
                 x0=0, x1=21.3, y0=0, y1=17.0),
            dict(type="rect", layer="below", line=dict(width=0),
                 fillcolor="rgba(200,64,26,0.06)",
                 x0=21.3, x1=94.5, y0=0, y1=17.0),
            dict(type="rect", layer="below", line=dict(width=0),
                 fillcolor="rgba(107,76,154,0.06)",
                 x0=0, x1=21.3, y0=17.0, y1=65.1),
            dict(type="line", x0=0, x1=1, xref="x domain",
                 y0=17.0, y1=17.0, yref="y",
                 line=dict(color=C["border"], dash="dot", width=1.5)),
            dict(type="line", x0=21.3, x1=21.3, xref="x",
                 y0=0, y1=1, yref="y domain",
                 line=dict(color=C["border"], dash="dot", width=1.5)),
        ],
        annotations=[
            dict(text="SCALE LEADERS",    x=22.3, xanchor="left", y=63.1, yanchor="top",
                 showarrow=False, font=dict(size=8, color=C["lite"], family=FONT_MONO)),
            dict(text="MATURE MARKETS",   x=1,    xanchor="left", y=16.0, yanchor="top",
                 showarrow=False, font=dict(size=8, color=C["lite"], family=FONT_MONO)),
            dict(text="MASS ADOPTION",    x=22.3, xanchor="left", y=16.0, yanchor="top",
                 showarrow=False, font=dict(size=8, color=C["lite"], family=FONT_MONO)),
            dict(text="PREMIUMISATION",   x=1,    xanchor="left", y=63.1, yanchor="top",
                 showarrow=False, font=dict(size=8, color=C["lite"], family=FONT_MONO)),
        ],
    ))
    return json.loads(pio.to_json(fig))


def build_ticket_bar(d: dict) -> dict:
    fig = go.Figure(go.Bar(
        x=d["decline"],
        y=d["states"],
        orientation="h",
        marker=dict(color=d["colours"], line=dict(width=0)),
        customdata=list(zip(d["states"], d["early"], d["recent"], d["decline"])),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Early period avg: Rs %{customdata[1]:,} per transaction<br>"
            "Recent period avg: Rs %{customdata[2]:,} per transaction<br>"
            "Decline: %{customdata[3]:.1f}%<extra></extra>"
        ),
    ))
    fig.update_layout(_base_layout(
        height=720,
        bargap=0.2,
        margin=dict(l=180, r=80, t=80, b=40),
        title=dict(
            text=(
                "By how much has the average transaction size fallen?<br>"
                "<sup style='font-size:10px;color:#8a9bb0'>"
                "All 34 states recorded a decline · Red = largest fall "
                "(most new small-ticket users) · Green = smallest fall"
                "</sup>"
            ),
            font=dict(family=FONT_DISP, size=13, color=C["dark"]),
            x=0,
        ),
        xaxis=dict(
            title=dict(text="% decline in average transaction size",
                       font=dict(color=C["lite"], size=10)),
            tickfont=dict(color=C["mid"], size=9),
            gridcolor=C["border"],
            zeroline=False,
            ticksuffix="%",
        ),
        yaxis=dict(
            tickfont=dict(color=C["dark"], size=9),
            gridcolor="rgba(0,0,0,0)",
            automargin=True,
            autorange=True,
        ),
    ))
    return json.loads(pio.to_json(fig))


# ══════════════════════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>India UPI — State-Level Digitisation Analysis</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f5f2ed;--card:#fff;--bdr:#e8e3db;
  --dark:#1c2533;--mid:#4a5568;--lite:#8a9bb0;
  --a1:#1d6fa4;--a2:#c8401a;--a3:#1e7d52;--a4:#6b4c9a;
}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--dark);
  font-family:'DM Mono',monospace;font-size:13px;line-height:1.6}
.caveat-bar{background:#fffbf0;border-bottom:1px solid #f0e6c8;
  padding:8px 36px;font-size:10px;color:#7a6a45;
  display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.nav{background:#1c2533;height:54px;display:flex;align-items:center;
  justify-content:space-between;padding:0 36px;position:sticky;top:0;z-index:200}
.nav-brand{font-family:'Syne',sans-serif;font-size:14px;font-weight:700;color:#fff}
.nav-brand em{font-style:normal;color:#4aadde}
.nav-right{font-size:10px;color:rgba(255,255,255,.35);letter-spacing:.3px}
.wrap{max-width:1320px;margin:0 auto;padding:0 32px 80px}
.hero{padding:52px 0 40px;border-bottom:1px solid var(--bdr);margin-bottom:40px}
.hero-eye{font-size:10px;letter-spacing:3px;text-transform:uppercase;
  color:var(--a1);margin-bottom:14px}
.hero h1{font-family:'Syne',sans-serif;font-size:clamp(28px,5vw,50px);
  font-weight:800;line-height:1.05;letter-spacing:-1.5px;max-width:820px}
.hero h1 em{font-style:normal;color:var(--a1)}
.hero-sub{margin-top:16px;font-size:12px;color:var(--mid);
  max-width:580px;line-height:1.85}
.hero-meta{margin-top:10px;font-size:10px;color:var(--lite)}
.kpi-row{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:40px}
@media(max-width:1000px){.kpi-row{grid-template-columns:repeat(3,1fr)}}
@media(max-width:580px){.kpi-row{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--card);border:1px solid var(--bdr);border-radius:12px;
  padding:18px 20px;position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.kpi:nth-child(1)::before{background:var(--a1)}
.kpi:nth-child(2)::before{background:var(--a2)}
.kpi:nth-child(3)::before{background:var(--a3)}
.kpi:nth-child(4)::before{background:var(--a4)}
.kpi:nth-child(5)::before{background:#e8a87c}
.kpi:nth-child(6)::before{background:#64748b}
.kpi-lbl{font-size:9px;letter-spacing:2px;text-transform:uppercase;
  color:var(--lite);margin-bottom:8px}
.kpi-val{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;line-height:1}
.kpi-sub{font-size:10px;color:var(--lite);margin-top:6px}
.ins-row{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:48px}
@media(max-width:700px){.ins-row{grid-template-columns:1fr}}
.ins{background:var(--card);border:1px solid var(--bdr);
  border-left:3px solid var(--a1);border-radius:12px;padding:20px 22px}
.ins:nth-child(2){border-left-color:var(--a2)}
.ins:nth-child(3){border-left-color:var(--a3)}
.ins-num{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;margin-bottom:6px}
.ins-ttl{font-family:'Syne',sans-serif;font-size:13px;font-weight:700;margin-bottom:7px}
.ins-body{font-size:11px;color:var(--mid);line-height:1.8}
.tab-bar{display:flex;border-bottom:2px solid var(--bdr);margin-bottom:36px;
  position:sticky;top:54px;background:var(--bg);z-index:100;padding-top:12px}
.tab-btn{padding:10px 26px;font-family:'Syne',sans-serif;font-size:12px;
  font-weight:700;color:var(--lite);border:none;background:none;cursor:pointer;
  border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s}
.tab-btn:hover{color:var(--dark)}
.tab-btn.active{color:var(--dark);border-bottom-color:var(--dark)}
.tab-eye{font-size:8px;letter-spacing:2px;text-transform:uppercase;
  display:block;margin-bottom:3px;opacity:.5}
.tab-panel{display:none}.tab-panel.active{display:block}
.pull{background:#1c2533;color:#fff;border-radius:14px;
  padding:24px 32px;margin-bottom:32px;
  display:flex;align-items:flex-start;gap:22px}
.pull-stat{font-family:'Syne',sans-serif;font-size:38px;font-weight:800;
  line-height:1;flex-shrink:0;white-space:nowrap}
.pull-body{font-size:12px;color:rgba(255,255,255,.65);line-height:1.85;padding-top:3px}
.pull-body strong{color:#fff;font-family:'Syne',sans-serif}
.pull-body em{font-style:italic}
.sec{margin-bottom:40px}
.sec-eye{font-size:9px;letter-spacing:3px;text-transform:uppercase;
  color:var(--lite);margin-bottom:5px}
.sec-ttl{font-family:'Syne',sans-serif;font-size:18px;font-weight:700;margin-bottom:5px}
.sec-desc{font-size:11px;color:var(--mid);max-width:720px;line-height:1.8;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--bdr);
  border-radius:14px;overflow:hidden;padding:4px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.full{width:100%}
.mt16{margin-top:16px}.mt32{margin-top:32px}
@media(max-width:860px){.two{grid-template-columns:1fr}}
.legend-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.leg{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--mid);
  padding:4px 12px;border:1px solid var(--bdr);border-radius:20px;background:var(--card)}
.leg-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.map-wrap{position:relative;border-radius:14px;overflow:hidden;
  background:var(--card);border:1px solid var(--bdr);min-height:650px;
  display:flex;flex-direction:column}
#map-msg{display:flex;flex-direction:column;align-items:center;
  justify-content:center;flex:1;font-size:11px;color:var(--lite);
  text-align:center;padding:24px}
#choropleth{flex:1}
.state-bar{display:flex;align-items:center;gap:14px;margin-bottom:18px;flex-wrap:wrap}
.state-lbl{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--lite)}
.state-sel{padding:9px 16px;font-family:'DM Mono',monospace;font-size:11px;
  border:1px solid var(--bdr);border-radius:8px;background:var(--card);
  color:var(--dark);cursor:pointer;min-width:240px;outline:none}
.state-sel:focus{border-color:var(--a1)}
.ts-stack{display:flex;flex-direction:column;gap:10px}
footer{margin-top:64px;padding-top:24px;border-top:1px solid var(--bdr);
  font-size:10px;color:var(--lite);line-height:2}
footer strong{color:var(--mid)}
</style>
</head>
<body>

<div class="caveat-bar">
  <span>⚠ ~30% of national UPI volume is unclassified by NPCI and excluded from state totals — state shares are indicative, not exhaustive.</span>
  <span style="margin-left:24px">Population denominator: Census 2011 projected to 2024 — treat small-state per capita figures with caution.</span>
</div>

<nav class="nav">
  <div class="nav-brand">India <em>UPI</em> — State-Level Digitisation Analysis</div>
  <div class="nav-right">NPCI · MOSPI · Census 2011 (proj.) · <strong style="color:rgba(255,255,255,.6)">Data through Jan 2026</strong></div>
</nav>

<div class="wrap">

<header class="hero">
  <div class="hero-eye">State-Level Fintech Intelligence · 34 States · 33 Months</div>
  <h1>UPI Digitisation in India:<br><em>A State-Level Analysis</em></h1>
  <p class="hero-sub">
    Aggregate UPI volume numbers obscure a structural divide. Once you control for population, Bihar, a state that generates over 450 million UPI transactions a month, still ranks dead last on per capita usage. Volume conceals depth. Growth has continued across most states, but the rate of expansion is slowing, and the per capita gap between states remains very large.
  </p>
  <div class="hero-meta">
    NPCI Ecosystem Statistics · MOSPI National Accounts ·
    Population: Census 2011 projected to 2024 · May 2023 – Jan 2026
  </div>
</header>

<div class="kpi-row">
  <div class="kpi">
    <div class="kpi-lbl">Monthly UPI Value</div>
    <div class="kpi-val">Rs 28.3L Cr</div>
    <div class="kpi-sub">January 2026 · national total</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">Monthly Transactions</div>
    <div class="kpi-val">21.7Bn</div>
    <div class="kpi-sub">January 2026 · national total</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">Avg Transaction Size</div>
    <div class="kpi-val">Rs 1,306</div>
    <div class="kpi-sub">Period average · all states · declining</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">Top 5 States Share ↓</div>
    <div class="kpi-val">-6.6pp</div>
    <div class="kpi-sub">Change over 33 months</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">High-Growth States</div>
    <div class="kpi-val">26/34</div>
    <div class="kpi-sub">&gt;30% growth · 32/34 growing at all</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">Per Capita Gap</div>
    <div class="kpi-val">7×</div>
    <div class="kpi-sub">Delhi vs Bihar · txns per person</div>
  </div>
</div>

<div class="ins-row">
  <div class="ins">
    <div class="ins-num" style="color:var(--a1)">7× divide</div>
    <div class="ins-ttl">Size Hides the Depth Gap</div>
    <div class="ins-body">
      Delhi makes 22.5 UPI transactions per person per month.
      Bihar makes 3.2. When you control for population size, the digital divide
      is far wider than headline numbers suggest.
    </div>
  </div>
  <div class="ins">
    <div class="ins-num" style="color:var(--a2)">Peak growth rate: passed</div>
    <div class="ins-ttl">The First Wave Is Largely Over</div>
    <div class="ins-body">
      32/34 states are still growing in absolute volume, but only 26 are
      accelerating above 30%. The states that have slowed most are the ones
      that had the most to lose: Maharashtra (now plateauing),
      Telangana, and Karnataka.
    </div>
  </div>
  <div class="ins">
    <div class="ins-num" style="color:var(--a3)">-6.6pp shift</div>
    <div class="ins-ttl">Concentration Declining</div>
    <div class="ins-body">
      The top 5 states' share of national UPI value fell 6.6 percentage
      points in 33 months. More states are participating,
      but per capita gaps between states remain very large.
    </div>
  </div>
</div>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('policy',this)">
    <span class="tab-eye">View for</span>Policy Makers
  </button>
  <button class="tab-btn" onclick="switchTab('market',this)">
    <span class="tab-eye">View for</span>Investors &amp; Business
  </button>
</div>

<!-- POLICY TAB -->
<div class="tab-panel active" id="tab-policy">

  <div class="pull">
    <div class="pull-stat" style="color:#4aadde">7×</div>
    <div class="pull-body">
      <strong>A 7× gap separates India's most and least digitised states — once you
      account for population.</strong>
      Delhi, Goa, Chandigarh, and Telangana each record over 20 UPI
      transactions per person per month. Bihar, Tripura, and Meghalaya record
      3–4. Targeting digital inclusion based on total transaction volume
      will consistently misallocate resources toward large states
      that are already relatively well-served.
    </div>
  </div>

  <div class="sec">
    <div class="sec-eye">Geographic View</div>
    <div class="sec-ttl">Where Is India Actually Using UPI?</div>
    <div class="sec-desc">
      This map shows UPI transactions per person per month, averaged over Feb 2025 – Jan 2026. Darker = more digitised per capita. The ranking chart on the right shows the same data sorted for easy comparison.
      Hover over any state for detailed numbers.
    </div>
    <div class="two">
      <div class="map-wrap">
        <div id="map-msg">
          Loading India map…<br>
          <span style="font-size:10px;margin-top:8px;opacity:.6">
            Requires internet connection
          </span>
        </div>
        <div id="choropleth" style="height:648px;min-height:648px"></div>
      </div>
      <div class="card" id="pc-bar"></div>
    </div>
  </div>

  <div class="sec mt32">
    <div class="sec-eye">Trend</div>
    <div class="sec-ttl">Is the Geographic Divide Narrowing Over Time?</div>
    <div class="sec-desc">
      The chart below tracks what share of India's total UPI value was transacted by just the top 5 states each month. A falling line means the rest of India is catching up, slowly.
    </div>
    <div class="card full mt16" id="conc"></div>
  </div>

  <div class="sec mt32">
    <div class="sec-eye">Structural Analysis</div>
    <div class="sec-ttl">Does UPI Adoption Track Income — and Where Does It Break Free?</div>
    <div class="sec-desc">
      Each dot is a state. The x-axis shows GSDP per capita (FY2024-25 estimate), the y-axis shows annual UPI value transacted per person. The dotted 45 degree line marks where UPI intensity equals 100% — states above it are transacting more through UPI than their GSDP per capita, states below are under-digitised relative to their wealth.
      <strong>Key findings:</strong> Telangana (134% intensity) and Ladakh (119%) are the
      clearest outliers above the diagonal. Gujarat (44%) and Sikkim (41%) are the
      most striking under-performers relative to their income level.
      Hover for exact GSDP, UPI value, intensity, and transaction frequency.
    </div>
    <div class="legend-row">
      <div class="leg"><div class="leg-dot" style="background:#1e7d52"></div>Above diagonal — UPI value exceeds GSDP per capita (over-indexed)</div>
      <div class="leg"><div class="leg-dot" style="background:#c8401a"></div>High income (GSDP &gt;Rs 2.5L) but below diagonal — under-digitised relative to wealth</div>
      <div class="leg"><div class="leg-dot" style="background:#8a9bb0"></div>Low income · below diagonal — expected (income constrains adoption)</div>
    </div>
    <div class="card full mt16" id="scat-intensity"></div>
  </div>

</div>

<!-- INVESTOR TAB -->
<div class="tab-panel" id="tab-market">

  <div class="pull">
    <div class="pull-stat" style="color:#e8a87c">26/34</div>
    <div class="pull-body">
      <strong>Peak growth has passed for the markets that mattered most.</strong>
      Only 2 states are declining or plateauing in absolute volume — but for
      the biggest markets (Maharashtra, Telangana, Karnataka, Delhi), the rapid
      user-acquisition phase is over. Growth is now shifting to mid-tier states
      like UP, Gujarat, and Haryana. The question for investors is no longer
      <em>where</em> to acquire users — it's <em>what to sell</em> to the ones already there.
    </div>
  </div>

  <div class="sec">
    <div class="sec-eye">Growth Trajectory</div>
    <div class="sec-ttl">Which States Are Still Growing Faster Than Before?</div>
    <div class="sec-desc">
      Each bar shows the percentage change in average monthly transaction volume between Year 1 (May 2023 – Apr 2024) and Year 2 (Feb 2025 – Jan 2026). Colour shows growth rate tier. Longer bars = faster growth rate.
      <strong>Important:</strong> small states (Andaman, Ladakh, Manipur) show very high percentage growth from tiny bases — hover for absolute volumes before drawing conclusions. A state adding 2 Mn transactions/month is a different market than one adding 320 Mn.
    </div>
    <div class="legend-row">
      <div class="leg"><div class="leg-dot" style="background:#1e7d52"></div>Accelerating (&gt;30% growth · 26 states)</div>
      <div class="leg"><div class="leg-dot" style="background:#1d6fa4"></div>Steady growth (10–30% · 6 states)</div>
      <div class="leg"><div class="leg-dot" style="background:#c8401a"></div>Plateauing (&lt;10% growth · 1 state)</div>
      <div class="leg"><div class="leg-dot" style="background:#8a9bb0"></div>Declining (volume falling · 1 state)</div>
    </div>
    <div class="card full" id="growth"></div>
  </div>

  <div class="sec mt32">
    <div class="sec-eye">Market Archetypes</div>
    <div class="sec-ttl">Growing in Transactions, Value, or Both?</div>
    <div class="sec-desc">
      Each dot is a state. The further right, the faster transactions are growing. The further up, the faster the total value is growing.
      <b>Scale Leaders</b> (top-right): focus on user acquisition and merchant onboarding.
      <b>Mature Markets</b> (bottom-left): focus on credit, insurance, and wealth products.
      <b>Mass Adoption</b> (bottom-right): many new small-ticket users — opportunity for BNPL and micro-lending.
      <b>Premiumisation</b> (top-left): fewer but higher-value transactions — B2B and merchant acquiring.
    </div>
    <div class="card full mt16" id="scat"></div>
  </div>

  <div class="sec mt32">
    <div class="sec-eye">Transaction Profile</div>
    <div class="sec-ttl">Are Transaction Sizes Getting Smaller?</div>
    <div class="sec-desc">
      Every state recorded a decline in average transaction size between the early and recent periods. Red bars indicate the steepest declines: these states are seeing the most new small-ticket users entering the system.
      Hover for exact values.
    </div>
    <div class="card full mt16" id="tick"></div>
  </div>

  <div class="sec mt32">
    <div class="sec-eye">State Deep Dive</div>
    <div class="sec-ttl">Explore Any State's Digitisation Journey</div>
    <div class="sec-desc">
      Select a state to see three charts over time: how many UPI transactions the average person makes each month, the average transaction size in rupees, and total monthly transaction volume. Together these show whether a state is digitising broadly or just deeply among a smaller user base.
    </div>
    <div class="state-bar">
      <span class="state-lbl">Select state</span>
      <select class="state-sel" id="state-sel" onchange="renderState(this.value)">
        {STATE_OPTIONS}
      </select>
    </div>
    <div class="ts-stack">
      <div class="card" id="ts-pc"></div>
      <div class="card" id="ts-ticket"></div>
      <div class="card" id="ts-vol"></div>
    </div>
  </div>

</div>

<footer>
  <strong>Data &amp; Methodology</strong><br>
  NPCI Ecosystem Statistics — State-wise UPI Product Statistics · May 2023 to January 2026 ·
  MOSPI National Accounts — Table 21, GSDP at Current Prices, Base 2011-12 ·
  Population estimates: Census of India 2011 projected to 2024 using state-specific
  decadal growth rates, consistent with MOSPI methodology ·
  Per capita figures use average of last 12 months (Feb 2025 – Jan 2026) ·
  Growth trajectory compares avg monthly volume in May 2023 – Apr 2024 vs Feb 2025 – Jan 2026 ·
  Value-volume CAGR uses 12-month smoothed averages at both endpoints to reduce
  seasonal distortion · GSDP FY2025-26 extrapolated via state-specific 5-year CAGR ·
  Unclassified transactions (~30% of national volume) excluded from state analysis ·
  Lakshadweep and Dadra &amp; NH excluded (proxy GSDP) ·
  Avg ticket size = (Monthly Value Cr / Monthly Volume Mn) × 10 = Rs per transaction ·
  UPI intensity = annual UPI value per capita / GSDP per capita × 100 ·
  Growth categories: Accelerating &gt;30%, Steady Growth 10–30%, Plateauing &lt;10%, Declining ·
  Built with Python · Plotly · NPCI Open Data
</footer>
</div>

<script>
const cfg = {responsive:true,displayModeBar:false};
const PC            = {PLACEHOLDER_PC};
const CONC          = {PLACEHOLDER_CONC};
const GROWTH        = {PLACEHOLDER_GROWTH};
const SCAT          = {PLACEHOLDER_SCAT};
const TICK          = {PLACEHOLDER_TICK};
const SCAT_INTENSITY = {PLACEHOLDER_SCAT_INTENSITY};
const MAP_DATA      = {PLACEHOLDER_MAP_DATA};
const STATE_DATA    = {PLACEHOLDER_STATE_DATA};
const STATES_ALL    = {PLACEHOLDER_STATES_ALL};

Plotly.newPlot('pc-bar',        PC.data,            PC.layout,            cfg);
Plotly.newPlot('conc',          CONC.data,          CONC.layout,          cfg);
Plotly.newPlot('growth',        GROWTH.data,        GROWTH.layout,        cfg);
Plotly.newPlot('scat',          SCAT.data,          SCAT.layout,          cfg);
Plotly.newPlot('tick',          TICK.data,          TICK.layout,          cfg);
Plotly.newPlot('scat-intensity',SCAT_INTENSITY.data,SCAT_INTENSITY.layout,cfg);

function switchTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  setTimeout(() => window.dispatchEvent(new Event('resize')), 80);
}

// ── Choropleth map ─────────────────────────────────────────────
const GEO_URL = 'https://gist.githubusercontent.com/jbrobst/56c13bbbf9d97d187fea01ca62ea5112/raw/e388c4cae20aa53cb5090210a42ebb9b765c0a36/india_states.geojson';
const NAME_MAP = {
  'ANDAMAN & NICOBAR':'Andaman & Nicobar Island',
  'ANDHRA PRADESH':'Andhra Pradesh',
  'ARUNACHAL PRADESH':'Arunanchal Pradesh',
  'ASSAM':'Assam','BIHAR':'Bihar','CHANDIGARH':'Chandigarh',
  'CHHATTISGARH':'Chhattisgarh','DELHI':'NCT of Delhi','GOA':'Goa',
  'GUJARAT':'Gujarat','HARYANA':'Haryana','HIMACHAL PRADESH':'Himachal Pradesh',
  'JAMMU AND KASHMIR':'Jammu & Kashmir','JHARKHAND':'Jharkhand',
  'KARNATAKA':'Karnataka','KERALA':'Kerala','LADAKH':'Ladakh',
  'LAKSHADWEEP':'Lakshadweep','MADHYA PRADESH':'Madhya Pradesh',
  'MAHARASHTRA':'Maharashtra','MANIPUR':'Manipur','MEGHALAYA':'Meghalaya',
  'MIZORAM':'Mizoram','NAGALAND':'Nagaland','ODISHA':'Odisha',
  'PUDUCHERRY':'Puducherry','PUNJAB':'Punjab','RAJASTHAN':'Rajasthan',
  'SIKKIM':'Sikkim','TAMIL NADU':'Tamil Nadu','TELANGANA':'Telangana',
  'TRIPURA':'Tripura','UTTAR PRADESH':'Uttar Pradesh',
  'UTTARAKHAND':'Uttarakhand','WEST BENGAL':'West Bengal',
};
const GEO_LOOKUP = {};
MAP_DATA.forEach(d => { const gn = NAME_MAP[d.state]; if (gn) GEO_LOOKUP[gn] = d; });
let geoJson = null;

async function loadMap() {
  try {
    const res = await fetch(GEO_URL);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    geoJson = await res.json();
    const sample  = geoJson.features[0].properties;
    const nameKey = sample.ST_NM !== undefined ? 'ST_NM' : 'NAME_1';
    document.getElementById('map-msg').style.display = 'none';
    const locs=[], zs=[], txts=[], cdata=[];
    geoJson.features.forEach(f => {
      const gn = f.properties[nameKey];
      const d  = GEO_LOOKUP[gn];
      locs.push(gn);
      zs.push(d ? +d.txns_per_capita : null);
      txts.push(d ? d.state_title : gn);
      cdata.push([d ? d.state_title:'N/A', d ? d.txns_per_capita:'N/A',
                  d ? d.rank:'N/A', d ? d.growth_type:'N/A']);
    });
    const valid = zs.filter(v => v !== null);
    Plotly.newPlot('choropleth', [{
      type:'choropleth', geojson:geoJson,
      featureidkey:'properties.' + nameKey,
      locations:locs, z:zs,
      zmin:Math.min(...valid), zmax:Math.max(...valid),
      colorscale:[[0,'#f0f9ff'],[0.2,'#bae6fd'],[0.5,'#38bdf8'],[0.8,'#0369a1'],[1.0,'#0c2d5e']],
      text:txts, customdata:cdata,
      hovertemplate:'<b>%{customdata[0]}</b><br>UPI txns per person per month: <b>%{customdata[1]}</b><br>Rank: #%{customdata[2]} of 34<br>Growth status: %{customdata[3]}<extra></extra>',
      marker:{line:{color:'#ffffff',width:0.8}},
      colorbar:{title:{text:'Txns / person / month',
        font:{size:10,color:'#8a9bb0',family:'DM Mono,monospace'}},
        tickfont:{size:9,color:'#8a9bb0',family:'DM Mono,monospace'},
        thickness:10,len:0.65,bgcolor:'rgba(0,0,0,0)'},
    }], {
      geo:{scope:'asia',resolution:50,center:{lat:22,lon:80},
        projection:{type:'mercator',scale:1.2},
        showland:true,landcolor:'#f0ece6',showocean:true,oceancolor:'#e8f4f8',
        showlakes:false,showcountries:true,countrycolor:'#d0ccc6',
        showcoastlines:true,coastlinecolor:'#d0ccc6',bgcolor:'rgba(0,0,0,0)',
        lataxis:{range:[6,38]},lonaxis:{range:[66,100]}},
      paper_bgcolor:'rgba(0,0,0,0)',margin:{l:0,r:0,t:0,b:0},height:650,
      hoverlabel:{bgcolor:'#1c2533',bordercolor:'#1d6fa4',
        font:{family:'DM Mono,monospace',color:'#fff',size:11}},
    }, {responsive:true, displayModeBar:false});
  } catch(e) {
    document.getElementById('map-msg').innerHTML =
      '<b style="color:#c8401a">Map unavailable</b><br>Requires internet connection.<br>' +
      '<span style="font-size:10px;margin-top:8px;opacity:.6">See ranking chart for same data.</span>';
  }
}

// ── State time-series deep dive ────────────────────────────────
function tsLayout(title, ytitle, color) {
  return {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'DM Mono,monospace',color:'#1c2533',size:10},
    margin:{l:55,r:16,t:44,b:64},
    title:{text:title,font:{family:'Syne,sans-serif',size:12,color:'#1c2533'},x:0},
    xaxis:{type:'category',gridcolor:'#e8e3db',tickfont:{color:'#8a9bb0',size:8},
           tickangle:-45,zeroline:false,automargin:true},
    yaxis:{title:{text:ytitle,font:{color:'#8a9bb0',size:10}},
           gridcolor:'#e8e3db',tickfont:{color:'#4a5568'},zeroline:false,automargin:true},
    height:240, showlegend:false,
    hoverlabel:{bgcolor:'#1c2533',bordercolor:color,
      font:{family:'DM Mono,monospace',color:'#fff',size:11}},
  };
}

function renderState(state) {
  const d = STATE_DATA[state];
  if (!d) return;
  const t = state.split(' ').map(w => w.charAt(0).toUpperCase()+w.slice(1).toLowerCase()).join(' ');
  const toRgba = (hex, a) => 'rgba('+parseInt(hex.slice(1,3),16)+','+parseInt(hex.slice(3,5),16)+','+parseInt(hex.slice(5,7),16)+','+a+')';
  [
    {id:'ts-pc',    y:d.percapita, color:'#1d6fa4', title:'UPI transactions per person per month — '+t, yt:'Transactions per person'},
    {id:'ts-ticket',y:d.ticket,    color:'#c8401a', title:'Average transaction size (Rs) — '+t,         yt:'Rs per transaction'},
    {id:'ts-vol',   y:d.volume,    color:'#1e7d52', title:'Total monthly transactions — '+t,            yt:'Transactions (Millions)'},
  ].forEach(ch => {
    Plotly.react(ch.id, [{
      x:d.months, y:ch.y, type:'scatter', mode:'lines+markers',
      line:{color:ch.color,width:2.5,shape:'spline'},
      marker:{size:4,color:ch.color,line:{width:1.5,color:'#fff'}},
      fill:'tozeroy', fillcolor:toRgba(ch.color,0.07),
      hovertemplate:'<b>%{x}</b><br>'+ch.yt+': %{y}<extra></extra>',
    }], tsLayout(ch.title, ch.yt, ch.color), cfg);
  });
}

renderState(STATES_ALL[0]);
loadMap();
</script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════════════════
# STATE TIME-SERIES DATA  (full 33-month series per state)
# ══════════════════════════════════════════════════════════════════════════════

def get_state_time_series() -> dict:
    """33-month per-state time series: percapita txns, ticket size, total volume."""
    months = [
        "May 2023","Jun 2023","Jul 2023","Aug 2023","Sep 2023","Oct 2023",
        "Nov 2023","Dec 2023","Jan 2024","Feb 2024","Mar 2024","Apr 2024",
        "May 2024","Jun 2024","Jul 2024","Aug 2024","Sep 2024","Oct 2024",
        "Nov 2024","Dec 2024","Jan 2025","Feb 2025","Mar 2025","Apr 2025",
        "May 2025","Jun 2025","Jul 2025","Aug 2025","Sep 2025","Oct 2025",
        "Nov 2025","Dec 2025","Jan 2026",
    ]
    # fmt: off  (keeps the table readable)
    raw = {
      "ANDAMAN & NICOBAR": {
        "percapita":[4.02,3.78,4.09,4.46,4.46,5.11,5.38,6.39,6.42,6.37,7.14,7.26,7.29,7.02,7.24,7.26,7.26,8.14,8.23,9.2,9.03,7.82,8.86,9.18,9.56,7.82,8.93,9.13,8.89,9.95,10.22,11.23,11.36],
        "ticket":[2026,1961,1886,1842,1842,1881,1926,1861,1862,1858,1781,1785,1810,1688,1644,1631,1631,1690,1662,1671,1687,1653,1633,1635,1597,1492,1495,1462,1530,1602,1569,1603,1635],
        "volume":[1.7,1.6,1.7,1.8,1.8,2.1,2.2,2.6,2.6,2.6,3.0,3.0,3.0,2.9,3.0,3.0,3.0,3.4,3.4,3.8,3.7,3.2,3.7,3.8,4.0,3.2,3.7,3.8,3.7,4.1,4.2,4.6,4.7]},
      "ANDHRA PRADESH": {
        "percapita":[5.31,5.22,5.72,6.18,6.18,6.4,6.65,7.74,8.23,8.18,9.11,9.08,9.31,9.1,9.47,9.82,9.82,10.45,10.41,11.29,9.76,8.19,9.28,10.65,12.05,8.78,9.47,9.75,9.5,9.9,9.96,10.79,11.11],
        "ticket":[2165,2133,2075,2000,2000,1988,1969,1922,1940,1912,1886,1916,1868,1830,1814,1785,1785,1765,1715,1719,1776,1767,1787,1748,1747,1754,1747,1672,1692,1729,1666,1682,1720],
        "volume":[300.2,295.3,323.3,349.6,349.6,361.8,376.2,437.8,465.5,462.4,515.3,513.6,526.3,514.5,535.7,555.0,555.0,590.9,588.7,638.5,551.8,463.2,524.7,602.4,681.4,496.6,535.3,551.5,537.2,559.8,563.4,609.8,628.2]},
      "ARUNACHAL PRADESH": {
        "percapita":[3.88,4.13,4.37,4.72,4.72,5.27,5.5,6.2,6.04,6.42,7.68,6.82,8.27,8.08,8.45,8.01,8.01,8.42,8.64,9.54,9.11,8.21,9.51,9.89,11.28,9.58,11.35,11.49,11.29,11.58,11.7,11.79,11.61],
        "ticket":[1846,1790,1687,1634,1634,1635,1624,1677,1634,1624,1585,1829,1529,1434,1387,1377,1377,1364,1347,1401,1398,1402,1384,1418,1318,1273,1311,1265,1272,1296,1309,1368,1355],
        "volume":[7.2,7.7,8.1,8.8,8.8,9.8,10.2,11.6,11.2,12.0,14.3,12.7,15.4,15.0,15.7,14.9,14.9,15.7,16.1,17.8,17.0,15.3,17.7,18.4,21.0,17.8,21.1,21.4,21.0,21.6,21.8,22.0,21.6]},
      "ASSAM": {
        "percapita":[2.37,2.34,2.53,2.78,2.78,3.15,3.16,3.07,3.41,3.92,4.37,4.49,4.86,4.87,4.89,4.71,4.71,5.11,5.17,5.7,4.93,4.24,4.76,5.74,6.61,4.75,5.19,5.35,5.22,5.39,5.58,5.94,5.93],
        "ticket":[1656,1578,1516,1465,1465,1475,1483,1474,1479,1457,1443,1396,1283,1222,1190,1188,1188,1198,1185,1216,1234,1241,1258,1188,1134,1096,1103,1053,1084,1074,1083,1102,1111],
        "volume":[90.2,89.2,96.6,105.9,105.9,120.1,120.2,117.1,130.0,149.1,166.5,171.1,185.2,185.4,186.2,179.4,179.4,194.5,197.0,217.0,187.7,161.4,181.4,218.8,251.7,181.1,197.8,203.8,198.7,205.4,212.7,226.4,225.9]},
      "BIHAR": {
        "percapita":[2.0,1.88,2.01,2.2,2.2,2.46,2.68,2.38,2.57,2.86,3.26,3.4,3.54,3.47,3.44,3.33,3.33,3.76,3.82,3.88,2.97,2.55,2.96,4.13,4.84,2.81,2.9,2.85,2.83,3.22,3.26,3.24,3.27],
        "ticket":[1832,1829,1660,1554,1554,1576,1610,1669,1602,1636,1585,1578,1520,1517,1473,1414,1414,1432,1472,1498,1527,1577,1545,1432,1452,1503,1449,1393,1444,1469,1456,1471,1459],
        "volume":[280.3,263.0,281.5,307.7,307.7,343.9,375.5,332.7,359.2,400.5,455.8,475.9,495.2,486.0,481.0,466.2,466.2,526.1,535.3,542.9,415.4,357.2,415.0,577.8,677.1,393.0,405.5,399.2,396.8,450.6,456.5,454.0,457.9]},
      "CHANDIGARH": {
        "percapita":[14.19,13.56,14.45,16.38,16.38,17.73,17.22,15.77,15.9,17.0,20.52,21.49,23.16,20.94,21.87,20.2,20.2,21.43,19.36,21.21,18.72,16.46,19.06,22.91,25.18,17.66,20.07,20.48,20.63,21.49,20.93,21.69,20.78],
        "ticket":[1356,1381,1383,1331,1331,1356,1427,1338,1378,1373,1285,1297,1270,1268,1303,1261,1261,1293,1309,1316,1281,1254,1235,1248,1272,1197,1246,1200,1221,1305,1263,1283,1331],
        "volume":[18.4,17.6,18.8,21.3,21.3,23.0,22.4,20.5,20.6,22.1,26.6,27.9,30.1,27.2,28.4,26.2,26.2,27.8,25.1,27.5,24.3,21.4,24.7,29.7,32.7,22.9,26.0,26.6,26.8,27.9,27.2,28.2,27.0]},
      "CHHATTISGARH": {
        "percapita":[2.43,2.2,2.55,2.93,2.93,3.06,2.83,3.2,3.39,3.48,3.96,3.9,4.17,4.09,4.08,4.03,4.03,4.76,4.21,4.66,4.04,3.37,3.86,4.6,5.14,3.63,3.89,4.05,3.92,4.23,4.11,4.38,4.46],
        "ticket":[1426,1441,1385,1313,1313,1354,1405,1370,1410,1415,1352,1357,1321,1337,1313,1264,1264,1335,1277,1315,1380,1388,1330,1286,1261,1285,1274,1216,1244,1329,1250,1292,1349],
        "volume":[80.8,73.1,84.7,97.2,97.2,101.8,93.9,106.2,112.5,115.6,131.6,129.7,138.7,136.0,135.5,133.8,133.8,158.0,140.0,154.8,134.2,111.9,128.2,152.8,170.9,120.6,129.3,134.6,130.2,140.5,136.6,145.5,148.1]},
      "DELHI": {
        "percapita":[18.0,17.95,18.45,18.74,18.74,20.87,20.03,16.63,18.26,19.66,21.79,21.5,23.23,21.79,21.01,18.59,18.59,21.56,20.5,22.62,19.05,16.7,19.45,24.45,28.08,19.49,21.72,22.6,22.79,23.64,22.78,23.98,23.81],
        "ticket":[1432,1419,1364,1311,1311,1346,1426,1384,1361,1364,1272,1262,1196,1205,1251,1235,1235,1224,1251,1241,1284,1288,1277,1217,1198,1209,1257,1227,1249,1326,1312,1288,1330],
        "volume":[387.9,386.9,397.8,404.0,404.0,449.9,431.7,358.6,393.6,423.8,469.7,463.6,500.7,469.8,452.9,400.7,400.7,464.8,442.0,487.6,410.6,359.9,419.2,527.0,605.3,420.1,468.2,487.3,491.3,509.6,491.1,516.9,513.4]},
      "GOA": {
        "percapita":[12.3,11.47,11.4,12.96,12.96,14.89,15.14,17.3,18.31,18.53,18.7,17.3,18.42,17.28,15.88,16.81,16.81,19.23,19.63,23.61,21.75,18.27,20.19,22.5,24.81,17.8,18.93,19.97,19.98,22.21,22.48,24.9,24.97],
        "ticket":[1492,1500,1491,1418,1418,1441,1437,1470,1459,1430,1389,1411,1424,1440,1440,1393,1393,1402,1393,1423,1431,1376,1385,1386,1411,1409,1421,1406,1426,1472,1437,1489,1503],
        "volume":[19.9,18.5,18.4,21.0,21.0,24.1,24.5,28.0,29.6,29.9,30.2,28.0,29.8,27.9,25.7,27.2,27.2,31.1,31.7,38.2,35.2,29.5,32.6,36.4,40.1,28.8,30.6,32.3,32.3,35.9,36.3,40.2,40.4]},
      "GUJARAT": {
        "percapita":[3.8,3.65,3.98,4.28,4.28,4.79,4.45,4.49,4.96,5.16,5.78,5.68,6.02,5.95,5.96,5.73,5.73,6.88,5.89,6.76,6.35,5.48,6.19,7.08,7.71,5.8,6.6,6.78,6.78,7.03,6.72,7.31,7.48],
        "ticket":[1660,1674,1640,1592,1592,1587,1721,1691,1657,1660,1562,1546,1539,1517,1525,1502,1502,1616,1466,1561,1560,1513,1494,1437,1453,1453,1476,1427,1464,1600,1491,1561,1552],
        "volume":[288.6,277.8,302.2,325.3,325.3,364.3,338.5,341.6,376.7,392.5,439.5,431.6,457.4,452.6,453.2,435.3,435.3,523.1,447.8,513.7,482.4,416.3,470.8,538.6,585.8,440.9,501.3,515.2,515.1,534.1,510.6,555.3,568.9]},
      "HARYANA": {
        "percapita":[7.2,7.05,7.69,7.97,7.97,9.14,8.7,9.06,9.43,9.3,10.94,10.9,11.79,11.34,11.24,10.25,10.25,11.58,10.78,11.6,10.59,9.42,10.8,12.78,14.41,11.25,12.38,12.5,12.53,13.1,12.53,13.03,12.88],
        "ticket":[1595,1551,1510,1498,1498,1533,1616,1578,1549,1557,1438,1445,1442,1400,1427,1414,1414,1429,1490,1476,1491,1467,1431,1403,1425,1356,1382,1345,1370,1479,1467,1466,1481],
        "volume":[231.2,226.3,246.8,255.9,255.9,293.2,279.3,290.9,302.7,298.6,351.2,349.9,378.4,363.8,360.8,328.9,328.9,371.8,346.0,372.4,339.8,302.2,346.8,410.4,462.7,361.0,397.3,401.3,402.1,420.3,402.1,418.1,413.4]},
      "HIMACHAL PRADESH": {
        "percapita":[4.79,4.66,4.21,4.38,4.38,5.17,5.06,5.24,5.21,5.35,6.46,6.86,7.66,7.53,6.57,6.05,6.05,6.98,6.5,7.09,6.59,5.83,7.11,8.0,8.51,7.23,7.07,6.83,6.61,7.71,7.29,7.85,7.5],
        "ticket":[1380,1471,1393,1334,1334,1376,1408,1366,1381,1361,1276,1253,1243,1287,1306,1285,1285,1392,1338,1308,1326,1270,1234,1216,1233,1249,1258,1228,1299,1397,1336,1339,1353],
        "volume":[38.5,37.5,33.9,35.2,35.2,41.6,40.7,42.2,41.9,43.0,51.9,55.2,61.6,60.5,52.8,48.7,48.7,56.1,52.3,57.0,53.0,46.8,57.1,64.3,68.4,58.1,56.8,54.9,53.1,62.0,58.6,63.1,60.3]},
      "JAMMU AND KASHMIR": {
        "percapita":[1.95,1.87,1.96,2.11,2.11,2.42,2.47,2.41,2.64,2.75,3.27,3.66,4.08,4.06,4.04,3.84,3.84,4.36,4.25,4.52,4.13,3.7,4.36,5.37,5.73,4.66,5.2,4.92,4.74,5.3,5.07,5.27,5.09],
        "ticket":[1571,1640,1654,1518,1518,1554,1561,1545,1464,1455,1391,1411,1360,1386,1390,1393,1393,1527,1452,1416,1382,1360,1400,1306,1252,1236,1285,1266,1344,1436,1397,1373,1357],
        "volume":[32.1,30.8,32.3,34.8,34.8,39.9,40.7,39.7,43.5,45.2,53.8,60.2,67.2,66.8,66.5,63.2,63.2,71.7,70.0,74.4,68.0,60.9,71.8,88.4,94.4,76.7,85.6,81.0,78.0,87.2,83.5,86.7,83.8]},
      "JHARKHAND": {
        "percapita":[2.18,2.07,2.25,2.44,2.44,2.77,2.86,3.08,3.2,3.3,3.67,3.71,3.82,3.79,3.93,3.69,3.69,4.39,4.24,4.47,3.87,3.32,3.88,4.8,5.34,3.63,3.91,3.99,3.95,4.25,4.16,4.33,4.4],
        "ticket":[1543,1555,1476,1390,1390,1425,1447,1456,1409,1443,1430,1423,1354,1357,1367,1288,1288,1346,1325,1370,1385,1397,1426,1360,1334,1327,1283,1260,1310,1327,1319,1353,1350],
        "volume":[93.4,88.8,96.7,104.7,104.7,118.9,122.6,132.2,137.1,141.5,157.4,159.0,163.7,162.7,168.7,158.2,158.2,188.4,182.0,191.8,165.9,142.3,166.6,206.1,229.1,155.8,167.6,171.2,169.5,182.2,178.5,185.9,188.6]},
      "KARNATAKA": {
        "percapita":[10.79,10.99,11.78,12.51,12.51,12.96,12.65,12.46,13.37,14.05,15.46,14.83,15.63,15.43,15.81,16.01,16.01,16.69,16.31,17.52,15.34,13.18,14.79,17.1,19.53,13.54,14.45,14.58,14.35,14.7,14.96,15.78,15.77],
        "ticket":[1480,1439,1409,1373,1373,1391,1413,1398,1385,1394,1374,1401,1410,1386,1366,1356,1356,1386,1356,1356,1372,1360,1392,1373,1389,1348,1354,1322,1357,1389,1359,1391,1413],
        "volume":[797.6,812.5,870.3,924.4,924.4,957.7,935.0,921.0,987.7,1038.6,1142.2,1095.6,1155.2,1140.2,1168.4,1182.9,1182.9,1233.2,1205.0,1294.8,1133.6,974.1,1092.9,1263.4,1443.0,1000.7,1067.7,1077.8,1060.4,1086.6,1105.6,1166.4,1165.0]},
      "KERALA": {
        "percapita":[6.18,6.06,6.31,7.02,7.02,7.16,7.28,7.71,7.94,8.1,8.73,8.77,9.12,8.81,8.88,9.26,9.26,9.73,9.67,10.41,10.51,9.28,9.97,10.2,11.18,9.37,10.4,11.25,11.16,11.79,11.72,12.72,12.98],
        "ticket":[1554,1529,1511,1501,1501,1441,1423,1427,1442,1408,1427,1432,1462,1421,1410,1395,1395,1356,1354,1358,1382,1367,1431,1403,1427,1385,1405,1404,1407,1392,1373,1374,1408],
        "volume":[219.5,215.1,224.0,249.4,249.4,254.3,258.4,273.7,282.0,287.6,309.8,311.3,323.8,312.7,315.4,328.8,328.8,345.6,343.4,369.8,373.2,329.6,354.0,362.3,397.1,332.8,369.3,399.5,396.3,418.4,416.3,451.7,460.7]},
      "LADAKH": {
        "percapita":[5.89,6.2,6.64,7.02,7.02,6.92,5.86,5.96,5.92,5.75,7.23,9.25,11.51,13.25,13.29,11.99,11.99,10.99,9.55,9.18,8.22,7.4,8.73,12.43,14.83,14.42,16.03,15.34,12.88,10.27,11.3,10.38,9.55],
        "ticket":[2400,2513,2494,2346,2346,2321,2161,2119,1999,2018,1813,1974,1944,2047,1985,2017,2017,2121,1919,1933,1849,1735,1645,1796,1674,1615,1755,1744,1812,2211,1842,1830,1777],
        "volume":[1.7,1.8,1.9,2.0,2.0,2.0,1.7,1.7,1.7,1.7,2.1,2.7,3.4,3.9,3.9,3.5,3.5,3.2,2.8,2.7,2.4,2.2,2.6,3.6,4.3,4.2,4.7,4.5,3.8,3.0,3.3,3.0,2.8]},
      "MADHYA PRADESH": {
        "percapita":[4.3,4.63,5.11,5.44,5.44,6.37,5.53,4.16,4.89,5.34,6.23,6.3,6.5,6.14,6.26,6.05,6.05,6.18,5.79,6.24,5.16,4.22,4.63,6.24,7.45,4.19,4.56,4.72,4.55,4.89,4.82,5.07,5.14],
        "ticket":[1503,1491,1413,1350,1350,1378,1414,1399,1379,1389,1336,1378,1344,1335,1306,1267,1267,1332,1331,1331,1365,1374,1359,1354,1348,1346,1320,1274,1286,1356,1344,1369,1377],
        "volume":[397.5,427.3,471.5,502.8,502.8,588.0,510.5,384.1,451.9,493.4,575.5,581.9,600.1,567.4,578.0,558.9,558.9,571.1,534.8,576.3,476.4,389.7,427.8,576.0,688.2,386.8,420.8,436.1,420.5,451.9,444.9,468.4,475.1]},
      "MAHARASHTRA": {
        "percapita":[13.64,14.37,14.93,15.55,15.55,16.33,15.29,12.81,12.69,12.76,13.4,13.05,13.63,13.41,13.61,13.83,13.83,15.99,14.43,16.37,15.6,13.89,16.11,17.48,18.08,12.78,13.98,14.57,14.48,15.75,15.8,17.24,16.66],
        "ticket":[1388,1400,1368,1335,1335,1335,1389,1316,1331,1330,1371,1380,1364,1379,1345,1255,1255,1290,1236,1225,1187,1162,1159,1168,1206,1214,1210,1171,1196,1247,1165,1122,1176],
        "volume":[1859.6,1958.6,2034.1,2119.3,2119.3,2225.6,2083.4,1746.5,1729.3,1738.5,1826.5,1779.2,1857.6,1827.9,1855.4,1884.8,1884.8,2179.8,1967.1,2231.0,2126.3,1892.7,2195.6,2382.3,2463.9,1741.9,1905.4,1985.6,1973.4,2146.3,2152.8,2349.4,2271.2]},
      "MANIPUR": {
        "percapita":[0.8,0.56,0.47,0.68,0.68,1.21,1.27,1.69,1.91,1.89,2.52,2.55,2.57,2.67,2.88,2.87,2.87,3.16,2.33,2.86,3.36,3.01,3.55,3.99,4.54,3.19,4.25,4.38,4.34,4.77,4.66,5.15,4.99],
        "ticket":[2479,2617,2988,3366,3366,3261,3344,2855,2675,2740,2520,2449,2482,2394,2319,2255,2255,2308,2478,2523,2329,2310,2209,2105,2012,2050,2000,1927,1955,2033,1987,2009,2000],
        "volume":[2.7,1.9,1.6,2.3,2.3,4.1,4.3,5.7,6.5,6.4,8.5,8.6,8.7,9.0,9.7,9.7,9.7,10.7,7.9,9.7,11.4,10.2,12.0,13.5,15.4,10.8,14.4,14.8,14.7,16.2,15.8,17.4,16.9]},
      "MEGHALAYA": {
        "percapita":[1.08,1.03,1.25,1.5,1.5,1.45,1.6,1.72,1.6,1.89,2.35,2.37,2.63,2.63,2.74,2.42,2.42,2.74,3.03,3.45,2.69,2.67,3.2,3.51,4.13,3.25,3.8,3.9,3.81,4.01,4.13,4.46,3.86],
        "ticket":[1908,1923,1859,1797,1797,1794,1786,1905,1805,1747,1591,1527,1457,1399,1409,1470,1470,1466,1431,1550,1522,1484,1439,1377,1358,1315,1351,1262,1314,1336,1362,1378,1313],
        "volume":[4.4,4.2,5.1,6.1,6.1,5.9,6.6,7.0,6.5,7.7,9.6,9.7,10.7,10.7,11.2,9.9,9.9,11.2,12.4,14.1,11.0,10.9,13.1,14.3,16.9,13.2,15.5,15.9,15.6,16.4,16.8,18.2,15.8]},
      "MIZORAM": {
        "percapita":[2.62,2.61,2.81,2.98,2.98,3.4,3.77,3.83,3.65,4.17,4.56,4.65,4.96,4.9,5.03,5.04,5.04,5.79,6.3,6.62,6.09,6.0,6.99,6.81,7.62,6.91,8.0,8.28,8.65,9.56,9.3,10.34,9.1],
        "ticket":[2429,2422,2291,2199,2199,2193,2168,2217,2088,2057,2035,1923,1939,1871,1801,1775,1775,1730,1743,1803,1683,1686,1678,1594,1603,1516,1486,1438,1453,1439,1517,1539,1457],
        "volume":[3.8,3.7,4.0,4.3,4.3,4.9,5.4,5.5,5.2,6.0,6.5,6.7,7.1,7.0,7.2,7.2,7.2,8.3,9.0,9.5,8.7,8.6,10.0,9.8,10.9,9.9,11.5,11.9,12.4,13.7,13.3,14.8,13.0]},
      "NAGALAND": {
        "percapita":[2.05,2.53,2.58,2.76,2.76,3.03,2.92,2.79,2.68,3.1,4.02,4.1,4.86,4.75,5.08,4.41,4.41,5.06,5.16,5.52,4.54,4.31,5.01,5.47,6.28,5.07,5.93,6.15,6.14,6.45,6.53,6.96,6.2],
        "ticket":[2569,2339,2344,2264,2264,2239,2319,2520,2362,2274,2110,2001,1899,1778,1720,1784,1784,1725,1747,1842,1812,1753,1732,1625,1555,1493,1486,1432,1463,1486,1540,1620,1565],
        "volume":[4.1,5.0,5.1,5.5,5.5,6.0,5.8,5.6,5.3,6.2,8.0,8.2,9.7,9.5,10.1,8.8,8.8,10.1,10.3,11.0,9.0,8.6,10.0,10.9,12.5,10.1,11.8,12.2,12.2,12.8,13.0,13.8,12.3]},
      "ODISHA": {
        "percapita":[3.98,3.97,4.18,4.42,4.42,4.89,4.9,4.8,5.2,5.56,6.22,5.93,6.25,6.25,6.43,6.4,6.4,7.15,7.11,7.53,6.08,5.01,5.65,7.27,8.36,4.98,5.29,5.58,5.4,5.69,5.79,6.11,6.24],
        "ticket":[1521,1520,1497,1390,1390,1420,1402,1450,1464,1478,1414,1366,1355,1347,1347,1253,1253,1288,1246,1266,1369,1394,1378,1235,1249,1286,1285,1225,1291,1287,1252,1286,1333],
        "volume":[198.1,197.7,208.1,220.0,220.0,243.4,244.2,239.0,259.3,277.1,310.0,295.5,311.4,311.5,320.2,318.7,318.7,356.2,354.2,375.2,302.7,249.8,281.3,362.0,416.5,247.9,263.7,277.8,269.2,283.6,288.6,304.6,311.0]},
      "PUDUCHERRY": {
        "percapita":[5.85,5.95,6.45,6.72,6.72,7.16,6.88,7.48,7.7,7.9,8.45,8.19,8.77,8.7,8.85,8.79,8.79,9.41,8.77,9.38,9.78,8.81,9.85,10.14,11.01,9.68,10.73,10.95,10.54,11.25,10.8,11.8,12.05],
        "ticket":[1500,1515,1490,1478,1478,1435,1478,1426,1426,1445,1422,1425,1423,1422,1411,1412,1412,1403,1372,1375,1402,1397,1382,1367,1397,1351,1366,1353,1386,1421,1380,1377,1411],
        "volume":[10.1,10.2,11.1,11.6,11.6,12.3,11.8,12.9,13.2,13.6,14.5,14.1,15.1,15.0,15.2,15.1,15.1,16.2,15.1,16.1,16.8,15.2,16.9,17.4,18.9,16.6,18.4,18.8,18.1,19.4,18.6,20.3,20.7]},
      "PUNJAB": {
        "percapita":[3.95,3.78,4.03,4.48,4.48,4.86,4.7,4.61,4.7,4.88,5.67,5.71,6.2,5.77,5.72,5.34,5.34,5.83,5.6,5.88,5.66,5.07,5.93,6.46,6.83,5.72,6.39,6.45,6.48,7.02,6.75,6.91,6.81],
        "ticket":[1808,1791,1772,1686,1686,1724,1868,1887,1857,1804,1675,1653,1671,1636,1675,1610,1610,1661,1752,1762,1779,1749,1697,1629,1714,1633,1658,1585,1626,1741,1785,1787,1811],
        "volume":[129.9,124.2,132.5,147.1,147.1,159.7,154.3,151.5,154.3,160.3,186.2,187.5,203.6,189.6,187.8,175.3,175.3,191.4,184.1,193.2,185.8,166.7,194.7,212.0,224.5,187.8,210.0,211.8,212.7,230.7,221.7,227.0,223.5]},
      "RAJASTHAN": {
        "percapita":[4.34,3.83,4.6,5.21,5.21,5.24,5.12,5.19,5.74,6.12,6.8,6.64,7.15,6.98,7.14,6.77,6.77,7.6,7.04,7.58,6.16,5.22,5.84,7.57,8.65,5.42,5.97,6.14,5.88,6.22,6.01,6.31,6.34],
        "ticket":[1648,1646,1554,1509,1509,1575,1648,1632,1600,1610,1521,1525,1502,1468,1470,1422,1422,1512,1543,1540,1569,1556,1515,1468,1473,1460,1442,1384,1419,1546,1532,1528,1528],
        "volume":[382.6,337.7,405.9,459.9,459.9,462.0,451.8,458.0,506.6,540.3,599.8,586.4,630.9,616.0,630.2,597.3,597.3,671.0,621.0,668.6,543.6,460.6,515.6,668.4,763.4,478.6,527.2,541.4,519.1,549.3,530.2,557.1,559.8]},
      "SIKKIM": {
        "percapita":[5.32,5.48,5.34,5.43,5.43,5.4,5.39,6.44,6.42,6.76,7.91,7.56,8.95,8.47,8.3,8.11,8.11,9.31,8.92,10.48,9.26,8.85,10.9,12.13,13.69,10.67,11.49,11.37,11.94,10.65,12.22,12.95,12.73],
        "ticket":[1900,1838,1695,1666,1666,1811,1724,1757,1716,1651,1580,1653,1648,1547,1446,1407,1407,1544,1428,1493,1453,1365,1368,1412,1392,1279,1275,1218,1331,1336,1292,1369,1358],
        "volume":[3.8,3.9,3.8,3.9,3.9,3.8,3.8,4.6,4.6,4.8,5.6,5.4,6.4,6.0,5.9,5.8,5.8,6.6,6.4,7.5,6.6,6.3,7.8,8.6,9.8,7.6,8.2,8.1,8.5,7.6,8.7,9.2,9.1]},
      "TAMIL NADU": {
        "percapita":[5.28,5.27,5.67,5.87,5.87,6.18,6.03,5.88,6.33,6.8,7.53,7.33,7.71,7.62,7.77,7.78,7.78,8.22,7.87,8.56,8.21,7.47,8.38,8.92,9.87,8.03,8.94,9.17,8.96,9.32,9.34,9.9,9.86],
        "ticket":[1699,1727,1680,1651,1651,1623,1663,1631,1608,1618,1583,1583,1604,1618,1574,1557,1557,1567,1518,1498,1518,1533,1528,1485,1519,1503,1503,1478,1524,1580,1518,1519,1543],
        "volume":[459.8,458.9,494.2,511.0,511.0,538.5,525.3,511.9,551.2,592.6,656.3,638.5,671.8,663.6,677.2,677.8,677.8,716.4,685.8,746.1,715.5,651.2,730.3,776.9,859.8,699.3,778.8,799.2,780.4,812.0,813.8,862.9,859.4]},
      "TELANGANA": {
        "percapita":[17.47,17.31,17.56,18.37,18.37,18.96,18.64,16.56,17.94,19.48,21.62,20.74,21.21,21.41,21.78,22.4,22.4,23.36,22.88,24.22,19.5,17.14,19.12,23.15,26.53,17.99,19.29,19.59,19.39,20.38,20.75,21.62,21.23],
        "ticket":[1807,1817,1775,1696,1696,1700,1725,1741,1671,1650,1600,1626,1632,1622,1593,1571,1571,1548,1551,1603,1603,1579,1593,1549,1607,1609,1601,1522,1549,1565,1543,1593,1598],
        "volume":[716.8,710.3,720.6,753.6,753.6,778.0,764.8,679.5,736.2,799.5,887.1,851.1,870.2,878.6,893.7,919.0,919.0,958.4,938.6,993.8,800.2,703.4,784.4,949.7,1088.6,738.4,791.5,804.0,795.5,836.3,851.2,887.1,871.0]},
      "TRIPURA": {
        "percapita":[1.35,1.28,1.42,1.54,1.54,1.93,1.82,1.88,2.03,2.31,2.51,2.45,2.5,2.46,2.45,2.25,2.25,2.66,2.67,2.84,2.86,2.61,3.0,3.17,3.37,2.85,3.24,3.32,3.55,3.44,3.5,3.73,3.79],
        "ticket":[1708,1745,1707,1665,1665,1687,1684,1672,1653,1652,1623,1538,1471,1464,1487,1436,1436,1474,1474,1510,1481,1460,1422,1389,1329,1285,1329,1285,1372,1295,1346,1361,1367],
        "volume":[6.0,5.6,6.2,6.8,6.8,8.5,8.0,8.3,8.9,10.2,11.0,10.8,11.0,10.8,10.8,9.9,9.9,11.7,11.7,12.5,12.6,11.5,13.2,13.9,14.8,12.5,14.2,14.6,15.6,15.1,15.4,16.4,16.7]},
      "UTTAR PRADESH": {
        "percapita":[2.41,2.35,2.48,2.67,2.67,2.97,3.1,3.05,3.23,3.46,3.94,3.97,4.19,4.01,3.93,3.67,3.67,4.15,4.12,4.35,3.75,3.36,3.79,4.75,5.52,3.83,4.06,4.17,4.08,4.48,4.41,4.52,4.45],
        "ticket":[1546,1515,1443,1388,1388,1432,1512,1493,1444,1485,1406,1409,1326,1314,1334,1304,1304,1362,1394,1382,1397,1437,1393,1324,1300,1274,1278,1242,1274,1352,1362,1352,1362],
        "volume":[612.8,596.1,630.3,678.4,678.4,753.0,786.8,774.2,821.2,877.8,1000.0,1007.1,1064.6,1018.7,997.0,932.0,932.0,1054.6,1044.8,1105.7,952.1,852.2,962.1,1206.8,1401.4,972.3,1031.9,1059.4,1036.1,1136.2,1118.9,1147.6,1130.5]},
      "UTTARAKHAND": {
        "percapita":[6.73,6.26,6.2,6.45,6.45,7.58,7.11,6.53,6.76,6.69,7.61,8.4,9.01,8.48,7.68,7.47,7.47,9.37,8.89,9.01,7.85,7.09,8.32,9.93,11.16,8.71,8.8,8.58,8.53,9.45,9.07,9.42,9.18],
        "ticket":[1406,1435,1373,1310,1310,1367,1429,1375,1375,1374,1282,1268,1289,1291,1283,1248,1248,1301,1305,1289,1306,1288,1260,1228,1248,1232,1212,1193,1214,1319,1291,1292,1317],
        "volume":[85.3,79.4,78.5,81.7,81.7,96.1,90.0,82.7,85.7,84.8,96.4,106.4,114.2,107.4,97.3,94.7,94.7,118.7,112.6,114.1,99.5,89.8,105.4,125.8,141.4,110.4,111.5,108.7,108.0,119.8,114.9,119.4,116.3]},
      "WEST BENGAL": {
        "percapita":[2.44,2.53,2.68,2.65,2.65,2.97,2.9,2.81,3.09,3.28,3.57,3.58,3.75,3.9,3.98,3.88,3.88,4.43,4.26,4.64,3.95,3.34,3.76,4.63,5.36,3.67,3.94,4.04,4.13,4.14,4.16,4.43,4.57],
        "ticket":[1830,1811,1730,1706,1706,1702,1718,1751,1733,1734,1728,1678,1636,1616,1598,1550,1550,1558,1561,1579,1587,1572,1593,1498,1503,1448,1460,1426,1484,1456,1467,1486,1493],
        "volume":[263.5,273.8,289.6,286.1,286.1,321.2,313.0,304.0,334.0,354.8,386.0,387.1,404.8,421.2,429.8,419.6,419.6,478.4,460.4,501.8,427.1,361.1,405.8,500.1,579.1,396.8,425.5,436.2,446.2,447.8,449.7,478.7,493.6]},
    }
    # fmt: on
    return {
        state: {"months": months, **series}
        for state, series in raw.items()
    }


# ══════════════════════════════════════════════════════════════════════════════
# ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════════

STATE_DISPLAY_NAMES = {
    "ANDAMAN & NICOBAR": "Andaman & Nicobar",
    "ANDHRA PRADESH":    "Andhra Pradesh",
    "ARUNACHAL PRADESH": "Arunachal Pradesh",
    "ASSAM":             "Assam",
    "BIHAR":             "Bihar",
    "CHANDIGARH":        "Chandigarh",
    "CHHATTISGARH":      "Chhattisgarh",
    "DELHI":             "Delhi",
    "GOA":               "Goa",
    "GUJARAT":           "Gujarat",
    "HARYANA":           "Haryana",
    "HIMACHAL PRADESH":  "Himachal Pradesh",
    "JAMMU AND KASHMIR": "Jammu And Kashmir",
    "JHARKHAND":         "Jharkhand",
    "KARNATAKA":         "Karnataka",
    "KERALA":            "Kerala",
    "LADAKH":            "Ladakh",
    "MADHYA PRADESH":    "Madhya Pradesh",
    "MAHARASHTRA":       "Maharashtra",
    "MANIPUR":           "Manipur",
    "MEGHALAYA":         "Meghalaya",
    "MIZORAM":           "Mizoram",
    "NAGALAND":          "Nagaland",
    "ODISHA":            "Odisha",
    "PUDUCHERRY":        "Puducherry",
    "PUNJAB":            "Punjab",
    "RAJASTHAN":         "Rajasthan",
    "SIKKIM":            "Sikkim",
    "TAMIL NADU":        "Tamil Nadu",
    "TELANGANA":         "Telangana",
    "TRIPURA":           "Tripura",
    "UTTAR PRADESH":     "Uttar Pradesh",
    "UTTARAKHAND":       "Uttarakhand",
    "WEST BENGAL":       "West Bengal",
}


def generate(output_path: Path, embeds: bool = False, embeds_dir: Path = Path("embeds")) -> None:
    """Build and write the dashboard HTML, and optionally the embed chart files."""
    print("Building charts…")
    pc_data    = get_per_capita_data()
    conc_data  = get_concentration_data()
    growth_data= get_growth_data()
    arch_data  = get_archetype_data()
    tick_data  = get_ticket_data()
    int_data   = get_intensity_data()
    map_data   = get_map_data()
    ts_data    = get_state_time_series()
    states_all = sorted(ts_data.keys())

    pc_json    = build_pc_bar(pc_data)
    conc_json  = build_concentration(conc_data)
    growth_json= build_growth_bar(growth_data)
    scat_json  = build_archetype_scatter(arch_data)
    tick_json  = build_ticket_bar(tick_data)
    int_json   = build_intensity_scatter(int_data)

    state_options = "\n".join(
        f'        <option value="{k}">{v}</option>'
        for k, v in STATE_DISPLAY_NAMES.items()
        if k in ts_data
    )

    html = HTML_TEMPLATE
    html = html.replace("{STATE_OPTIONS}", state_options)
    html = html.replace("{PLACEHOLDER_PC}",            json.dumps(pc_json))
    html = html.replace("{PLACEHOLDER_CONC}",          json.dumps(conc_json))
    html = html.replace("{PLACEHOLDER_GROWTH}",        json.dumps(growth_json))
    html = html.replace("{PLACEHOLDER_SCAT}",          json.dumps(scat_json))
    html = html.replace("{PLACEHOLDER_TICK}",          json.dumps(tick_json))
    html = html.replace("{PLACEHOLDER_SCAT_INTENSITY}",json.dumps(int_json))
    html = html.replace("{PLACEHOLDER_MAP_DATA}",      json.dumps(map_data))
    html = html.replace("{PLACEHOLDER_STATE_DATA}",    json.dumps(ts_data))
    html = html.replace("{PLACEHOLDER_STATES_ALL}",    json.dumps(states_all))

    output_path.write_text(html, encoding="utf-8")
    size_kb = output_path.stat().st_size / 1024
    print(f"✓ Dashboard written → {output_path}  ({size_kb:.0f} KB)")

    if embeds:
        print("\nBuilding embed charts…")
        generate_embeds(
            embeds_dir=embeds_dir,
            pc_json=pc_json,
            conc_json=conc_json,
            growth_json=growth_json,
            scat_json=scat_json,
            tick_json=tick_json,
            int_json=int_json,
            ts_data=ts_data,
        )


# ── Single-chart embed HTML template ──────────────────────────────────────────
_EMBED_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:#f5f2ed}}
#chart{{width:100%;height:{height}px}}
</style>
</head>
<body>
<div id="chart"></div>
<script>
const DATA = {json_data};
Plotly.newPlot('chart', DATA.data, DATA.layout, {{responsive:true,displayModeBar:false}});
</script>
</body>
</html>
"""

_EMBED_TS_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>State UPI Deep Dive</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:#f5f2ed;font-family:'DM Mono',monospace}}
body{{padding:14px}}
.row{{display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap}}
.lbl{{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#8a9bb0}}
select{{padding:8px 14px;font-family:'DM Mono',monospace;font-size:11px;
  border:1px solid #e8e3db;border-radius:8px;background:#fff;
  color:#1c2533;cursor:pointer;min-width:220px;outline:none}}
.stack{{display:flex;flex-direction:column;gap:8px}}
.card{{background:#fff;border:1px solid #e8e3db;border-radius:12px;overflow:hidden;padding:4px}}
</style>
</head>
<body>
<div class="row">
  <span class="lbl">Select state</span>
  <select id="sel" onchange="render(this.value)">{options}</select>
</div>
<div class="stack">
  <div class="card"><div id="ts-pc"></div></div>
  <div class="card"><div id="ts-ticket"></div></div>
  <div class="card"><div id="ts-vol"></div></div>
</div>
<script>
const SD = {state_data};
const cfg = {{responsive:true,displayModeBar:false}};
function layout(title,yt,color){{
  return {{
    paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
    font:{{family:'DM Mono,monospace',color:'#1c2533',size:10}},
    margin:{{l:55,r:16,t:44,b:64}},
    title:{{text:title,font:{{family:'DM Mono,monospace',size:11,color:'#1c2533'}},x:0}},
    xaxis:{{type:'category',gridcolor:'#e8e3db',tickfont:{{color:'#8a9bb0',size:8}},
            tickangle:-45,zeroline:false,automargin:true}},
    yaxis:{{title:{{text:yt,font:{{color:'#8a9bb0',size:10}}}},
            gridcolor:'#e8e3db',tickfont:{{color:'#4a5568'}},zeroline:false,automargin:true}},
    height:210,showlegend:false,
    hoverlabel:{{bgcolor:'#1c2533',font:{{family:'DM Mono,monospace',color:'#fff',size:11}}}},
  }};
}}
function render(state){{
  const d=SD[state];if(!d)return;
  const t=state.split(' ').map(w=>w[0].toUpperCase()+w.slice(1).toLowerCase()).join(' ');
  const rgba=(h,a)=>`rgba(${{parseInt(h.slice(1,3),16)}},${{parseInt(h.slice(3,5),16)}},${{parseInt(h.slice(5,7),16)}},${{a}})`;
  [
    {{id:'ts-pc',    y:d.percapita,color:'#1d6fa4',title:'UPI txns per person per month — '+t,yt:'Txns / person / month'}},
    {{id:'ts-ticket',y:d.ticket,   color:'#c8401a',title:'Average transaction size (Rs) — '+t,yt:'Rs per transaction'}},
    {{id:'ts-vol',   y:d.volume,   color:'#1e7d52',title:'Total monthly transactions (Mn) — '+t,yt:'Transactions (Mn)'}},
  ].forEach(c=>Plotly.react(c.id,[{{
    x:d.months,y:c.y,type:'scatter',mode:'lines+markers',
    line:{{color:c.color,width:2.5,shape:'spline'}},
    marker:{{size:4,color:c.color,line:{{width:1.5,color:'#fff'}}}},
    fill:'tozeroy',fillcolor:rgba(c.color,0.07),
    hovertemplate:'<b>%{{x}}</b><br>'+c.yt+': %{{y}}<extra></extra>',
  }}],layout(c.title,c.yt,c.color),cfg));
}}
render(Object.keys(SD)[0]);
</script>
</body>
</html>
"""


def generate_embeds(
    embeds_dir: Path,
    pc_json:    dict,
    conc_json:  dict,
    growth_json:dict,
    scat_json:  dict,
    tick_json:  dict,
    int_json:   dict,
    ts_data:    dict,
) -> None:
    """
    Write seven minimal single-chart HTML files for Wix iframe embedding.

    Files produced
    --------------
    chart-pc-bar.html        — per capita ranking bar chart
    chart-conc.html          — concentration line chart
    chart-growth.html        — growth trajectory bar chart
    chart-scat.html          — market archetype scatter
    chart-tick.html          — ticket size decline bar chart
    chart-scat-intensity.html— GSDP vs UPI intensity scatter
    chart-state-ts.html      — state deep-dive time series (interactive selector)

    Wix embed instructions
    ----------------------
    Add → Embed → HTML iframe → paste URL of each file hosted on Netlify.
    Recommended iframe heights match the height_px values below.
    """
    embeds_dir.mkdir(parents=True, exist_ok=True)

    # (filename, chart_json, title, height_px)
    static_charts = [
        ("chart-pc-bar.html",         pc_json,     "Per Capita UPI Ranking",              680),
        ("chart-conc.html",           conc_json,   "Top 5 States Concentration Trend",    460),
        ("chart-growth.html",         growth_json, "Year-on-Year Growth by State",         740),
        ("chart-scat.html",           scat_json,   "Market Archetypes: Volume vs Value",   560),
        ("chart-tick.html",           tick_json,   "Transaction Size Decline",             720),
        ("chart-scat-intensity.html", int_json,    "UPI Adoption vs Economic Development", 580),
    ]

    for fname, chart_json, title, height in static_charts:
        html = _EMBED_TEMPLATE.format(
            title=title,
            height=height,
            json_data=json.dumps(chart_json),
        )
        (embeds_dir / fname).write_text(html, encoding="utf-8")
        print(f"  ✓ {fname}")

    # State time-series — needs STATE_DATA and a state selector
    state_options = "".join(
        f'<option value="{k}">{v}</option>'
        for k, v in STATE_DISPLAY_NAMES.items()
        if k in ts_data
    )
    ts_html = _EMBED_TS_TEMPLATE.format(
        options=state_options,
        state_data=json.dumps(ts_data),
    )
    (embeds_dir / "chart-state-ts.html").write_text(ts_html, encoding="utf-8")
    print(f"  ✓ chart-state-ts.html")
    print(f"\n✓ 7 embed files written → {embeds_dir}/")
    print(
        "\nWix iframe heights:\n"
        "  chart-pc-bar.html         680px\n"
        "  chart-conc.html           460px\n"
        "  chart-growth.html         740px\n"
        "  chart-scat.html           560px\n"
        "  chart-tick.html           720px\n"
        "  chart-scat-intensity.html 580px\n"
        "  chart-state-ts.html       720px"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out",  default="upi_dashboard.html",
                        help="Output file path (default: upi_dashboard.html)")
    parser.add_argument("--open", action="store_true",
                        help="Open in browser after generating")
    parser.add_argument("--embeds", action="store_true",
                        help="Also generate single-chart embed HTML files for Wix iframes")
    parser.add_argument("--embeds-dir", default="embeds",
                        help="Directory for embed files (default: embeds/)")
    args = parser.parse_args()

    output = Path(args.out)
    generate(output, embeds=args.embeds, embeds_dir=Path(args.embeds_dir))

    if args.open:
        webbrowser.open(output.resolve().as_uri())


if __name__ == "__main__":
    main()
