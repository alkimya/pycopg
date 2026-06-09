# Phase 12: Refactoring — brancher les abstractions - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-09
**Phase:** 12-refactoring-brancher-les-abstractions
**Areas discussed:** base.py adoption depth, Pure builders contract, queries.py SIMPLE variants, Refactor safety / scope guard

---

## base.py adoption depth (REF-02)

### Q1 — Profondeur du collapse sur DatabaseBase

| Option | Description | Selected |
|--------|-------------|----------|
| Inherit + delete duplicate factories | `class Database(DatabaseBase, QueryMixin)`. Supprimer from_env/from_url/__repr__ concrets, hériter du socle. `cls(...)` retourne la bonne sous-classe. Garder le `__init__` propre (super().__init__ puis engines). | ✓ |
| Inherit but keep concrete factories | Hériter mais garder les fabriques concrètes (docstrings Example plus riches) en fallback. Moins de dédup. | |
| Lift docstrings up, then delete | Remonter les docstrings Example dans le socle d'abord, puis supprimer. Plus de travail, réconcilie les Example maintenant. | |

**User's choice:** Inherit + delete duplicate factories (Recommended)
**Notes:** → D-01. Le `cls(...)` du socle corrige le type de retour ; docstrings vivent une fois sur le socle.

### Q2 — SessionMixin + _build_batch_insert_sql

| Option | Description | Selected |
|--------|-------------|----------|
| Wire batch builder; skip SessionMixin | Brancher _build_batch_insert_sql dans insert_many/upsert_many (sync+async). Laisser SessionMixin hors des socles (code session divergent, fragile, non nommé dans REF-02). | ✓ |
| Wire both batch builder + SessionMixin | Aussi migrer le code session sur SessionMixin. Blast radius dans la zone session/transaction fragile. | |
| Adopt base/QueryMixin only, defer batch builder too | Laisser même le batch-INSERT inline. Contredit le « utiliser _build_batch_insert_sql » du milestone. | |

**User's choice:** Wire batch builder; skip SessionMixin (Recommended)
**Notes:** → D-02. SessionMixin noté en Deferred ; CONCERNS.md flague la zone session comme fragile.

---

## Pure builders contract (REF-03)

### Q1 — Où vivent les builders

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level funcs in base.py | Fonctions module-level dans base.py, args explicites (pas self). Sync+async appellent la même fonction. Trivialement testables DB-free. | ✓ |
| Staticmethods on QueryMixin | @staticmethod sur QueryMixin à côté des _build_*_sql existants. Inherité, appelé via self. Un peu plus clunky à tester. | |
| Private staticmethods on each class | _build_* staticmethods sur Database, async appelle Database._build_*. Couple async au sync. | |

**User's choice:** Module-level funcs in base.py (Recommended)
**Notes:** → D-03. Cmd byte-identique sync/async → source unique.

### Q2 — Frontière du builder (env/subprocess)

| Option | Description | Selected |
|--------|-------------|----------|
| Builder = argv list only; env+subprocess stay | Le builder retourne seulement la liste cmd. PGPASSWORD env + subprocess.run restent dans la méthode. Split pur/impur propre, pas de secret dans le builder. | ✓ |
| Builder returns (cmd, env) tuple | Le builder assemble aussi le dict env. Route le password par la fonction pure, gain coverage minime. | |
| Planner's discretion on the exact seam | Verrouiller « builder retourne l'argv, DB-free testable » ; planner décide la coupe précise. | |

**User's choice:** Builder = argv list only; env+subprocess stay (Recommended)
**Notes:** → D-04. La complexité testable (format maps, flags, boucles tables) = 100 % couvrable ; coquille I/O reste non couverte.

---

## queries.py SIMPLE variants (REF-01/REF-04)

### Q1 — Sort des constantes *_SIMPLE

| Option | Description | Selected |
|--------|-------------|----------|
| Delete SIMPLE + wire async to canonical | Supprimer TABLE_INFO_SIMPLE/LIST_ROLES_SIMPLE (orphelines, 0 réf). Brancher async table_info/list_roles sur les constantes canoniques pleines. test_parity assert déjà la forme complète → net-safe. | ✓ |
| Delete SIMPLE only, leave async wiring to planner | Supprimer les SIMPLE ; laisser le choix de la constante cible au planner sous REF-01. | |
| Keep SIMPLE constants | Les laisser. Contredit REF-04 (nommées comme code mort à supprimer). | |

**User's choice:** Delete SIMPLE + wire async to canonical (Recommended)
**Notes:** → D-05. Vérifié par grep : zéro référence aux deux constantes. Async table_info utilise GET_COLUMNS inline aujourd'hui, pas même la SIMPLE.

---

## Refactor safety / scope guard

### Q1 — Posture du filet de sécurité

| Option | Description | Selected |
|--------|-------------|----------|
| Behavior-preserving; test_parity + full suite as net | Zéro changement API/forme/comportement. Filet = test_parity étendu + suite complète, verts en continu. Nouveaux tests SEULEMENT pour les builders purs. Test rouge = vraie régression → stop, ne pas réparer le test. | ✓ |
| Add characterization snapshots first | Capturer des snapshots (SQL, cmd, repr) avant et assert-equal après. Belt-and-suspenders, chevauche test_parity + tests builder. | |
| Planner decides safety depth | Verrouiller l'intention behavior-preserving seulement ; planner choisit le scaffolding par tranche. | |

**User's choice:** Behavior-preserving; test_parity + full suite as net (Recommended)
**Notes:** → D-06.

### Q2 — Discipline gate + agressivité dead-code

| Option | Description | Selected |
|--------|-------------|----------|
| Same gate discipline; remove only verified-dead | (a) Réutiliser Phase 11 D-08 : mesurer puis flipper 90→95. (b) Supprimer seulement les items grep-vérifiés-morts (cibles REF-04 toutes vérifiées) ; pas de suppression spéculative. | ✓ |
| Flip gate to 95 up front | Mettre 95 au début, bloque tous les commits intermédiaires. Contredit la discipline mesurer-puis-flipper. | |
| Aggressive dead-code sweep | Chasser tout import/constante/branche inutilisé trouvé. Élargit le blast radius. | |

**User's choice:** Same gate discipline; remove only verified-dead (Recommended)
**Notes:** → D-07.

---

## Claude's Discretion

- Ordre/granularité des tranches REF-* et des commits.
- Quelles ~25 chaînes SQL inline précises brancher et leur constante canonique cible (REF-01).
- Signature / ordre des args exacts des fonctions builder (D-03).
- Forme précise des tests builder DB-free et lesquels écrire pour atteindre 95 (D-04/D-07).
- Détail du `__init__` post-`super().__init__()` de chaque classe (D-01).
- Quels `import re` / branches `try/except: raise` / `stdout` non lus précis sont supprimables après vérif grep (D-07/REF-04).

## Deferred Ideas

- Adoption de `SessionMixin` (unification session-mode) — refactor session à part, hors REF-02, zone fragile. (D-02)
- Migration docstrings numpydoc / interrogate / V2 exceptions / `__version__` importlib / mypy → Phase 13.
- Spatial helpers `db.spatial.*` → Phase 14 (réutilise le pattern builder-pur).
- Sweep agressif de code mort au-delà des cibles REF-04 nommées → écarté (D-07).
