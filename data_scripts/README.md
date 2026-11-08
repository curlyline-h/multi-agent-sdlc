# Multi-Agent SDLC Benchmark — Data Pipeline & Dataset Card

This directory (`data_scripts/`) contains the data collection, merging, cleaning, feature engineering, stratified splitting, and Exploratory Data Analysis (EDA) pipeline for the **40-scenario Multi-Agent SDLC Benchmark**.

---

## 1. Pipeline Execution Order

Run the scripts from the repository root in the following order:

```bash
# Step 1: Collect and normalize 15 GitHub feature-request scenarios -> data/raw/github_issues.json
python -m data_scripts.collect_github_issues

# Step 2: Merge 25 manual scenarios + 15 GitHub scenarios -> data/raw/merged_scenarios.json
python -m data_scripts.build_dataset

# Step 3: Clean missing fields, deduplicate, and flag 1.5x IQR length outliers -> data/processed/benchmark.json
python -m data_scripts.clean

# Step 4: Extract OneHot, MinMaxScaler, and TF-IDF features -> data/processed/features_summary.json
python -m data_scripts.features

# Step 5: Create stratified 70/15/15 dev/val/test splits (seed=42) -> data/splits/{dev,val,test}.json
python -m data_scripts.split

# Step 6: Generate EDA visualizations -> reports/figures/*.png
python -m data_scripts.eda

# Step 7: Verify dataset schema, DAG integrity, and split partitioning
pytest agents/tests/unit/test_dataset.py
```

---

## 2. Dataset Card

### Dataset Summary
The **Multi-Agent SDLC Benchmark** evaluates end-to-end software engineering agents across **40 realistic full-stack application scenarios**. Each scenario pairs a natural-language software requirement specification with ground-truth functional requirements, architectural components, a dependency-ordered task Directed Acyclic Graph (DAG) assigned to specialized SDLC roles (`database_engineer`, `backend`, `frontend`, `qa`, `security`, `devops`), acceptance criteria, security requirements, and verification test cases.

### Composition & Provenance
| Attribute | Value |
| :--- | :--- |
| **Total Scenarios** | `40` (`scen_001` – `scen_040`) |
| **Hand-Written (`manual`)** | `25` scenarios (`62.5%`, 5 per category) |
| **GitHub Issues (`github`)** | `15` scenarios (`37.5%`, 3 per category, adapted from real OSS feature requests) |
| **Application Categories** | `crud` (8), `rest_api` (8), `ecommerce` (8), `auth` (8), `db_app` (8) |
| **Stratified Splits (`seed=42`)** | `dev.json`: 28 (`70%`) \| `val.json`: 6 (`15%`) \| `test.json`: 6 (`15%`) |

### Scenario JSON Schema
Every scenario object in `data/processed/benchmark.json` and `data/splits/*.json` conforms to the following schema:

```json
{
  "id": "scen_001",
  "category": "crud | rest_api | ecommerce | auth | db_app",
  "source": "manual | github",
  "requirement": "Natural-language problem specification describing the target system...",
  "expected_functional_reqs": [
    "Functional requirement 1",
    "Functional requirement 2"
  ],
  "expected_components": [
    "database_schema",
    "backend_api",
    "frontend_ui"
  ],
  "tasks": [
    {
      "title": "Design relational schema",
      "role": "database_engineer",
      "depends_on": []
    },
    {
      "title": "Implement REST endpoints",
      "role": "backend",
      "depends_on": ["Design relational schema"]
    }
  ],
  "acceptance_criteria": [
    "Verifiable HTTP status and state transition criterion"
  ],
  "security_reqs": [
    "Authentication, authorization, or input validation requirement"
  ],
  "test_cases": [
    "test_case_identifier"
  ],
  "requirement_char_length": 312,
  "is_length_outlier": false
}
```

### Cleaning & Quality Controls (`data_scripts/clean.py`)
1. **Missing-Key Remediation:** Drops malformed records lacking `id`, `category`, or `requirement`; populates default list containers for optional array fields.
2. **Normalized Text Deduplication:** Strips punctuation and normalizes whitespace/casing to eliminate duplicate requirement specifications.
3. **DAG Reference Validation:** Ensures every task's `depends_on` list references an existing task `title` within the same scenario and contains no self-loops.
4. **Length Outlier Flagging:** Computes Tukey fences ($[Q_1 - 1.5 \times \text{IQR},\; Q_3 + 1.5 \times \text{IQR}]$) over character lengths and records `is_length_outlier` on every scenario.

### Feature Representation (`data_scripts/features.py`)
- **Categorical Encoding (`OneHotEncoder`):** 7 binary features across `category` (5 classes) and `source` (2 classes).
- **Complexity Scaling (`MinMaxScaler`):** 6 normalized structural features (`char_length`, `word_count`, `functional_req_count`, `task_count`, `max_dag_depth`, `security_req_count`).
- **Lexical Representation (`TfidfVectorizer`):** 64 sublinear TF-IDF unigram/bigram features extracted from requirement specifications.

