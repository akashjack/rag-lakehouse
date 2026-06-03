"""One-shot diagnostic: can Spark see bronze?

Variables URI/Path/FileSystem are Java class references via Py4J,
not Python instances. PascalCase is the PySpark convention for these.
"""

# ruff: noqa: N806  # Java class refs via Py4J — see module docstring

from __future__ import annotations

from lakehouse.spark_session import build_spark


def main() -> None:
    spark = build_spark("diagnose_bronze")
    spark.sparkContext.setLogLevel("WARN")

    hadoop_conf = spark._jsc.hadoopConfiguration()
    print("=== Spark Hadoop S3A config ===")
    print("  fs.s3a.endpoint           :", hadoop_conf.get("fs.s3a.endpoint"))
    print("  fs.s3a.path.style.access  :", hadoop_conf.get("fs.s3a.path.style.access"))
    print("  fs.s3a.connection.ssl.enabled:", hadoop_conf.get("fs.s3a.connection.ssl.enabled"))
    print("  fs.s3a.access.key set     :", hadoop_conf.get("fs.s3a.access.key") is not None)

    URI = spark._jvm.java.net.URI
    Path = spark._jvm.org.apache.hadoop.fs.Path
    FileSystem = spark._jvm.org.apache.hadoop.fs.FileSystem

    print("\n=== Listing s3a://bronze/ via Hadoop FileSystem ===")
    try:
        fs = FileSystem.get(URI("s3a://bronze/"), hadoop_conf)
        for s in fs.listStatus(Path("s3a://bronze/")):
            print("   ", s.getPath().toString(), "(dir)" if s.isDirectory() else "(file)")
    except Exception as e:
        print("  ERROR:", str(e)[:300])

    print("\n=== Listing s3a://bronze/source=angular/ ===")
    try:
        fs = FileSystem.get(URI("s3a://bronze/"), hadoop_conf)
        for s in fs.listStatus(Path("s3a://bronze/source=angular/")):
            print("   ", s.getPath().toString())
    except Exception as e:
        print("  ERROR:", str(e)[:300])

    print("\n=== Spark glob: s3a://bronze/source=*/date=*/text/*.json ===")
    try:
        df = spark.read.json("s3a://bronze/source=*/date=*/text/*.json")
        print("  count:", df.count())
        print("  partitions:", df.rdd.getNumPartitions())
        if df.count() > 0:
            df.printSchema()
            df.show(1, truncate=80)
    except Exception as e:
        print("  ERROR:", str(e)[:300])

    print("\n=== Spark glob (alternate): s3a://bronze/*/* ===")
    try:
        df2 = spark.read.json("s3a://bronze/*/*/text/*.json")
        print("  count:", df2.count())
    except Exception as e:
        print("  ERROR:", str(e)[:300])

    spark.stop()


if __name__ == "__main__":
    main()
