# AWS infrastructure: Data engineering and analytics

> [Index](../../README.md) · **Use for:** data lake, formats, Glue/Athena/Redshift/DMS/EMR, streaming ingestion. Placeholders are defined in the index.

## 11. Data engineering and analytics pipelines

Use this section when the project ingests, transforms, or analyses data beyond the OLTP
database.

### 11.1 Lake layout

```
s3://<project>-<env>-datalake-raw/      # immutable landing zone, source format
s3://<project>-<env>-datalake-curated/  # cleaned, Parquet, partitioned (dt=…/), catalogued
s3://<project>-<env>-datalake-analytics/# aggregates / feature tables
```

- The **Glue Data Catalog** is the metastore that Athena, Redshift Spectrum, EMR, and Glue
  share. Use **Lake Formation** for table- or column-level permissions when several teams
  share the lake.
- **Partition** by the most common filter (usually the date), and **compact** small files.

### 11.2 Data formats

| Format | Best for | Key trait |
|---|---|---|
| CSV | Small or simple data, human readability | Universal, but slow and bulky |
| **Parquet** | Analytics (Athena, Glue, Redshift Spectrum), most ML | Columnar, compressed, fast. **The default for curated data** |
| ORC | Hive/Hadoop workloads | Similar to Parquet, optimized for Hive |
| RecordIO / protobuf | SageMaker built-in algorithms | Fast sequential reads during training |
| JSON / JSON Lines | API and semi-structured data, raw landing | Flexible, but inefficient at scale |

### 11.3 Batch ingestion and transformation: when to use which

| Service | What it does | Pick it when |
|---|---|---|
| **Glue** (Crawlers + ETL jobs) | Discovers schema, catalogs it, and transforms data (serverless Spark). **Job bookmarks** prevent reprocessing | The default for ETL into curated Parquet. Crawlers are scheduled to keep the catalog in sync |
| **Glue DataBrew** | Visual, no-code cleaning with 250+ transforms, profiling, and reusable **recipes** | Non-engineers prepare data, or quick profiling is needed |
| **Athena** | Serverless SQL directly on S3, through the Glue Catalog. **Pay per data scanned** | Ad-hoc analysis, or SQL transforms (CTAS) with no infrastructure. Parquet plus partitions keep the cost down |
| **Redshift** | Data warehouse for heavy, concurrent analytics and BI | Structured analytics at scale. Use **Redshift Serverless** for variable load |
| **Redshift Spectrum** | Lets Redshift query data in S3 without loading it | You **already have Redshift** and need to join warehouse tables with S3 data. Without Redshift, use Athena |
| **DMS** | Database migration, plus ongoing replication (**CDC**) | Moving data or keeping it in sync from existing databases (on-prem or another cloud) into AWS |
| **EMR** | A managed cluster for Spark, Hive, Presto/Trino, Hadoop | PB scale, custom Spark logic, or frameworks Glue does not support |
| **Step Functions** / **MWAA (managed Airflow)** | Orchestration | Step Functions for AWS-native serverless workflows. MWAA when the team already uses Airflow DAGs |

**EMR cost and operations:**

- **Node types:**
  - The **primary** node coordinates the cluster.
  - **Core** nodes store HDFS data and run tasks.
  - **Task** nodes only compute.
- **Purchasing:** run primary and core nodes On-Demand or Reserved. Run task nodes on
  **Spot** for cheap scaling.
- **Prefer transient clusters**, which start, run the job, write to S3, and terminate. Use a
  long-running cluster (or **EMR Serverless**) only for continuous work.
- Spark processes in memory and is much faster than disk-based MapReduce. Its **MLlib**
  library trains on data that does not fit on a single machine.

### 11.4 Streaming ingestion

See [aws §7.3](messaging-streaming.md). A typical streaming pipeline:

1. Producers write to Kinesis Data Streams or MSK.
2. **Managed Flink** (real-time transformations or anomaly detection) and/or **Firehose**
   (delivery) read from it.
3. Firehose writes to S3 as Parquet (format conversion through the Glue schema), partitioned
   by time.
4. Athena, Redshift, and ML consume the result.
