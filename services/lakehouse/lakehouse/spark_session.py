"""Spark session factory configured for Iceberg + MinIO/S3."""

from __future__ import annotations

import os

from pyspark.sql import SparkSession


def build_spark(app_name: str) -> SparkSession:
    """Return a SparkSession wired to the Iceberg REST catalog + MinIO.

    Catalog name `lh` is used in all SQL: SELECT * FROM lh.silver.documents
    """
    minio_endpoint = os.getenv("S3_ENDPOINT", "http://minio:9000")
    minio_user = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
    minio_pw = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin")
    rest_uri = os.getenv("ICEBERG_REST_URI", "http://iceberg-rest:8181")

    return (
        SparkSession.builder.appName(app_name)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.lh", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.lh.type", "rest")
        .config("spark.sql.catalog.lh.uri", rest_uri)
        .config("spark.sql.catalog.lh.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.lh.s3.endpoint", minio_endpoint)
        .config("spark.sql.catalog.lh.s3.path-style-access", "true")
        .config("spark.sql.catalog.lh.warehouse", "s3://lakehouse/warehouse/")
        .config("spark.hadoop.fs.s3a.endpoint", minio_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", minio_user)
        .config("spark.hadoop.fs.s3a.secret.key", minio_pw)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
        )
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
