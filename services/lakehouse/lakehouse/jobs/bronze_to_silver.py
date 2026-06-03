"""Bronze (MinIO JSON) -> Silver (Iceberg documents table)."""

from __future__ import annotations

import structlog
from pyspark.sql import functions as F
from pyspark.sql.types import (
    LongType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.window import Window

from lakehouse.spark_session import build_spark

log = structlog.get_logger(__name__)

BRONZE_SCHEMA = StructType(
    [
        StructField(
            "metadata",
            StructType(
                [
                    StructField("doc_id", StringType()),
                    StructField("source", StringType()),
                    StructField("source_type", StringType()),
                    StructField("source_url", StringType()),
                    StructField("title", StringType()),
                    StructField("section", StringType()),
                    StructField("ingested_at", StringType()),
                    StructField("content_hash", StringType()),
                    StructField("raw_object_key", StringType()),
                    StructField("text_object_key", StringType()),
                    StructField("byte_size", LongType()),
                    StructField("char_count", LongType()),
                ]
            ),
        ),
        StructField("text", StringType()),
    ]
)


def run() -> None:
    spark = build_spark("bronze_to_silver")
    spark.sparkContext.setLogLevel("WARN")

    spark.sql("CREATE NAMESPACE IF NOT EXISTS lh.silver")

    spark.sql("""
        CREATE TABLE IF NOT EXISTS lh.silver.documents (
            doc_id          STRING,
            source          STRING,
            source_type     STRING,
            source_url      STRING,
            title           STRING,
            section         STRING,
            ingested_at     TIMESTAMP,
            content_hash    STRING,
            raw_object_key  STRING,
            text_object_key STRING,
            byte_size       BIGINT,
            char_count      BIGINT,
            text            STRING
        )
        USING iceberg
        PARTITIONED BY (source, days(ingested_at))
        TBLPROPERTIES (
            'write.format.default' = 'parquet',
            'write.parquet.compression-codec' = 'zstd',
            'format-version' = '2'
        )
    """)

    df = (
        spark.read.option("multiLine", "true")
        .schema(BRONZE_SCHEMA)
        .json("s3a://bronze/source=*/date=*/text/*.json")
    )

    flat = df.select(
        F.col("metadata.doc_id").alias("doc_id"),
        F.col("metadata.source").alias("source"),
        F.col("metadata.source_type").alias("source_type"),
        F.col("metadata.source_url").alias("source_url"),
        F.col("metadata.title").alias("title"),
        F.col("metadata.section").alias("section"),
        F.to_timestamp("metadata.ingested_at").alias("ingested_at"),
        F.col("metadata.content_hash").alias("content_hash"),
        F.col("metadata.raw_object_key").alias("raw_object_key"),
        F.col("metadata.text_object_key").alias("text_object_key"),
        F.col("metadata.byte_size").alias("byte_size"),
        F.col("metadata.char_count").alias("char_count"),
        F.col("text"),
    ).filter(F.col("doc_id").isNotNull() & F.col("text").isNotNull())

    w = Window.partitionBy("doc_id").orderBy(F.col("ingested_at").desc_nulls_last())
    deduped = flat.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1).drop("_rn")

    log.info("bronze_to_silver.incoming", rows=deduped.count())

    deduped.createOrReplaceTempView("incoming")

    spark.sql("""
        MERGE INTO lh.silver.documents t
        USING incoming s
        ON t.doc_id = s.doc_id
        WHEN MATCHED AND s.content_hash <> t.content_hash THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    row = spark.sql("SELECT COUNT(*) AS n FROM lh.silver.documents").first()
    final = row["n"] if row is not None else 0
    log.info("bronze_to_silver.done", silver_total=final)

    spark.stop()


if __name__ == "__main__":
    import logging

    logging.basicConfig(level="INFO")
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    run()
