# Phase 39: Couverture & Benchmarks - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Solder les deux derniers chantiers de durcissement/perf de v0.10.0 **avant la release (Phase 40)** :

1. **COV-01 — Cliquet de couverture 94→95 %.** Monter `--cov-fail-under=94`→`95` dans [pyproject.toml](pyproject.toml), combler l'écart par de **vrais tests comportementaux**, et tenir le gate vert en CI (`uv run pytest` contre un vrai Postgres).
2. **PERF-04 — Suite de benchmarks reproductible.** Mesurer les chemins d'insertion (`insert_batch`, `copy_insert`, `from_dataframe`, ETL load) sur un volume représentatif (~100k lignes), produire des **résultats comparatifs lisibles** qui documentent les gains COPY, et servir de **garde-fou anti-régression** via un **protocole documenté** (comment lancer, comment lire, à quoi ressemble une régression).

**État de couverture mesuré (stored `.coverage`, 2026-06-26) :** **94 % global, 199 lignes manquées / 3464**. Pour franchir 95 % il faut ≤173 manquées (~26 lignes à couvrir). Plus gros pools : `async_database.py` (68), `database.py` (41), `etl.py` (27), `timescale.py` (24), `schema.py` (18). ⚠ Ce `.coverage` peut refléter un run avec quelques échecs d'environnement (async/PostGIS) — le researcher reconfirme les chiffres exacts sous `PGDATABASE=pycopg_test2`. **Le repo n'a jamais utilisé `pragma: no cover`.**

**Contraintes absolues (carried forward du milestone v0.10.0 + Phases 37–38) :**
- **Non-cassant** — aucun changement de surface publique (cette phase n'ajoute que des tests + un dossier `benchmarks/` dev).
- **Zéro nouvelle dépendance *runtime*** — et ici, **zéro nouvelle dépendance dev non plus** : le tooling benchmark est en **stdlib pure** (décision D-01).
- **Parité sync/async + builder-pur** intacts — les nouveaux tests doivent rester symétriques quand ils touchent une méthode présente dans les deux classes.
- **Pas d'assertion de timing dans le gate de tests** — Phase 38 D-06 + Phase 37 vient de dé-flaker la suite ; on ne ré-introduit AUCUN timing dans `uv run pytest`.

**Explicitement hors de cette phase :**
- **REL-10** (version bump, CHANGELOG, 4 gates, tag + publish PyPI) → **Phase 40**.
- **COPY binaire** (PERF-F01) et **vectorisation numpy explicite** (PERF-F02) → **v2** ; le levier mesuré reste l'**I/O COPY textuel**.
- **Optimisation de code de prod supplémentaire** — Phase 38 a livré les chemins COPY ; Phase 39 **mesure et couvre**, ne re-optimise pas.

</domain>

<decisions>
## Implementation Decisions

### Benchmark tooling (PERF-04)
- **D-01 (Stdlib pur, standalone — pas de nouvelle dépendance même dev) :** Le harnais benchmark est un **runner autonome** sous `benchmarks/` utilisant `time.perf_counter` + `statistics` (stdlib). **Rejeté :** `pytest-benchmark` (ajoute une dépendance dev, couple le timing à pytest → exige un marker + désélection pour ne jamais entrer dans le gate de couverture) ; `asv`/airspeed-velocity (surdimensionné). Conforme au minimalisme du milestone (Phase 37 n'a ajouté que `vulture` + `pytest-randomly`).
- **D-01a (Localisation & isolation du gate — conséquence verrouillée de D-01) :** `benchmarks/` est un **dossier top-level**, **PAS** dans `[tool.pytest.ini_options] testpaths` (qui reste `["tests"]`). Donc `uv run pytest` et le gate `--cov-fail-under` **ne le touchent jamais** et il **ne compte pas dans la couverture** (`[tool.coverage.run] omit` peut l'ajouter par ceinture-et-bretelles si besoin). Entrée : `python -m benchmarks` (un `benchmarks/__main__.py`) **+ une cible `make bench`** dans le [Makefile](Makefile). Volume paramétrable via **arg CLI, défaut ~100k lignes**.

### Comparative baseline (PERF-04)
- **D-02 (Méthodes réelles tête-à-tête — pas de code mort ressuscité) :** Le benchmark mesure les **chemins publics expédiés** entre eux sur le même volume : `insert_batch` (executemany = **la baseline ligne-à-ligne**) vs `copy_insert` vs `from_dataframe` vs **chemin de load ETL** (`db.etl.run()` append/replace). Le gain COPY se lit **directement** comme le speedup vs `insert_batch`. **Rejeté :** ressusciter un `df.to_sql()` jetable dans le benchmark pour un before/after littéral de Phase 38 (réintroduit le chemin SQLAlchemy-engine mort + exige la fixture engine, pour une valeur marginale). Chaque chiffre mappe sur une méthode qui expédie.

### Regression guard-rail (PERF-04)
- **D-03 (Outil manuel documenté — aucune assertion de timing automatisée) :** La suite **imprime un tableau comparatif lisible** (par méthode : lignes/s, temps total, speedup vs `insert_batch`). Un humain la lance **à la demande** (local) et interprète une régression selon un **protocole documenté**. **NON câblé à la CI.** **Rejeté :** baseline committée + seuil de tolérance (timing bruité sur runners partagés → ré-introduit la flakiness que Phase 37 vient d'éliminer ; exigerait son propre harnais hors-pytest car ne peut pas vivre dans le gate de couverture) ; check de ratio relatif (« copy_insert ≥ Nx insert_batch ») — toujours une assertion de timing à maintenir/tuner. Cohérent avec **38-D-06** (pas de test timing-based) et le critère de succès ROADMAP #3 (« comment **interpréter** une régression » ⇒ lecture humaine).
- **D-03a (Protocole documenté — emplacement) :** Le protocole (comment lancer, comment lire le tableau, à quoi ressemble une régression — p.ex. les chemins COPY doivent rester un **multiple** plus rapides que `insert_batch`) vit dans **`benchmarks/README.md`**. Le researcher/planner décide s'il faut aussi un court pointeur dans le README projet — mais la source d'autorité du protocole est `benchmarks/README.md`.

### Coverage 94→95 approach (COV-01)
- **D-04 (Vrais tests d'abord ; `pragma: no cover` en dernier recours, justifié) :** Combler l'écart par de **vrais tests comportementaux** ciblant les branches réellement non testées (pools prioritaires : `async_database.py`, `database.py`, `etl.py`, `timescale.py`, `schema.py`). N'autoriser **`pragma: no cover` que pour des lignes véritablement injoignables/défensives** (p.ex. branches d'erreur driver impossibles à déclencher proprement), **chacune avec un commentaire de justification inline**. Introduit la convention `pragma` **délibérément et avec parcimonie** (première utilisation dans le repo). **Rejeté :** « real-tests-only, jamais de pragma » (peut forcer des tests fragiles sur du défensif non-instrumentable) et « pragma-forward » (fait monter le chiffre sans profondeur de test — trahit l'intention de durcissement du milestone).
- **D-04a (Mécanique du cliquet — verrouillé par l'exigence) :** Bump `--cov-fail-under=94`→`95` dans `addopts` de [pyproject.toml](pyproject.toml). C'est le **dernier acte** de la phase (après que les nouveaux tests aient réellement amené la mesure ≥95 %) pour ne pas casser le gate en cours de route.

### Claude's Discretion
- **Forme exacte du tableau de sortie** (colonnes, formatage rows/s vs ms, warmup/discard du 1er run) — researcher/planner tranche ; lean : warmup + N runs, médiane, colonne speedup vs `insert_batch`.
- **Gestion de l'env DB du benchmark** — réutiliser les variables `PG*` / `pycopg_test`(CI) / `pycopg_test2`(local) comme les tests ; détails au planner.
- **Quelles lignes précises tester pour atteindre 95 %** (et lesquelles, rares, méritent `pragma`) — researcher identifie après un run `--cov-report=term-missing` propre sous `PGDATABASE=pycopg_test2`.
- **Ajout (optionnel) de `benchmarks/` à `[tool.coverage.run] omit`** — ceinture-et-bretelles ; planner décide (déjà hors `testpaths`, donc non exécuté par le gate de toute façon).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Périmètre & exigences
- `.planning/REQUIREMENTS.md` — **COV-01** (cliquet 94→95) + **PERF-04** (benchmark reproductible, dev-group, comparatif, protocole documenté, ~100k lignes) = le périmètre exact de Phase 39 ; table **Out of Scope** (non-cassant, zéro dep runtime, pas de COPY binaire, pas de vectorisation numpy) ; §v2 (PERF-F01/F02 reportés).
- `.planning/ROADMAP.md` §"Phase 39: Couverture & Benchmarks" — goal + **3 critères de succès** (la source d'autorité du « DONE ») : (1) `--cov-fail-under=95` vert, (2) suite benchmark sur volume représentatif avec résultats comparatifs lisibles, (3) protocole documenté incl. « comment interpréter une régression ».
- `.planning/PROJECT.md` §"Current Milestone: v0.10.0" — contexte du levier COPY et de l'éthos zéro-dépendance.

### Décisions/contexte des phases amont (cohérence)
- `.planning/phases/38-performance-copy/38-CONTEXT.md` — **D-06** (pas de test timing-based en Phase 38 ; débit chiffré explicitement délégué à la suite benchmark Phase 39) ; les sites COPY livrés (`from_dataframe` Hybrid, seam ETL, `insert_batch` hoist) que le benchmark mesure.
- `.planning/phases/37-dette-audit/37-CONTEXT.md` + `37-DECISIONS.md` — Phase 37 a **dé-flaké** la suite et ajouté `pytest-randomly` (l'ordre est randomisé) ; raison structurelle de **ne pas** ré-introduire de timing dans le gate (D-03).

### Sites de code (cibles de mesure & couverture)
- `pycopg/database.py` — `insert_batch` ([L925](pycopg/database.py#L925)), `copy_insert` ([L995](pycopg/database.py#L995)), `from_dataframe` ([L1204](pycopg/database.py#L1204)) ; 41 lignes non couvertes (pool COV-01).
- `pycopg/async_database.py` — miroirs async (`insert_batch` [L568](pycopg/async_database.py#L568), `copy_insert` [L636](pycopg/async_database.py#L636), `from_dataframe` [L967](pycopg/async_database.py#L967)) ; **68 lignes non couvertes** (plus gros pool COV-01 — confirmer si réel ou artefact d'env).
- `pycopg/etl.py` — chemin de load (`db.etl.run()` append/replace via COPY) à mesurer ([seam L1415](pycopg/etl.py#L1415)) ; 27 lignes non couvertes.
- `pycopg/timescale.py` (24 miss) et `pycopg/schema.py` (18 miss) — pools COV-01 secondaires.

### Config & outillage
- [pyproject.toml](pyproject.toml) — `[tool.pytest.ini_options] addopts` (`--cov-fail-under=94`→**95**, **seul** lieu du bump ; `testpaths=["tests"]` **inchangé**) ; `[tool.coverage.run] omit` (option `benchmarks/`) ; `[tool.coverage.report] exclude_lines` (déjà : `pragma: no cover`, `def __repr__`, `if TYPE_CHECKING:`, `raise AssertionError`, `raise NotImplementedError`).
- [Makefile](Makefile) — ajouter cible `bench` (à côté de `test`/`lint`/`format`/`build`).
- `.github/workflows/tests.yml` — `uv run pytest` contre `timescale/timescaledb-ha:pg17` sur `pycopg_test` ; c'est là que le gate 95 % doit rester vert (benchmarks **n'y tournent pas**).

### Cartes de codebase
- `.planning/codebase/TESTING.md` — patterns de tests (fixtures DB réelles, classes `Test*`, `pytest.raises`) ; ⚠ daté 2026-02-11, structure de `tests/` a grossi depuis.
- `.planning/codebase/CONVENTIONS.md` — builder-pur, parité ; ⚠ `CONCERNS.md` daté 2026-02-11, largement périmé.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Chemins d'insertion expédiés (Phase 38)** — `insert_batch` (executemany), `copy_insert` (COPY), `from_dataframe` (Hybrid DDL+COPY), seam ETL load (COPY inline) : ce sont exactement les 4 cibles du benchmark (D-02). Aucune nouvelle surface à écrire pour mesurer.
- **Fixtures de tests DB réelles** (`tests/conftest.py`, `tests/setup_test_db.py`) — patrons pour les nouveaux tests COV-01 (et pour la config env du benchmark, réutilisable telle quelle).
- **`[tool.coverage.report] exclude_lines` déjà configuré** — `pragma: no cover` est **déjà** dans la liste d'exclusion ; D-04 n'a qu'à l'**employer** (avec justification inline), pas à le configurer.
- **[Makefile](Makefile)** existant (`install/test/lint/format/build`) — point d'ancrage pour la cible `bench`.

### Established Patterns
- **Parité sync/async** vérifiée par `test_parity`/`test_accessor_parity` — les nouveaux tests COV-01 sur méthodes bi-classes restent symétriques.
- **Builder-pur + `validate_identifiers` d'abord** — les nouveaux tests asservissent le comportement existant, ne contournent pas les builders.
- **Cliquet de couverture monotone** (convention historique « ratchet ») — on **monte** à 95, jamais on ne baisse.
- **Tests DB réels** sur `pycopg_test2` en local (le défaut `pycopg_test` est cassé depuis 2026-06-24) / `pycopg_test` en CI.
- **`pytest-randomly` actif** — tout nouveau test doit être déterministe quel que soit l'ordre (pas d'état partagé entre tests).

### Integration Points
- `benchmarks/` (nouveau, top-level, hors `testpaths`) → importe `pycopg` comme un consommateur, ouvre une vraie connexion (env `PG*`), mesure les 4 chemins, imprime le tableau. **Aucun** lien avec le gate pytest/couverture.
- `make bench` → `python -m benchmarks` (avec arg volume optionnel).
- Bump `--cov-fail-under=95` dans [pyproject.toml](pyproject.toml) **après** que les nouveaux tests aient amené la mesure ≥95 % (D-04a).

</code_context>

<specifics>
## Specific Ideas

- **Le benchmark documente, le test garde-fou ne chronomètre pas.** PERF-04 « garde-fou anti-régression » = **protocole + sortie lisible + lecture humaine**, pas une assertion CI (D-03). On ne ré-arme pas la flakiness soldée en Phase 37.
- **« Gains COPY » = speedup vs `insert_batch`** (la baseline ligne-à-ligne expédiée), pas un before/after contre du `to_sql` ressuscité (D-02).
- **Stdlib pur** : la suite benchmark **n'ajoute aucune dépendance**, même en dev — cohérent avec le minimalisme assumé du milestone (D-01).
- **`pragma: no cover` introduit avec parcimonie et justifié** : premier emploi dans le repo, réservé au défensif injoignable (D-04).
- **Le bump du cliquet est le dernier acte** — verdir d'abord la mesure, modifier `--cov-fail-under` ensuite (D-04a).

</specifics>

<deferred>
## Deferred Ideas

- **REL-10** (version bump, CHANGELOG `[0.10.0]`, 4 gates, tag + PyPI OIDC publish + smoke) → **Phase 40**.
- **COPY binaire** (PERF-F01) et **vectorisation numpy explicite** (PERF-F02) → **v2** (REQUIREMENTS §v2) ; le benchmark mesure le COPY **textuel** actuel.
- **Baseline benchmark committée + gate automatisé de régression** → écarté pour ce milestone (D-03) ; reconsidérable post-1.0 si un runner perf dédié/stable existe.
- **Pointeur protocole benchmark dans le README projet / docs Sphinx** → optionnel, choix planner ; la source d'autorité reste `benchmarks/README.md`.
- **Durcissement comportemental WR-03 (`copy_insert` session bypass)** → reste reporté **v1.0.0** (déféré en Phase 37) — pas touché par la mesure de Phase 39.

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 39-couverture-benchmarks*
*Context gathered: 2026-06-26*
