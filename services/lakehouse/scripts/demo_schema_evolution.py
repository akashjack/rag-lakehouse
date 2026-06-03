"""Demo: Iceberg schema evolution (metadata-only, no rewrite)."""

from __future__ import annotations

from lakehouse.spark_session import build_spark


def main() -> None:
    spark = build_spark("demo_schema_evolution")
    spark.sparkContext.setLogLevel("WARN")

    print("== Adding column 'language' to lh.silver.documents (no rewrite) ==")
    spark.sql("ALTER TABLE lh.silver.documents ADD COLUMNS (language STRING)")

    print("== Schema after evolution ==")
    spark.sql("DESCRIBE lh.silver.documents").show(truncate=False)

    print("== Old rows show NULL for the new column ==")
    spark.sql("SELECT doc_id, source, language FROM lh.silver.documents LIMIT 3").show()

    spark.stop()


if __name__ == "__main__":
    main()
