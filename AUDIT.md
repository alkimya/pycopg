# Audit du Projet pycopg

**Date** : 2026-01-02
**Version auditée** : 0.1.0
**Auditeur** : Claude Code

---

## 1. Vue d'ensemble

**pycopg** est une API Python de haut niveau pour PostgreSQL/PostGIS/TimescaleDB basée sur psycopg 3.
Le projet comprend ~3,800 lignes de code réparties sur 6 modules principaux.

### Structure du projet

```
pycopg/
├── __init__.py        (78 lignes)   - Exports publics
├── config.py          (244 lignes)  - Configuration et parsing d'URL
├── exceptions.py      (38 lignes)   - Hiérarchie d'exceptions
├── database.py        (2061 lignes) - Interface sync principale
├── async_database.py  (567 lignes)  - Interface async
├── pool.py            (416 lignes)  - Connection pooling
└── migrations.py      (388 lignes)  - Système de migrations SQL
```

---

## 2. Points Positifs

| Aspect | Évaluation |
|--------|------------|
| **Architecture** | Bonne séparation des responsabilités (sync/async, pool, migrations) |
| **Documentation** | Excellente - docstrings complètes avec exemples |
| **Typage** | Bon usage de type hints et TYPE_CHECKING |
| **Sécurité SQL** | `_validate_identifier()` protège contre l'injection |
| **Context managers** | Gestion correcte des ressources |
| **Dépendances optionnelles** | Gestion élégante (dotenv, geopandas) |
| **API Pythonic** | Interface intuitive et cohérente |

---

## 3. Issues Identifiées

### 3.1 Sécurité - Priorité HAUTE

#### 3.1.1 Identifiants SQL non validés

**Fichier** : `database.py`

| Méthode | Ligne | Paramètres non validés |
|---------|-------|------------------------|
| `create()` | 169-170 | `owner`, `template` |
| `create_database()` | 373-378 | `owner`, `template` |
| `add_foreign_key()` | 693-737 | tous les paramètres |
| `create_index()` | 758-797 | `method` |
| `enable_compression()` | 1110-1141 | `segment_by`, `order_by` |
| `create_hypertable()` | 1069-1108 | `chunk_time_interval` |

**Risque** : Injection SQL si des entrées utilisateur sont passées directement.

**Exemple vulnérable** :
```python
# Ligne 169-170
owner_clause = f" OWNER {owner}" if owner else ""
cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")
```

#### 3.1.2 pool.py sans validation

**Fichier** : `pool.py`

Le module `pool.py` n'importe pas et n'utilise pas `_validate_identifier()`.
Si des méthodes avec construction SQL dynamique sont ajoutées, elles seront vulnérables.

---

### 3.2 Bugs - Priorité HAUTE

#### 3.2.1 Accès incorrect au résultat dict

**Fichier** : `database.py:1984`

```python
def copy_to_csv(...) -> int:
    # ...
    cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
    return cur.fetchone()[0]  # BUG: dict_row retourne un dict, pas un tuple!
```

**Correction** : `return cur.fetchone()["count"]` ou utiliser `fetch_val()`.

#### 3.2.2 Stub load_dotenv incompatible

**Fichier** : `config.py:20-22` vs `config.py:136`

```python
# Stub (ligne 20-22)
def load_dotenv(dotenv_path=None):
    """No-op when python-dotenv is not installed."""
    pass

# Utilisation (ligne 136)
load_dotenv(dotenv_path, override=True)  # override= non supporté par le stub!
```

---

### 3.3 Dead Code - Priorité MOYENNE

#### 3.3.1 Attribut `_pool` inutilisé

**Fichier** : `async_database.py:54`

```python
class AsyncDatabase:
    def __init__(self, config: Config):
        self.config = config
        self._pool: Optional[AsyncConnectionPool] = None  # Jamais utilisé!
```

L'attribut `_pool` est initialisé mais jamais assigné à un vrai pool.
L'import `AsyncConnectionPool` dans TYPE_CHECKING est donc aussi inutile.

---

### 3.4 Duplication de Code (DRY) - Priorité MOYENNE

#### 3.4.1 `_validate_identifier()` dupliquée

La même fonction est définie 3 fois :
- `database.py:2038-2046`
- `async_database.py:548-552`
- Absente de `pool.py` (problème de sécurité)

#### 3.4.2 Requêtes SQL dupliquées

Les requêtes suivantes sont identiques entre `Database` et `AsyncDatabase` :
- `list_schemas()`
- `list_tables()`
- `table_exists()`
- `table_info()`
- `row_count()`
- `has_extension()`
- `list_extensions()`
- `role_exists()`
- `list_roles()`
- `size()`
- `table_size()`

---

### 3.5 Performance - Priorité MOYENNE

#### 3.5.1 `execute_many()` non optimisé

**Fichier** : `database.py:298-319`

```python
def execute_many(self, sql: str, params_seq: Sequence[Sequence]) -> int:
    total = 0
    with self.cursor() as cur:
        for params in params_seq:
            cur.execute(sql, params)  # N requêtes séquentielles!
            total += cur.rowcount
    return total
```

**Optimisations possibles** :
1. Utiliser `cur.executemany()` natif de psycopg
2. Pour INSERT : utiliser `VALUES (...), (...), (...)` (batch)
3. Pour INSERT massif : utiliser `COPY` (10-100x plus rapide)

#### 3.5.2 `insert_many()` sous-optimal

**Fichier** : `async_database.py:384-426`

Utilise `execute_many()` qui fait N requêtes au lieu d'un batch INSERT.

#### 3.5.3 Connexions non réutilisées

Chaque appel à `execute()`, `fetch_one()`, etc. ouvre et ferme une connexion.
Pour des opérations multiples consécutives, cela génère un overhead significatif.

---

## 4. Recommandations d'Amélioration

### 4.1 Sécurité

- [x] Extraire `_validate_identifier()` dans un module `utils.py` partagé
- [x] Valider TOUS les identifiants SQL dans toutes les méthodes
- [x] Ajouter une validation pour les valeurs d'intervalle (chunk_time_interval, etc.)

### 4.2 Bug Fixes

- [x] Corriger `copy_to_csv()` pour accéder correctement au dict
- [x] Corriger le stub `load_dotenv()` pour accepter `override=`

### 4.3 Nettoyage

- [x] Supprimer `_pool` inutilisé dans `AsyncDatabase`
- [x] Supprimer l'import `AsyncConnectionPool` dans TYPE_CHECKING

### 4.4 Factorisation

- [x] Créer `pycopg/utils.py` avec les fonctions utilitaires partagées
- [x] Créer `pycopg/queries.py` avec les requêtes SQL constantes
- [x] Créer une classe de base `BaseDatabase` pour la logique commune (`pycopg/base.py`)

### 4.5 Optimisation

- [x] Implémenter `executemany()` pour les opérations batch
- [x] Ajouter une méthode `insert_batch()` utilisant VALUES multiples
- [x] Ajouter une méthode `copy_insert()` utilisant COPY pour les gros volumes
- [x] Mode "session" pour réutiliser les connexions (`db.session()`)

---

## 5. Plan d'Action (COMPLÉTÉ)

### Phase 1 : Corrections Critiques ✅
1. ✅ Créer `utils.py` avec `validate_identifier()`
2. ✅ Corriger les vulnérabilités d'injection SQL
3. ✅ Corriger le bug `copy_to_csv()`
4. ✅ Corriger le stub `load_dotenv()`

### Phase 2 : Nettoyage ✅
5. ✅ Supprimer le dead code (`_pool`, imports inutiles)
6. ✅ Créer `queries.py` pour centraliser les requêtes SQL

### Phase 3 : Optimisation ✅
7. ✅ Optimiser `execute_many()` avec `executemany()`
8. ✅ Ajouter `insert_batch()` pour les INSERT massifs
9. ✅ Ajouter support `COPY` pour les très gros volumes (`copy_insert()`)

### Phase 4 : Améliorations Optionnelles ✅
10. ✅ Créer `base.py` avec classes de base et mixins
11. ✅ Ajouter mode session (`db.session()`) pour réutilisation des connexions

---

## 6. Métriques

| Métrique | Valeur |
|----------|--------|
| Lignes de code total | ~3,800 |
| Duplication estimée | ~10-15% |
| Issues sécurité (haute) | 2 |
| Bugs (haute) | 2 |
| Dead code (moyenne) | 2 |
| Optimisations possibles | 4 |

---

## 7. Conclusion

Le projet pycopg est **bien conçu et documenté**. Les principales améliorations à apporter sont :

1. **Sécurité** : Valider systématiquement tous les identifiants SQL
2. **Qualité** : Corriger les bugs identifiés
3. **DRY** : Factoriser le code dupliqué
4. **Performance** : Optimiser les opérations batch

Le code est prêt pour la production après correction des issues de priorité haute.
