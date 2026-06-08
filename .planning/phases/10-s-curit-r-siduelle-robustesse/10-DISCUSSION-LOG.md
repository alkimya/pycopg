# Phase 10: Sécurité résiduelle & robustesse - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-08
**Phase:** 10-s-curit-r-siduelle-robustesse
**Areas discussed:** Items déjà faits (v0.3.1), Résidu B2, Forme des tests, Atteindre 80

---

## Items déjà faits (par le hotfix v0.3.1)

Contexte présenté : le scout du code montre que les validations identifiants/intervalles et SEC-05 (async `create_role`) sont déjà implémentées et testées (sync + async, 28 tests dans `test_sql_injection.py`).

| Option | Description | Selected |
|--------|-------------|----------|
| Vérifier puis cocher comme acquis | Audit de chaque item validation + SEC-05 contre le code réel ; les déjà-couverts marqués DONE sans nouveau code. Seul le résiduel vrai (B1/B3/B5/B2) est codé. | ✓ |
| Combler les trous restants seulement | Audit rapide pour trouver uniquement les méthodes sans validation/test et les combler. | |
| Re-tout-valider par sécurité | Ré-auditer exhaustivement chaque méthode même si un test existe. | |

**User's choice:** Vérifier puis cocher comme acquis
**Notes:** Évite la ré-implémentation. Un trou avéré (méthode listée sans validation/test) est tout de même comblé. → D-01.

---

## Résidu B2 (fuite de connexion dans session())

Contexte présenté : SEC-02/B2 (masquage d'exception) est déjà corrigé sur disque ; reste un résidu distinct — `commit()` puis `close()` dans le même `try`, donc `close()` sauté si `commit()` lève → fuite de connexion.

| Option | Description | Selected |
|--------|-------------|----------|
| Oui — corriger le résidu commit/close | Restructurer le finally de session() (sync + async) pour garantir close() même si commit() lève, avec test dédié. | ✓ |
| Non — B2 est clos, hors périmètre | Considérer SEC-02 satisfait ; le résidu → backlog. | |

**User's choice:** Oui — corriger le résidu commit/close
**Notes:** Dans l'esprit « robustesse » de la phase. → D-02.

---

## Forme des tests (bugs de correction B1/B2/B3/B5)

Contexte présenté : ces bugs ne sont pas des injections SQL ; le critère n°3 exige un test rouge→vert par correctif.

| Option | Description | Selected |
|--------|-------------|----------|
| Tests d'intégration (vraie DB) | Test contre un vrai PostgreSQL (CI a déjà timescaledb-ha). Réaliste mais plus lent. | |
| Mocks ciblés où possible | B5/B2 par mock (rapides, aident coverage) ; B1/B3 en intégration. Mix pragmatique. | |
| À ma discrétion (planner tranche) | Le planner choisit la forme la plus adaptée par bug au moment du plan, et la documente. | ✓ |

**User's choice:** À ma discrétion (planner tranche)
**Notes:** Autonomie cohérente avec Phase 1. → D-06.

---

## Atteindre le cliquet coverage → 80

Contexte présenté : le résiduel pur pourrait ne pas suffire à gagner 10 points de coverage.

| Option | Description | Selected |
|--------|-------------|----------|
| Tests des correctifs + comblement ciblé | Tests rouge→vert d'abord ; si < 80, le planner cible les modules faciles/critiques (pool, migrations, session). Pas de refacto (Phase 12). | ✓ |
| Plafonner l'effort, ajuster si besoin | Viser 80 mais documenter et viser le max atteignable proprement si du code dur à mocker bloque. | |
| À ma discrétion | Le planner décide de la stratégie coverage. | |

**User's choice:** Tests des correctifs + comblement ciblé
**Notes:** Pas de refacto ni de tests fragiles. Gate montée à 80 seulement quand le seuil est réellement franchi. → D-07.

---

## Claude's Discretion

- Forme exacte des tests par bug (D-06).
- Stratégie de comblement coverage pour atteindre 80 proprement, sans refacto ni tests fragiles (D-07).
- Types/messages d'exception et structuration précise des correctifs.
- Détails de la restructuration `try/finally` de `session()` (D-02).
- Périmètre exact et niveau de preuve de l'audit « déjà fait » (D-01).
- B3 : verrouillage par Claude que `_apply` ET `rollback` passent en transaction atomique (conforme critère n°2 + SEC-03).

## Deferred Ideas

- Refactoring `base.py`/`queries.py` + builders purs → Phase 12.
- Parité sync/async (méthodes async manquantes) → Phase 11.
- Concerns robustesse hors SEC-01..06 (statement_timeout, retry/backoff, streaming, pool adaptatif, SRID silencieux) → backlog.
- Logging des fichiers de migration ignorés silencieusement (`migrations.py._get_migrations`) → backlog (distinct de B3).
