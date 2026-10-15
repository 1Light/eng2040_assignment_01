# ENG2040 Assignment 01

A reproducible pipeline that turns a raw marketplace SQL dump into a model-ready feature table for predicting late deliveries.

The pipeline repairs defective values, builds one row per order, creates delivery labels, analyses late deliveries, and writes a numerical feature table. Everything rebuilds from `data/raw.sql` with one command.

All findings concern the supplied modified extract. Observed associations do not establish causation.

## Requirements

Python 3.10 or later, on macOS or Linux.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

That installs pandas, NumPy and Matplotlib, pinned to exact versions. Nothing else is needed. SQL runs through Python's built-in SQLite support, so the `sqlite3` command-line tool is not required.

The pipeline assumes a Unix-like system. Memory measurement uses `os.wait4`, which Windows does not provide.

## Quick start

From the repository root:

```bash
python3 run_pipeline.py
```

The last verified run completed all 21 stages in 40.7 seconds. Generated outputs are deleted before each rebuild, so a successful run never depends on stale files.

Three files record what happened:

| File | What it tells you |
|---|---|
| `outputs/evidence/pipeline_execution.csv` | which stages ran, how long each took, and whether each passed |
| `outputs/evidence/task5_environment.csv` | the Python, package and SQLite versions it ran on |
| `outputs/evidence/task5_pipeline_resource_comparison.csv` | how much time, memory and disk each stage used |

## Project structure

```text
eng2040_assignment_01/
├── data/raw.sql              supplied SQL dump, unmodified
├── setup_db.py               builds marketplace.sqlite from raw.sql
├── run_pipeline.py           runs everything
├── requirements.txt
├── sql/                      the SQL the pipeline executes
├── src/
│   ├── common/               shared SQL runner
│   ├── task1/                order-level build and loading benchmark
│   ├── task2/                repairs, timestamp checks, labels
│   ├── task3/                exploratory analysis
│   ├── task4/                feature engineering
│   └── task5/                resource profiling and environment capture
├── docs/decisions.md         why each decision was made, with its evidence
└── outputs/                  everything the pipeline generates
```

`marketplace.sqlite` and `outputs/intermediate/` are generated and are listed in `.gitignore`. The pipeline recreates them.

## Pipeline stages

Seven stages produce data. The other fourteen validate it or measure resources.

| Stage | Script | Reads | Writes | One row is |
|---|---|---|---|---|
| Build source database | `setup_db.py` | `data/raw.sql` | `marketplace.sqlite` | depends on the table |
| Item repair | `src/task2/task2_clean_items.py` | `marketplace.sqlite` | `outputs/intermediate/items_clean.sqlite` | one purchased item |
| Catalogue repair | `src/task2/task2_clean_products.py` | `marketplace.sqlite` | `outputs/intermediate/catalogue_clean.sqlite` | one product, or one seller |
| Order-level build | `sql/task1_build_order_level.sql` | the three above | `outputs/intermediate/order_level.sqlite` | one order |
| Clean orders | `src/task2/task2_clean_orders.py` | `order_level.sqlite` | `outputs/intermediate/order_level_clean.sqlite` | one order, with its delivery label |
| Exploratory analysis | `src/task3/task3_exploratory_analysis.py` | `order_level_clean.sqlite` | `outputs/tables/`, `outputs/figures/` | depends on the table |
| Feature build | `src/task4/task4_build_features.py` | `order_level_clean.sqlite` | `outputs/final/` | one order with a usable label |

Sizes after a full run:

| Table | Rows | Columns |
|---|---:|---:|
| `order_items_clean` | 22,662 | 11 |
| `products_clean` | 11,334 | 20 |
| `sellers_clean` | 2,071 | 6 |
| `order_level` | 20,000 | 46 |
| `order_level_clean` | 20,000 | 56 |
| `task4_features.csv` | 15,843 | 73 |

The two repair stages run before the order-level build. Grouping sums the items, so a defective value has to be found while the individual items are still visible.

## Loading the outputs

The intermediate datasets are SQLite databases. Open one with `sqlite3.connect`, then query the table inside it.

```python
import sqlite3
import pandas as pd

orders = pd.read_sql(
    "SELECT * FROM order_level_clean",
    sqlite3.connect("outputs/intermediate/order_level_clean.sqlite"),
)
```

Substitute any database and table from this list:

| Database | Tables |
|---|---|
| `outputs/intermediate/items_clean.sqlite` | `order_items_clean` |
| `outputs/intermediate/catalogue_clean.sqlite` | `products_clean`, `sellers_clean` |
| `outputs/intermediate/order_level.sqlite` | `order_level` |
| `outputs/intermediate/order_level_clean.sqlite` | `order_level_clean` |

Everything else is CSV.

```python
features = pd.read_csv("outputs/final/task4_features.csv")
order_ids = pd.read_csv("outputs/final/task4_order_ids.csv")
labels = pd.read_csv("outputs/final/task4_labels.csv")
```

Those three files are row-aligned. Row 1 of each belongs to the same order.

## Outputs

| Folder | Contents |
|---|---|
| `outputs/final/` | the feature table, order IDs and labels |
| `outputs/tables/` | the Task 3 results, including the numbers behind each chart |
| `outputs/figures/` | the Task 3 charts |
| `outputs/evidence/` | validation results, repair records, audits, resource and environment records |
| `outputs/intermediate/` | working databases each stage passes to the next |

`outputs/evidence/task4_feature_dictionary.csv` describes every column in the feature table: its name, how it is represented, what it means, and which column in `order_level_clean` it was derived from.

## Checks

The pipeline checks its own work at every stage.

| Check | What it verifies | Output |
|---|---|---|
| Data-quality profile | what was wrong with the raw data | `outputs/evidence/task2_data_quality_profile.txt` |
| Order-level preservation | nothing was lost or duplicated in the build | `outputs/evidence/task1_validation.txt` |
| Cleaned-data validation | every order kept, every label consistent | `outputs/evidence/task2_clean_validation.txt` |
| Task 3 robustness | the findings hold under different rules | `outputs/evidence/task3_*_robustness.csv`, `task3_*_sensitivity.csv` |
| Feature validation | every feature recomputed from source | `outputs/evidence/task4_feature_validation.csv` |

The feature validation runs 107 checks and all of them pass.

## Decisions

`docs/decisions.md` records every substantive decision. Each one states the evidence behind it, the reasoning, and the rule the pipeline follows. Any figure reported in this project can be traced from there to the file that generates it.