from __future__ import annotations


def relationship_audit(db, schema: str = "dbo") -> dict:
    declared = db.rows("""SELECT fk.name foreign_key, OBJECT_NAME(fk.parent_object_id) child_table,
      COL_NAME(fkc.parent_object_id,fkc.parent_column_id) child_column,
      OBJECT_NAME(fk.referenced_object_id) parent_table,
      COL_NAME(fkc.referenced_object_id,fkc.referenced_column_id) parent_column
      FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
      WHERE SCHEMA_NAME(OBJECTPROPERTY(fk.parent_object_id,'SchemaId'))=? ORDER BY fk.name""", [schema])
    duplicates = {}
    pks = db.rows("""SELECT tc.TABLE_NAME table_name, kcu.COLUMN_NAME column_name
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
       ON tc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME AND tc.TABLE_SCHEMA=kcu.TABLE_SCHEMA
      WHERE tc.TABLE_SCHEMA=? AND tc.CONSTRAINT_TYPE='PRIMARY KEY' ORDER BY tc.TABLE_NAME,kcu.ORDINAL_POSITION""", [schema])
    grouped = {}
    for row in pks: grouped.setdefault(row["table_name"], []).append(row["column_name"])
    for table, cols in grouped.items():
        select_cols = ",".join(f"[{c}]" for c in cols)
        duplicates[table] = db.row(f"SELECT COUNT_BIG(*) duplicate_groups FROM (SELECT {select_cols} FROM [{schema}].[{table}] GROUP BY {select_cols} HAVING COUNT_BIG(*)>1) x")["duplicate_groups"]
    orphans={}
    for fk in declared:
        key=fk["foreign_key"]
        orphans[key]=db.row(f"""SELECT COUNT_BIG(*) orphan_count FROM [{schema}].[{fk['child_table']}] c
          LEFT JOIN [{schema}].[{fk['parent_table']}] p ON p.[{fk['parent_column']}]=c.[{fk['child_column']}]
          WHERE c.[{fk['child_column']}] IS NOT NULL AND p.[{fk['parent_column']}] IS NULL""")["orphan_count"]
    return {"declared_foreign_keys": declared, "declared_foreign_key_count": len(declared),
            "declared_foreign_key_orphans":orphans,"duplicate_primary_key_groups": duplicates}
