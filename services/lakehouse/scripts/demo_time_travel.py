"""Demo: Iceberg time travel."""

from __future__ import annotations

from lakehouse.spark_session import build_spark


def main() -> None:
    spark = build_spark("demo_time_travel")
    spark.sparkContext.setLogLevel("WARN")

    print("\n== Recent snapshots of lh.silver.documents ==")
    spark.sql("""
        SELECT snapshot_id, committed_at, operation, summary
        FROM lh.silver.documents.snapshots
        ORDER BY committed_at DESC
        LIMIT 5
    """).show(truncate=False)

    print("== Current row count ==")
    spark.sql("SELECT COUNT(*) AS rows_now FROM lh.silver.documents").show()

    print("== Row count as of the OLDEST available snapshot ==")
    oldest = spark.sql("""
        SELECT snapshot_id FROM lh.silver.documents.snapshots
        ORDER BY committed_at ASC LIMIT 1
    """).first()
    if oldest:
        sid = oldest["snapshot_id"]
        spark.sql(f"""
            SELECT COUNT(*) AS rows_then
            FROM lh.silver.documents VERSION AS OF {sid}
        """).show()

    spark.stop()


if __name__ == "__main__":
    main()
