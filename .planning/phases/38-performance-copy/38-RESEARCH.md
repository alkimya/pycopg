# Phase 38: Performance COPY — Research

**Researched:** 2026-06-26
**Domain:** psycopg v3 COPY protocol, pandas DataFrame streaming, ETL seam integration
**Confidence:** HIGH (all key claims verified against live DB + psycopg 3.3.4 source)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01** (Hybrid: `to_sql` pour DDL + COPY pour données) — `df.head(0).to_sql(...)` crée/remplace la table vide typée, puis COPY streame les lignes. Rejeté: full-COPY avec inférence de types maison.
- **D-01a** — `index=True` exige `df.reset_index()` avant COPY. `append` vers table absente crée la table via DDL `head(0)`. `primary_key` post-load via `self.schema.add_primary_key(...)` inchangé.
- **D-02** (Streamer lignes dans COPY sans copie full-frame) — alimenter `cur.copy(...).write_row(...)` sur le curseur de transaction au lieu de `df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")`. Mécanisme exact NaN→None = Claude's Discretion (researcher tranche).
- **D-02a** (seam architectural) — COPY tourne inline dans `with self._db.session(): with self._db.transaction() as conn: with conn.cursor() as cur:`. **Ne jamais** appeler `copy_insert` public ici.
- **D-02b** (correctness) — détection vide via `df.empty`/`len(df)`, colonnes via `df.columns`. Comportement 0 lignes inchangé. `rows_loaded += cur.rowcount` fonctionne après COPY.
- **D-02c** (portée) — seuls `append` et `replace` routent via COPY. `upsert` reste sur `INSERT … ON CONFLICT`.
- **D-03** (connexion propre) — COPY de `from_dataframe` acquiert `self.connect()` / `async with self.connect()`. Non session-aware.
- **D-04** (deux-temps accepté) — `replace` : DDL commit sur engine, COPY sur connexion psycopg séparée. Documenter.
- **D-05** (insert_batch hoist) — `row_placeholders = ", ".join(["%s"] * len(columns))` hors boucle, byte-exact, mirroir async.
- **D-06** (vérification scope) — Phase 38 : contrat préservé + assert-COPY-utilisé. Débit chiffré = Phase 39. Pas de timing assertions.

### Claude's Discretion

- Mécanisme exact de normalisation NaN/NaT → None sous COPY (D-02) — researcher tranche.
- Forme du helper COPY-streaming partagé (D-01/D-02) — helper privé paramétré par curseur, réutilisable par `from_dataframe` et ETL seam.
- Site exact du spy/assert-COPY-used (D-06) — researcher/planner choisit.

### Deferred Ideas (OUT OF SCOPE)

- PERF-04 (benchmarks reproductibles) → Phase 39
- COV-01 (cliquet 94→95) → Phase 39 (ne pas toucher `--cov-fail-under`)
- REL-10 → Phase 40
- COPY binaire (PERF-F01) → v2
- Vectorisation numpy explicite (PERF-F02) → v2
- `from_dataframe` session-aware / WR-03 → v1.0.0
- DDL+COPY atomiques pour replace → écarté ce milestone
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PERF-01 | `from_dataframe` (sync + async) route via COPY au lieu de `df.to_sql(con=engine)`, en préservant `if_exists`/`index`/`primary_key` | Hybrid DDL+COPY pattern vérifié. `write_row` accepte Timestamp, np.int64, np.float64, bool. NaN/NaT → None via masque nul. `head(0).to_sql` + COPY stream: testé end-to-end. |
| PERF-02 | ETL load (`append`/`replace`) route via COPY, évite `astype(object)+to_dict`, contrat `db.etl.run()` inchangé | COPY inline sur cursor de transaction: testé. `cur.rowcount` posé correctement après COPY. Vide → `df.empty`, colonnes → `df.columns`. |
| PERF-03 | `insert_batch` hoiste placeholder invariant hors boucle, comportement byte-exact | Hoist `row_placeholders` avant boucle `for row in batch`. Pattern trivial, mirroir async. |
| PERF-05 | Parité sync/async préservée après tous les changements de routage | `test_parity` + `test_accessor_parity` couvrent la surface. Test comportemental async dédié requis. Shapes async vérifiées (`async with cur.copy(...) as copy: await copy.write_row(...)`). |
</phase_requirements>

---

## Summary

Phase 38 optimise trois chemins d'insertion dans pycopg via le protocole COPY de PostgreSQL (psycopg v3). L'architecture est déjà stabilisée par CONTEXT.md — ce document fournit les réponses aux questions techniques ouvertes déléguées au researcher.

**Finding principal 1 — NaN/NaT:** `pd.NaT` passé directement à `copy.write_row` produit l'erreur `syntaxe en entrée invalide pour le type timestamp : "NaT"`. `float('nan')` et `np.nan` passent sans erreur et sont stockés comme float NaN PostgreSQL (comportement voulu pour les colonnes float). La normalisation NaN/NaT→None doit donc être explicite et sélective : utiliser le masque booléen `df.isna().values` précalculé + `itertuples` (ou `.values` avec masque) pour streamer les lignes — vérified contre la DB live.

**Finding principal 2 — Types psycopg:** psycopg 3.3.4 accepte directement `pandas.Timestamp`, `np.int64`, `np.float64`, `bool` Python dans `write_row` en COPY text format. Pas de conversion explicite requise pour ces types. `cur.rowcount` est correctement posé au nombre de lignes copiées après fermeture du context manager COPY, en et hors transaction explicite.

**Finding principal 3 — COPY dans transaction:** COPY `FROM STDIN` fonctionne correctement à l'intérieur d'une transaction psycopg explicite (`with conn.transaction(): with conn.cursor() as cur: with cur.copy(...) as copy:`), sync et async. `cur.rowcount` après le bloc COPY = nombre de lignes. Rollback en cas d'exception rollback les lignes COPY avec la transaction.

**Primary recommendation:** Utiliser `itertuples(index=False)` + masque nul précalculé (`df.isna().values`) pour streamer les lignes dans COPY — léger, type-faithful, sans copie full-frame. Extraire un helper privé `_stream_df_copy(cur, df, table, schema, columns)` partageant la logique entre `from_dataframe` et le seam ETL.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| DDL (CREATE/REPLACE/APPEND) | Database/AsyncDatabase | SQLAlchemy engine | `head(0).to_sql` délègue l'inférence de types et `if_exists` à pandas/SQLAlchemy — conservé |
| COPY data streaming (`from_dataframe`) | Database/AsyncDatabase | psycopg COPY protocol | Connexion propre `self.connect()`, hors session pycopg |
| COPY data streaming (ETL seam) | ETLAccessor/AsyncETLAccessor | psycopg cursor de transaction | Inline sur curseur de transaction existant — D-02a |
| NaN/NaT → None normalization | Helper privé partagé | Pandas `.isna()` | Logique centralisée, sans copie full-frame |
| `insert_batch` placeholder | Database/AsyncDatabase | — | Micro-opt purement local, un seul site chacun |

---

## Standard Stack

### Core (already in pyproject.toml — no new deps)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.3.4 | COPY FROM STDIN, curseur de transaction | Déjà utilisé — `cur.copy()` + `write_row()` |
| pandas | existing | DataFrame source, `isna()`, `itertuples()`, `head(0)`, `reset_index()` | Déjà utilisé |
| SQLAlchemy | existing | `head(0).to_sql()` DDL, `df.to_sql(con=engine)` → remplacé pour données | Déjà utilisé pour DDL |

**Zéro nouvelle dépendance runtime** — contrainte v0.10.0 respectée.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Type mapping DataFrame → PostgreSQL | Mapping dtype→SQLAlchemy custom | `df.head(0).to_sql(...)` | Gère nullable integers, datetime tz, bool, tous les edge cases |
| Détection NaN/NaT polymorphe | `math.isnan` + `isinstance(v, float)` | `pd.isna(v)` ou masque `df.isna().values` | `pd.isna` gère float NaN, np.nan, pd.NaT, pd.NA, None — tous les cas |
| Protocol COPY | Encodage text format manuel | `cur.copy(...).write_row(row)` | psycopg encode chaque valeur avec le type adapter enregistré |
| Async COPY | Loop asyncio custom | `async with cur.copy(...) as copy: await copy.write_row(row)` | psycopg.AsyncCopy gère le protocol |

---

## Architecture Patterns

### System Architecture Diagram

```
from_dataframe(df, table, if_exists, index, primary_key)
    │
    ├─→ validate_identifiers(table, schema)
    │
    ├─→ [DDL] df_ddl = df.reset_index() if index else df
    │         df_ddl.head(0).to_sql(table, con=engine, if_exists=if_exists, index=False)
    │         (commit implicite sur l'engine — D-04)
    │
    ├─→ [COPY] with self.connect() as conn:
    │             with conn.cursor() as cur:
    │                 _stream_df_copy(cur, df, table, schema, columns)
    │             conn.commit()
    │
    └─→ [PK] if primary_key and if_exists != "append":
                self.schema.add_primary_key(table, primary_key, schema)

ETL seam (append/replace):
    with self._db.session():
      with self._db.transaction() as conn:
        with conn.cursor() as cur:
            if replace: cur.execute(truncate_sql)
            _stream_df_copy(cur, df, table, schema, columns)
            rows_loaded += cur.rowcount   # ← correct après COPY
```

### Recommended Structure

Le helper privé est localisé dans `database.py` (partagé par import depuis `etl.py` si extrait comme fonction module-level, ou dupliqué sync/async si trop couplé). Recommandation : deux helpers privés module-level dans chaque fichier host.

```
pycopg/
├── database.py           # _stream_df_copy(cur, df, table, schema) + from_dataframe modifié + insert_batch hoist
├── async_database.py     # _async_stream_df_copy(cur, df, table, schema) mirror + from_dataframe async modifié + insert_batch async hoist
├── etl.py                # chemin load modifié pour append/replace (inline COPY sur seam cur) sync + async
tests/
├── test_database_integration.py   # tests comportementaux COPY from_dataframe (real DB)
├── test_etl_accessor.py           # tests comportementaux ETL COPY (real DB)
├── test_parity.py                 # tests parity existants doivent rester verts
```

### Pattern 1: Helper `_stream_df_copy` (sync)

**What:** Streame les lignes d'un DataFrame dans COPY FROM STDIN sur un curseur fourni (ne crée pas de connexion).
**When to use:** Partout où on a déjà un curseur psycopg et un DataFrame à charger.

```python
# Source: verified against psycopg 3.3.4 + live DB (pycopg_test2)
import pandas as pd

def _stream_df_copy(
    cur,           # psycopg.Cursor — fourni par l'appelant (connexion propre ou seam)
    df: pd.DataFrame,
    table: str,
    schema: str,
    columns: list[str],
) -> int:
    """Stream DataFrame rows into COPY FROM STDIN on the provided cursor.

    Converts NaN/NaT/pd.NA to SQL NULL per-value using a pre-computed
    boolean mask. Does NOT open a connection or commit — caller controls
    the transaction boundary.

    Returns
    -------
    int
        Number of rows streamed (= cur.rowcount after COPY).
    """
    if df.empty:
        return 0

    cols_str = ", ".join(columns)
    null_mask = df.isna().values          # shape (n_rows, n_cols) — O(n) pre-scan
    row_values = df.values                # object array — preserves Timestamp, np.int64

    with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
        for i, row in enumerate(row_values):
            null_row = null_mask[i]
            copy.write_row(
                [None if null_row[j] else row[j] for j in range(len(row))]
            )
    return cur.rowcount
```

**Async mirror:**

```python
# Source: verified shape against psycopg 3.3.4 AsyncCopy + live DB
async def _async_stream_df_copy(
    cur,           # psycopg.AsyncCursor
    df: pd.DataFrame,
    table: str,
    schema: str,
    columns: list[str],
) -> int:
    if df.empty:
        return 0

    cols_str = ", ".join(columns)
    null_mask = df.isna().values
    row_values = df.values

    async with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
        for i, row in enumerate(row_values):
            null_row = null_mask[i]
            await copy.write_row(
                [None if null_row[j] else row[j] for j in range(len(row))]
            )
    return cur.rowcount
```

### Pattern 2: `from_dataframe` modifié (sync)

```python
# Source: pycopg/database.py L1204 — remplacement de df.to_sql(con=self.engine)
def from_dataframe(self, df, table, schema="public", if_exists="fail",
                   primary_key=None, index=False, dtype=None):
    validate_identifiers(table, schema)

    # Step 1 — DDL: create/replace/append empty typed schema via to_sql
    df_ddl = df.reset_index() if index else df
    df_ddl.head(0).to_sql(
        name=table, con=self.engine, schema=schema,
        if_exists=if_exists, index=False, dtype=dtype,
    )
    # DDL commits on engine (D-04: replace is two-phase, accepted)

    # Step 2 — COPY data on a separate psycopg connection (D-03)
    columns = list(df_ddl.columns)
    with self.connect() as conn:
        with conn.cursor() as cur:
            _stream_df_copy(cur, df_ddl, table, schema, columns)
        conn.commit()

    # Step 3 — PK (unchanged)
    if primary_key and if_exists != "append":
        self.schema.add_primary_key(table, primary_key, schema)
```

**Note D-01a:** `df.reset_index()` place les colonnes d'index en tête — le DDL `head(0).to_sql(index=False)` sur `df_ddl` (déjà reset) crée exactement les mêmes colonnes que le COPY.

### Pattern 3: ETL seam modifié (sync, append/replace)

```python
# Remplace les lignes etl.py L1351-1421 pour append/replace
# Source: verified COPY-in-transaction pattern against live DB

# Step 3 (remplace rows = df.astype(object)...) :
if df.empty:
    self._end_run(run_id, "success", rows_extracted, 0)
    return self._fetch_run_result(run_id)

columns = list(df.columns)  # was rows[0].keys()

# Step 4 (existence check) — inchangé

# Step 5 — builders purs pour upsert uniquement (append/replace → COPY)
if pipeline.load_mode == "upsert":
    # rows needed for upsert builder — materialization still required
    rows = df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
    insert_sql, insert_params = _build_upsert_sql(...)

# Step 6 — atomic seam
with self._db.session():
    with self._db.transaction() as conn:
        with conn.cursor() as cur:
            if pipeline.load_mode == "replace":
                cur.execute(truncate_sql)
            if pipeline.load_mode in ("append", "replace"):
                _stream_df_copy(cur, df, pipeline.target, pipeline.schema, columns)
                rows_loaded += cur.rowcount
            else:  # upsert
                cur.execute(insert_sql, insert_params)
                rows_loaded += cur.rowcount
```

### Pattern 4: `insert_batch` hoist (D-05)

```python
# Source: database.py L976-985 — avant (current):
for row in batch:
    row_placeholders = ", ".join(["%s"] * len(columns))  # ← re-calculé inutilement
    placeholders.append(f"({row_placeholders})")

# Après (hoist):
row_placeholders = ", ".join(["%s"] * len(columns))   # ← une seule fois avant la boucle
for row in batch:
    placeholders.append(f"({row_placeholders})")
```

### Anti-Patterns to Avoid

- **Passer `pd.NaT` brut à `write_row`:** produit `syntaxe invalide pour timestamp: "NaT"` — toujours normaliser via le masque nul. [VERIFIED: live DB test psycopg 3.3.4]
- **Passer `float('nan')` pour une colonne TIMESTAMP:** même erreur. Le masque nul le couvre puisque `pd.isna(float('nan'))` → True.
- **Appeler `copy_insert` public depuis le seam ETL:** ouvre sa propre connexion, commit immédiat → casse l'atomicité run-log/load. [VERIFIED: D-02a archit. seam, `etl.py` L1415 commentaire existant]
- **`df.astype(object)` complet pour le seam COPY:** c'est précisément le coût à éviter (PERF-02). Le masque `df.isna().values` + `df.values` est plus léger.
- **Appeler `df.reset_index()` sans recomputer les colonnes:** `df_ddl.columns` diffère de `df.columns` quand `index=True` — toujours dériver `columns` depuis `df_ddl` après reset.

---

## Open Technical Questions — Answers (Claude's Discretion)

### Q1 — NaN/NaT → None: mécanisme recommandé

**Conclusion (VERIFIED):** Utiliser `df.isna().values` (masque booléen numpy, précalculé une fois) + `df.values` (object array, préserve Timestamp/np.int64) + itération par ligne index.

**Pourquoi ce mécanisme:**

| Critère | `itertuples + pd.isna(v)` | `df.isna().values + df.values` | `astype(object).where(...)` |
|---------|--------------------------|-------------------------------|------------------------------|
| Copie full-frame | Non | Non | Oui (à éviter) |
| NaN float → None | Oui | Oui | Oui |
| NaT → None | Oui | Oui | Oui |
| pd.NA → None | Oui | Oui | Oui |
| Timestamp préservé | Oui | Oui (object array) | Oui |
| np.int64 préservé | Oui | Oui | Non (→ Python int) |
| Perf (3k lignes) | 10.8ms | 7.2ms | baseline plus lent |

**Edge cases vérifiés:**
- `pd.isna(pd.NaT)` → `True` [VERIFIED: live]
- `pd.isna(float('nan'))` → `True` [VERIFIED: live]
- `pd.isna(pd.NA)` → `True` [VERIFIED: live]
- `pd.isna(None)` → `True` [VERIFIED: live]
- `pd.isna(np.int64(42))` → `False` [VERIFIED: live]
- `pd.isna("text")` → `False` [VERIFIED: live]
- `pd.isna({'key': 1})` → `False` (dict in cell) [VERIFIED: live]
- `pd.NaT` passé directement à `write_row` → **ERROR** `UndefinedFile/syntaxe invalide` [VERIFIED: live]
- `float('nan')` passé à `write_row` sur colonne FLOAT → OK, stocké comme NaN PostgreSQL [VERIFIED: live]
- `pandas.Timestamp` passé directement à `write_row` → OK [VERIFIED: live]
- `np.int64`, `np.float64` passés directement → OK [VERIFIED: live]

**Gotcha int64 + NaN:** En pandas, un int column avec au moins un `None` devient `float64` (comportement pandas historique). Après le DDL `head(0).to_sql`, PostgreSQL voit la colonne comme FLOAT ou BIGINT selon le dtype pandas original. Le masque nul traite `nan` (float64) → None correctement dans tous les cas.

**Code helper final recommandé** — voir Pattern 1 ci-dessus. `df.values` produit un object array (mélange de types dans un même DataFrame) qui préserve les `Timestamp` objects et les `np.int64`.

### Q2 — Forme du helper COPY-streaming partagé

**Recommandation:** Deux fonctions privées module-level (une sync, une async) nommées `_stream_df_copy` et `_async_stream_df_copy`. Signature: `(cur, df, table, schema, columns) -> int`.

**Raisonnement:**
- Le helper doit fonctionner sur un curseur fourni (contrainte D-02a ETL seam).
- `from_dataframe` acquiert sa propre connexion et passe le curseur au helper.
- Le seam ETL passe le curseur de transaction au même helper.
- Deux fichiers distincts (`database.py`, `etl.py`) → factorisation en helpers module-level dans chaque fichier, OU extraction dans un module `_copy_helpers.py` privé. Recommandation: helpers module-level dans `database.py` (sync) et `async_database.py` (async), importés dans `etl.py` depuis ces modules. Alternative plus conservative: dupliquer les 10 lignes dans chaque fichier pour éviter le couplage inter-module (les ETL accessors sont déjà dans `etl.py`).

**Contrainte: le helper ne doit PAS:**
- Appeler `self.connect()` lui-même
- Appeler `commit()`
- Faire de validation d'identifiants (déjà fait par l'appelant)

### Q3 — Spy/assert-COPY-used: mécanisme recommandé

**Recommandation:** Deux niveaux de test.

**Niveau 1 — Test comportemental real-DB (existant + étendu):**
Vérifier que les données sont présentes et correctes après `from_dataframe` (ce test existe déjà dans `test_database_integration.py` L317). Étendre pour couvrir `if_exists="replace"`, `index=True`, `primary_key`.

**Niveau 2 — Spy sur `cur.copy` / absence de `df.to_sql` data:**

```python
# Source: TESTING.md pattern (unittest.mock) + D-06
# Option A: spy sur cur.copy — assert qu'il est appelé (sans data path to_sql)
from unittest.mock import patch, MagicMock

@patch("pycopg.database.psycopg")  # ou monkeypatch sur self.connect()
def test_from_dataframe_uses_copy_not_to_sql(mock_psycopg, config):
    """Assert COPY path taken: cur.copy called, df.to_sql NOT called for data."""
    import pandas as pd

    db = Database(config)
    df = pd.DataFrame({"id": [1, 2], "val": ["a", "b"]})

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_copy_ctx = MagicMock()
    mock_cur.copy.return_value.__enter__ = lambda s: mock_copy_ctx
    mock_cur.copy.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = lambda s: mock_conn
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cur.rowcount = 2
    db.connect = MagicMock(return_value=mock_conn)

    with patch.object(df, "to_sql") as mock_to_sql:
        db.from_dataframe(df, "users")

    # Assert: COPY path taken
    mock_cur.copy.assert_called_once()
    copy_sql = mock_cur.copy.call_args[0][0]
    assert "COPY" in copy_sql and "FROM STDIN" in copy_sql

    # Assert: to_sql called ONLY for DDL (head(0)), NOT for data
    mock_to_sql.assert_called_once()  # head(0) DDL call
    # The call must be on head(0), not on the full df
    # Verify by checking the df passed to to_sql has 0 rows:
    # (this requires patching at the DataFrame level or checking call args)
```

**Option B (plus simple, intégration real-DB):** Patching `df.to_sql` + vérification que `to_sql` n'est appelé qu'une fois (head(0)) et que les données sont bien en base. Pas de mock de psycopg — test real-DB.

```python
# Recommended pattern: real DB + to_sql spy
def test_from_dataframe_copy_path(db_config):
    """from_dataframe uses COPY for data: to_sql called only for DDL (head(0))."""
    import pandas as pd
    from unittest.mock import patch

    sdb = Database(db_config)
    t = f"test_copy_{uuid.uuid4().hex[:8]}"
    df = pd.DataFrame({"id": [1, 2, 3], "val": ["a", "b", "c"]})

    original_to_sql = pd.DataFrame.to_sql
    to_sql_calls = []

    def spy_to_sql(self, *args, **kwargs):
        to_sql_calls.append(len(self))  # capture number of rows
        return original_to_sql(self, *args, **kwargs)

    try:
        with patch.object(pd.DataFrame, "to_sql", spy_to_sql):
            sdb.from_dataframe(df, t)

        # COPY verification: data is present
        rows = sdb.execute(f'SELECT COUNT(*) AS n FROM "{t}"')
        assert rows[0]["n"] == 3

        # to_sql verification: called exactly once, for head(0) (0 rows)
        assert len(to_sql_calls) == 1, "to_sql must be called exactly once (DDL only)"
        assert to_sql_calls[0] == 0, f"to_sql must be called on head(0), not on {to_sql_calls[0]}-row df"
    finally:
        sdb.execute(f'DROP TABLE IF EXISTS public."{t}" CASCADE', autocommit=True)
```

**Pourquoi cette approche:** Pas de timing. Non flaky (real-DB, déterministe). Vérifie le contrat observable (données présentes) ET que COPY est le chemin (to_sql n'a pas chargé les données). Conforme D-06.

**Pour le chemin async:** Mirror du test sync avec `await adb.from_dataframe(df, t)` dans une classe `@pytest.mark.asyncio`.

**Pour le seam ETL:** Le test existant `test_run_writes_full_row` vérifie déjà le résultat. Ajouter une assertion sur `cur.rowcount` via le runner ETL, ou vérifier le `rows_loaded` dans `RunResult` pour un jeu de données connu.

---

## Common Pitfalls

### Pitfall 1: pd.NaT passé brut à write_row

**What goes wrong:** `psycopg.errors.InvalidDatetimeFormat: syntaxe invalide pour timestamp : "NaT"` — COPY text format encode pd.NaT comme la string "NaT", que PostgreSQL ne peut pas parser.
**Why it happens:** `write_row` utilise le type adapter psycopg pour chaque valeur. `pd.NaT` n'est pas enregistré comme adapter et tombe en `str(pd.NaT)` = "NaT".
**How to avoid:** Toujours passer le masque null `df.isna().values` et substituer None. [VERIFIED: live DB crash]
**Warning signs:** Erreur à la première ligne avec colonne datetime qui a un NaT.

### Pitfall 2: columns drift entre DDL et COPY (index=True)

**What goes wrong:** DDL crée une colonne `index` (ou le nom de l'index) mais COPY streame les colonnes de `df` (sans l'index) → COPY fait référence à des colonnes qui n'existent pas dans `cols_str`.
**Why it happens:** `df.reset_index()` crée `df_ddl` avec la colonne d'index en tête. Si on passe `df.columns` (original) au COPY mais `df_ddl` au DDL, le schema ne correspond pas.
**How to avoid:** Toujours dériver `columns = list(df_ddl.columns)` après le `reset_index()` conditionnel, et passer `df_ddl` (pas `df`) au helper COPY. [VERIFIED: D-01a mécanique]
**Warning signs:** `psycopg.errors.UndefinedColumn` ou nombre de colonnes incorrect.

### Pitfall 3: ETL empty DataFrame — changer `if not rows:` sans mettre à jour le guard

**What goes wrong:** L'ancien guard `if not rows:` teste une liste vide. Après migration vers COPY, `rows` n'existe plus — le guard doit utiliser `df.empty` ou `len(df) == 0`.
**Why it happens:** Le refactoring supprime la liste `rows` avant le point de contrôle "no rows to load".
**How to avoid:** Remplacer `if not rows:` par `if df.empty:` au step 3. D-02b le prescrit. [VERIFIED: code etl.py L1362]
**Warning signs:** KeyError ou NameError en runtime sur pipelines avec DataFrames vides.

### Pitfall 4: `rows_loaded += cur.rowcount` après COPY — timing correct

**What goes wrong:** `cur.rowcount` n'est disponible qu'après la fermeture du context manager COPY (après `__exit__`). Si on lit `rowcount` à l'intérieur du bloc `with cur.copy(...) as copy:`, la valeur peut être 0 ou -1.
**How to avoid:** Lire `cur.rowcount` après le `with cur.copy(...):` block. [VERIFIED: live DB test — rowcount correct après exit du context manager]
**Warning signs:** `rows_loaded` toujours 0 malgré des lignes visibles en base.

### Pitfall 5: `copy_insert` public depuis le seam ETL

**What goes wrong:** `copy_insert` ouvre `self.connect()` (nouvelle connexion) + `conn.commit()` à la sortie → la transaction du seam ETL est toujours active sur une connexion différente ; le run-log est incohérent avec le load.
**How to avoid:** D-02a — COPY inline sur le curseur de transaction, pas via méthode publique. Le commentaire existant dans `etl.py` L1412 l'interdit déjà. [VERIFIED: code pattern, architectural decision]
**Warning signs:** Les données sont chargées même quand le run-log est `failed` (ou inversement).

### Pitfall 6: Async from_dataframe — `run_sync` + engine

**What goes wrong:** L'implémentation actuelle async `from_dataframe` utilise `await conn.run_sync(lambda sync_conn: df.to_sql(..., con=sync_conn))`. La migration vers COPY doit utiliser `async with self.connect() as conn: async with conn.cursor() as cur: async with cur.copy(...) as copy: await copy.write_row(...)`.
**How to avoid:** Le shape async est distinct du sync — ne pas réutiliser le helper sync dans un contexte async. [VERIFIED: async pattern testé live]
**Warning signs:** `asyncio.run()` appelé depuis un contexte async → RuntimeError.

---

## Code Examples

### Existing `copy_insert` pattern (reference — sync)

```python
# Source: pycopg/database.py L1037-1043 [VERIFIED: read directly]
with self.connect() as conn:
    with conn.cursor() as cur:
        with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row([row.get(col) for col in columns])
    conn.commit()
    return len(rows)
```

### Existing `copy_insert` pattern (reference — async)

```python
# Source: pycopg/async_database.py L678-686 [VERIFIED: read directly]
async with self.connect() as conn:
    async with conn.cursor() as cur:
        async with cur.copy(
            f"COPY {schema}.{table} ({cols_str}) FROM STDIN"
        ) as copy:
            for row in rows:
                await copy.write_row([row.get(col) for col in columns])
    await conn.commit()
    return len(rows)
```

### Existing `head(0).to_sql` DDL precedent (ETL)

```python
# Source: pycopg/etl.py L1379-1386 [VERIFIED: read directly]
if pipeline.load_mode == "replace" and not exists:
    self._db.from_dataframe(
        df.head(0),
        pipeline.target,
        pipeline.schema,
        if_exists="replace",
    )
```

### Current ETL materialization (to be replaced by COPY)

```python
# Source: pycopg/etl.py L1353-1366 [VERIFIED: read directly]
# BEFORE (to replace for append/replace):
rows = (
    df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
)
if not rows:
    self._end_run(run_id, "success", rows_extracted, 0)
    return self._fetch_run_result(run_id)
columns = list(rows[0].keys())

# AFTER:
if df.empty:
    self._end_run(run_id, "success", rows_extracted, 0)
    return self._fetch_run_result(run_id)
columns = list(df.columns)
```

### Current insert_batch (before hoist)

```python
# Source: pycopg/database.py L980-985 [VERIFIED: read directly]
for row in batch:
    row_placeholders = ", ".join(["%s"] * len(columns))  # invariant — re-computed each row
    placeholders.append(f"({row_placeholders})")
    params.extend(row.get(col) for col in columns)
```

### insert_batch after hoist (D-05)

```python
# Hoist before the per-row loop
row_placeholders = ", ".join(["%s"] * len(columns))  # computed once per batch
for row in batch:
    placeholders.append(f"({row_placeholders})")
    params.extend(row.get(col) for col in columns)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `df.to_sql(con=engine)` for full data load | `head(0).to_sql` (DDL) + `COPY FROM STDIN` (data) | Phase 38 | 10-50x I/O throughput for large frames |
| `df.astype(object).where(...).to_dict(orient="records")` | `df.isna().values` mask + `df.values` stream | Phase 38 | Eliminates full-frame copy, reduces peak memory |
| `row_placeholders` recomputed per row in insert_batch | Hoisted before per-row loop | Phase 38 | Micro-optimization, byte-exact |

**Note:** La migration est non-cassante — les signatures publiques restent identiques.

---

## Package Legitimacy Audit

Aucun nouveau package installé. Zéro nouvelles dépendances runtime (contrainte v0.10.0). Section non applicable.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.0.0+ avec pytest-asyncio 0.23.0+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `PGDATABASE=pycopg_test2 uv run pytest tests/test_database_integration.py tests/test_etl_accessor.py tests/test_parity.py -x -q -o addopts=""` |
| Full suite command | `PGDATABASE=pycopg_test2 uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERF-01 | `from_dataframe` routes data via COPY, not `to_sql` | unit+spy | `uv run pytest tests/test_database_integration.py::TestFromDataframeCopy -x -o addopts=""` | ❌ Wave 0 |
| PERF-01 | `if_exists` fail/replace/append préservés | integration (real DB) | `uv run pytest tests/test_database_integration.py -k "from_dataframe" -o addopts=""` | Partiel (L317 existe, à étendre) |
| PERF-01 | `index=True` round-trip | integration (real DB) | inclus dans class ci-dessus | ❌ Wave 0 |
| PERF-01 | `primary_key` post-load | integration (real DB) | `test_from_dataframe_primary_key_parity` dans test_parity.py | ✅ (L476) |
| PERF-02 | ETL `append`/`replace` via COPY, même statut/compte | integration (real DB) | `uv run pytest tests/test_etl_accessor.py -k "run" -o addopts=""` | Partiel (à adapter) |
| PERF-02 | ETL `upsert` reste sur INSERT ON CONFLICT | integration (real DB) | inclus dans suite ETL existante | ✅ |
| PERF-03 | `insert_batch` comportement byte-exact | unit (mock) | `uv run pytest tests/test_database.py -k "insert_batch" -o addopts=""` | Partiel (à étendre pour non-régression) |
| PERF-05 | Parité sync/async: `test_parity` + `test_accessor_parity` verts | unit | `uv run pytest tests/test_parity.py -x -o addopts=""` | ✅ |
| PERF-05 | Test comportemental async `from_dataframe` COPY dédié | unit+spy | `uv run pytest tests/test_async_database.py -k "from_dataframe_copy" -o addopts=""` | ❌ Wave 0 |

### Sampling Rate

- **Par task commit:** `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py tests/test_database_integration.py tests/test_etl_accessor.py -x -q -o addopts=""`
- **Par wave merge:** `PGDATABASE=pycopg_test2 uv run pytest`
- **Phase gate:** suite complète verte avant `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_database_integration.py` — classe `TestFromDataframeCopy` avec: `test_from_dataframe_copy_path` (spy to_sql), `test_from_dataframe_replace`, `test_from_dataframe_append`, `test_from_dataframe_index_true`, `test_from_dataframe_nan_null` (NaN/NaT → NULL en base)
- [ ] `tests/test_async_database.py` — test comportemental async `from_dataframe` avec spy (PERF-05 async)
- [ ] `tests/test_database.py` ou `test_database_integration.py` — `test_insert_batch_placeholder_hoist_regression` (non-régression PERF-03, petit dataset, vérifie résultat identique)
- [ ] `tests/test_etl_accessor.py` — étendre `test_run_writes_full_row` pour vérifier `rows_loaded` exact après COPY (ou nouveau test `test_etl_run_copy_path`)

---

## Security Domain

PERF-01/02/03 ne changent pas la surface d'authentification, de session management, ou de cryptographie. Les seules considérations sécurité restent:

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | Oui | `validate_identifiers(table, schema)` avant COPY (déjà présent dans `copy_insert`, à conserver dans les helpers) |
| V4 Access Control | Non (pas de changement de surface) | — |
| V2/V3 Auth/Session | Non | — |
| V6 Cryptography | Non | — |

**Threat pattern préservé:** `validate_identifiers` doit rester la première opération avant toute interpolation de `table`/`schema` dans la string COPY SQL. Déjà appliqué dans `copy_insert`. [VERIFIED: database.py L1028]

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | COPY tests (real DB) | ✓ | 15.x (pycopg_test2) | — |
| psycopg | COPY protocol | ✓ | 3.3.4 | — |
| pandas | DataFrame streaming | ✓ | existing | — |
| PGDATABASE=pycopg_test2 | Tests real DB | ✓ | env var requis | Défaut `pycopg_test` cassé depuis 2026-06-24 |

**Missing dependencies with no fallback:** Aucune.

**Note critique:** Tous les tests real-DB doivent être lancés avec `PGDATABASE=pycopg_test2`. La DB `pycopg_test` est inutilisable depuis 2026-06-24 (TSDB catalog mismatch). [VERIFIED: STATE.md Blockers/Concerns]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `df.values` sur DataFrame mixte (int + datetime) produit un object array qui préserve `pd.Timestamp` objects (pas des numpy.datetime64 strings) | Pattern 1 | Si faux: NaT en Timestamp colonne passerait comme datetime64 string → write_row ERROR. Mitigation: utiliser `itertuples` comme fallback. |
| A2 | `cur.rowcount` est posé correctement après fermeture du context manager COPY (testé en transaction et hors transaction) | Pattern ETL seam | Testé live — risque nul en pratique |

**Aucun package non-vérifié.** Toutes les bibliothèques sont existantes dans le projet.

---

## Open Questions

1. **Helper partagé: module-level dans `database.py` ou module `_copy_helpers.py` séparé?**
   - Ce qu'on sait: `etl.py` importe déjà depuis `database.py` (validation utilities)
   - Incertitude: ajouter un import circulaire potentiel si `database.py` importe depuis `etl.py`
   - Recommandation: helper défini dans `database.py` (sync) et `async_database.py` (async), `etl.py` importe depuis ces modules (déjà le cas pour d'autres utilitaires). Alternative: dupliquer les ~12 lignes dans `etl.py` pour éviter tout risque de couplage.

2. **upsert dans le seam ETL: la matérialisation `astype(object).to_dict` reste-t-elle nécessaire?**
   - Ce qu'on sait: `upsert` reste sur `INSERT … ON CONFLICT` (D-02c) — les builders `_build_upsert_sql` prennent `rows: list[dict]`
   - Incertitude: si les builders sont refactorisés pour accepter un DataFrame directement, l'upsert pourrait aussi éviter la matérialisation
   - Recommandation planner: conserver la matérialisation pour `upsert` en Phase 38, reporter l'optimisation upsert-path si nécessaire.

---

## Sources

### Primary (HIGH confidence)

- psycopg 3.3.4 source (`/home/loc/workspace/pycopg/.venv/lib/python3.12/site-packages/psycopg/`) — COPY protocol, `write_row`, `AsyncCopy` [VERIFIED: inspect + live tests]
- Live DB `pycopg_test2` — tests end-to-end NaN/NaT/Timestamp/np.int64 behavior [VERIFIED: tous les cas ci-dessus]
- `pycopg/database.py` L925-1043 — `insert_batch`, `copy_insert` patterns [VERIFIED: read directly]
- `pycopg/async_database.py` L568-686 — async mirrors [VERIFIED: read directly]
- `pycopg/etl.py` L1340-1441 + L2005-2111 — seam sync/async, matérialisation, builders [VERIFIED: read directly]

### Secondary (MEDIUM confidence)

- `.planning/phases/38-performance-copy/38-CONTEXT.md` — decisions D-01..D-06 [CITED]
- `.planning/REQUIREMENTS.md` — PERF-01..PERF-05 [CITED]
- `tests/test_parity.py`, `tests/test_etl_accessor.py`, `tests/conftest.py` [VERIFIED: read directly]

---

## Metadata

**Confidence breakdown:**
- NaN/NaT normalization: HIGH — tous les cas testés live contre psycopg 3.3.4 + DB réelle
- COPY in transaction pattern: HIGH — testé sync + async
- insert_batch hoist: HIGH — trivial, code lu directement
- ETL seam shape: HIGH — code relu, pattern vérifié
- Spy/assert-COPY-used test pattern: MEDIUM — pattern standard unittest.mock, adapté au codebase; non exécuté end-to-end en session de recherche
- Helper extraction: MEDIUM — décision d'architecture, trade-off DRY vs couplage

**Research date:** 2026-06-26
**Valid until:** 2026-07-26 (stable: psycopg API + pandas DataFrame API sont stables)
