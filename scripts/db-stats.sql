\pset footer off
\echo '== Migration'
SELECT version_num AS revision FROM alembic_version;

\echo '== Recordings by status'
SELECT status, count(*) AS recordings, pg_size_pretty(sum(size_bytes)) AS declared_size
FROM recordings GROUP BY status ORDER BY status;

\echo '== Recordings per user'
SELECT owner_id, count(*) AS recordings,
       count(*) FILTER (WHERE status = 'uploaded') AS uploaded,
       max(created_at)::timestamp(0) AS last_upload
FROM recordings GROUP BY owner_id ORDER BY last_upload DESC;

\echo '== Latest 10 recordings'
SELECT left(id::text, 8) AS id, left(owner_id::text, 8) AS owner, filename, status,
       pg_size_pretty(size_bytes) AS size, created_at::timestamp(0) AS created,
       coalesce(failure_reason, '') AS failure_reason
FROM recordings ORDER BY created_at DESC LIMIT 10;

\echo '== Tables'
SELECT relname AS table, n_live_tup AS live_rows, seq_scan, idx_scan,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables ORDER BY relname;

\echo '== Connections'
SELECT coalesce(nullif(application_name, ''), '(none)') AS application, state, count(*)
FROM pg_stat_activity WHERE datname = current_database()
GROUP BY 1, 2 ORDER BY 1, 2;
