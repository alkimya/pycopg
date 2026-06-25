# Phase 37: Dette & Audit - Context

**Gathered:** 2026-06-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Assainir et auditer le socle pycopg **avant le gel 1.0** : solder la dette technique connue (tests flaky par isolation de fixture, erreurs ruff, warnings advisory v0.8–0.9, code mort, incohérence `TableNotFound`), passer une **passe d'audit outillée** (`/gsd-code-review` + scan code mort), et solder la **dette de sign-off Nyquist** des phases 22–24.

**Contraintes absolues (carried forward) :**
- **Non-cassant** — aucun changement de signature ou de nom d'API publique. C'est la raison structurelle des choix N818 (suppression, pas renommage) et `TableNotFound` (site de raise, pas retrait d'export).
- **Zéro nouvelle dépendance runtime** — l'outillage d'audit/test (`vulture`, `pytest-randomly`) va dans `[dependency-groups] dev`.
- **Parité sync/async + builder-pur** intacts (cette phase n'ajoute aucune surface publique).

**Explicitement hors de cette phase (mappé ailleurs dans v0.10.0) :**
- COV-01 (cliquet couverture 94→95) → **Phase 39** (le cliquet reste à 94 ici).
- PERF-01..05 (COPY, micro-opts, benchmarks) → **Phases 38–39**.
- REL-10 (release) → **Phase 40**.

</domain>

<decisions>
## Implementation Decisions

### DEBT-02 — Ruff 0 erreur (N818 + erreurs de test)
- **D-01a (N818, lib) :** Les 4 seules erreurs `pycopg/` sont des N818 sur des exceptions publiques (`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`) qui n'ont pas le suffixe `Error`. Renommer casserait `from pycopg import …` → **interdit**. Résolution : **per-file ignore ruff** — ajouter `[tool.ruff.lint.per-file-ignores]` `"pycopg/exceptions.py" = ["N818"]` avec un commentaire d'explication (noms publics, renommage cassant, à reconsidérer au gel d'API v1.0.0). Centralisé, documenté, garde N818 actif partout ailleurs. **Pas** de `# noqa` par ligne, **pas** de renommage+alias.
- **D-01b (erreurs de test) :** Les 31 erreurs `tests/` (F841×21, W291×5, E722×5) sont des **corrections mécaniques triviales** — supprimer les variables inutilisées, retirer les espaces de fin, remplacer `except:` par `except Exception:`. **On les corrige** (pas de suppression).

### DEBT-05 — `TableNotFound` cohérent
- **D-02 :** **Ajouter un vrai site de raise interne** (pas retirer de `__all__` — retirer un nom exporté serait lui-même un changement de surface publique). Le raise rend l'export honnête et améliore l'UX d'erreur (strictement additif). Le researcher fixe le site exact (candidat : `db.schema.table_info`/`describe` lèvent `TableNotFound` quand la table est absente) **après avoir confirmé que le comportement actuel sur table absente n'est pas un contrat documenté** (ne pas casser un retour vide observable). Ajouter un test asservissant le raise. Repli (si aucun site propre n'existe) : retrait d'`__all__` documenté dans `37-DECISIONS.md`.

### DEBT-03 — Warnings advisory : fix les peu coûteux, clore les comportementaux
- **D-03a (fix en phase) :** WR-01 garde `time_bucket(` **insensible à la casse** ; `test_sequences_async` asserte le nom de séquence spécifique (`<table>_id_seq`) au lieu de `len >= 1` ; section `Raises` ajoutée à la docstring `upsert` ; déduplication des `import uuid`/helpers de table ad-hoc dans les tests async.
- **D-03b (clos avec justification, durcissement comportemental reporté v1.0.0) :** WR-03 (INTERVAL literal vs `%s`), `%`/`%s` dans le SQL structurel fourni par l'appelant (accepté comme UX d'erreur appelant, pas une injection), IN-03 (helper `chunk_seq` fragile). Justification consignée dans `37-DECISIONS.md`.

### DEBT-04 — Code mort de test
- **D-04 :** Supprimer les monkeypatches morts (`has_extension`/`role_exists`, patches de méthodes plates obsolètes) du fixture async de `tests/test_sql_injection.py` (WR-02). Housekeeping mécanique.

### DEBT-01 — Tests flaky déterministes
- **D-05 :** Corriger la **cause racine d'isolation de fixture** des 3 tests flaky (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`, le ~2.7% bound-param) — bug `UndefinedTable` dans les suites spatial/integration (teardown de fixture partagé). Objectif : `uv run pytest` passe **déterministe** sans `-o addopts=""` ni ordre particulier. **Enforcement :** `pytest-randomly` (dev-group, cf. D-07) randomise l'ordre en CI pour prouver le déterminisme et prévenir le re-flake. ⚠ La randomisation peut révéler **d'autres** bugs latents d'isolation — découverte in-scope, mais un NOUVEAU bug d'isolation large/non lié est **consigné pour disposition** plutôt que d'étendre la phase sans borne.

### AUDIT-01 — Passe d'audit + barre de disposition
- **D-06 :** Lancer `/gsd-code-review` sur l'ensemble de `pycopg/` → rapport classé HIGH/MEDIUM/LOW. **Barre de disposition :** tout **HIGH corrigé en phase** ; **MEDIUM** corrigé OU explicitement reporté à v1.0.0 avec justification consignée ; **LOW** simplement consigné. Garde la phase de dette bornée et laisse les corrections comportementales risquées au milestone de gel d'API.

### AUDIT-02 + outillage dev-group
- **D-07 :** Ajouter `vulture` **et** `pytest-randomly` au groupe `[dependency-groups] dev` (PEP 735 ; zéro dépendance runtime). `vulture` scanne `pycopg/` pour le code mort → code mort confirmé retiré, faux positifs capturés dans une **allowlist vulture documentée** (le terme exact qu'emploie AUDIT-02). `pytest-randomly` sert l'enforcement DEBT-01 (cf. D-05).

### NYQ-01 — Sign-off Nyquist phases 22–24
- **D-08 :** **Sign-off formel citant les preuves survivantes + spot-check.** ⚠ **Réalité d'artefact (découverte en discussion) :** les `VALIDATION.md`/`VERIFICATION.md` des phases 22–24 **n'existent plus sur disque** — les répertoires de phase v0.6.0 n'ont pas été archivés avec leurs artefacts par-phase (seul `v0.5.0-phases` l'a été). La **preuve survivante** est `.planning/milestones/v0.6.0-MILESTONE-AUDIT.md` (tous les reqs 22–24 SATISFIED : ADM-01/MNT-01/BKP-01/SCH-01/SCH-02 ; couverture suite 95.64% ; bloc nyquist : `compliant: [21]`, `partial: [22,23,24]`). **Mécanisme (à finaliser par researcher/planner) :** plutôt que fabriquer de faux fichiers `draft`, consigner le sign-off dans `37-DECISIONS.md` **et** basculer le bloc nyquist du `v0.6.0-MILESTONE-AUDIT.md` en `compliant` (ou recréer un `VALIDATION.md` minimal estampillé PASSED) en citant la couverture de reqs de l'audit ; spot-check que les reqs d'accessor v0.6.0 tiennent toujours dans le code courant. (Option `/gsd-validate-phase 22|23|24` écartée — plus lourde, non requise pour solder une dette de sign-off, pas une lacune de couverture.)

### Journal de décisions
- **D-09 :** **Un seul fichier consolidé** `.planning/phases/37-dette-audit/37-DECISIONS.md` recense **toute** disposition « clos-avec-justification » (clôtures comportementales DEBT-03, reports MEDIUM d'audit, raisonnement de sign-off NYQ-01, repli DEBT-05 si utilisé, raison d'être de l'allowlist vulture). Roll-up court dans `STATE.md` → Deferred Items. Le verifier vérifie les critères de succès contre ce fichier.

### Claude's Discretion
- Site de raise exact pour `TableNotFound` (D-02) — researcher/planner tranche ; lean : `db.schema.table_info`/`describe`.
- Forme exacte de l'allowlist vulture (fichier `.py` whitelist vs config) — choix du planner.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Périmètre & exigences
- `.planning/REQUIREMENTS.md` — DEBT-01..05, AUDIT-01/02, NYQ-01 (+ COV/PERF/REL pour contexte milestone) ; table Out of Scope (non-cassant, zéro dep runtime).
- `.planning/ROADMAP.md` §"Phase 37: Dette & Audit" — goal + 5 critères de succès (la source d'autorité du « DONE »).
- `.planning/PROJECT.md` §"Known tech debt" — **liste d'autorité** des warnings advisory (WR-01/WR-03/%-structurel/IN-03 + advisory v0.9), tests flaky, N818, `TableNotFound`.
- `.planning/STATE.md` §Deferred Items + Blockers/Concerns — mapping dette→requirement ; note `PGDATABASE=pycopg_test2` (le défaut `pycopg_test` est cassé depuis 2026-06-24).

### Sites de code (dette)
- `pycopg/exceptions.py` — 4 exceptions publiques N818 ; classe `TableNotFound` (DEBT-02 suppression + DEBT-05 site de raise).
- `pycopg/__init__.py` — export `TableNotFound` dans `__all__` (DEBT-05).
- `tests/test_session_edge_cases.py` — sites F841 (~L54 `inner_session`, ~L68 `exc_info`).
- `tests/test_sql_injection.py` — E722/F841 + monkeypatches morts du fixture async (DEBT-04 / WR-02).
- `pyproject.toml` — `[tool.ruff]` (`select`/`ignore` ; cible per-file-ignore) ; `[dependency-groups] dev` (ajouter `vulture`/`pytest-randomly`) ; `[tool.pytest.ini_options]` `addopts … --cov-fail-under=94` (**ne PAS modifier ici** ; le 95 est Phase 39).

### Preuve NYQ-01
- `.planning/milestones/v0.6.0-MILESTONE-AUDIT.md` — **seule preuve survivante** Nyquist + couverture de reqs phases 22–24. Les `VALIDATION.md`/`VERIFICATION.md` de 22–24 **n'existent plus sur disque**.

### Cartes de codebase
- `.planning/codebase/CONVENTIONS.md`, `TESTING.md` — patterns (builder-pur, parité, fixtures, cliquet couverture).
- `.planning/codebase/CONCERNS.md` — ⚠ daté 2026-02-11, largement périmé/dépassé par les milestones suivants ; à lire avec prudence.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Config ruff existante** (`pyproject.toml` `[tool.ruff]` `select = ["E","F","W","I","N","UP"]`, `ignore = ["E501"]`) — ajouter `[tool.ruff.lint.per-file-ignores]` sans toucher au `select`.
- **`[dependency-groups] dev`** (PEP 735, L63) — point d'ancrage pour `vulture` + `pytest-randomly`.
- **Hiérarchie d'exceptions** (`pycopg/exceptions.py`, base `PycopgError`) — le raise `TableNotFound` réutilise la classe existante.
- **`/gsd-code-review`** (skill disponible) — produit le rapport sévérité-classé pour AUDIT-01 (aucune dépendance ajoutée).

### Established Patterns
- **Builder-pur + `validate_identifiers` d'abord**, valeurs en `%s` — tout site de raise / fix reste dans ce cadre.
- **Parité sync/async** vérifiée par `test_parity`/`test_accessor_parity` — un fix touchant une méthode doit rester symétrique (peu probable ici, mais à respecter pour DEBT-05).
- **Cliquet de couverture à 94** (`--cov-fail-under=94`) — **tenu à 94 dans cette phase** ; la montée à 95 est Phase 39.
- **Tests DB réels** sur `pycopg_test2` (le défaut `pycopg_test` est cassé) — pertinent pour reproduire/valider les flaky DEBT-01.

### Integration Points
- `pytest-randomly` s'intègre via le dev-group + s'active automatiquement dans `uv run pytest` (randomise l'ordre) → c'est le harnais d'enforcement de DEBT-01.
- `vulture` produit le scan code mort + consomme une allowlist documentée (AUDIT-02).
- `37-DECISIONS.md` (nouveau) est le point de convergence des dispositions ; roll-up dans `STATE.md`.

</code_context>

<specifics>
## Specific Ideas

- **Tension non-cassant ↔ ruff 0** : N818 résolu par **suppression per-file documentée**, pas renommage — explicitement parce que les noms sont publics et exportés.
- **Split DEBT-03 fix-vs-close** précis (D-03a/D-03b) : les gains triviaux sont faits, les changements comportementaux risqués sont **clos avec justification** et reportés au gel d'API v1.0.0.
- **Barre de disposition audit** : HIGH en phase / MEDIUM fix-ou-report-justifié / LOW consigné — garde la phase bornée.
- **NYQ-01 — artefacts manquants** : ne pas supposer que les `VALIDATION.md` 22–24 existent ; signer off contre `v0.6.0-MILESTONE-AUDIT.md` et consigner dans `37-DECISIONS.md`.

</specifics>

<deferred>
## Deferred Ideas

- **Renommer les exceptions avec suffixe `Error`** (`*Error`) — à reconsidérer au **gel d'API v1.0.0** sous politique de dépréciation (hors phase non-cassante).
- **Durcissement comportemental** WR-03 (INTERVAL vs `%s`), `%`-dans-SQL-structurel, IN-03 `chunk_seq` — reporté **v1.0.0**, justification dans `37-DECISIONS.md`.
- **COV-01** (cliquet 95%) → **Phase 39** ; **PERF-01..05** (COPY/benchmarks) → **Phases 38–39** ; **REL-10** → **Phase 40**.
- **Nouveau bug d'isolation large** révélé par `pytest-randomly` au-delà des 3 connus → consigné pour disposition, **ne pas** étendre Phase 37 sans borne.

</deferred>

---

*Phase: 37-dette-audit*
*Context gathered: 2026-06-25*
