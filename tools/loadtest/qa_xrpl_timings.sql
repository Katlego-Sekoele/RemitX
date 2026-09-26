-- Real XRPL settlement timings, for calibrating the load test's simulated burn.
-- Run in the Neon SQL editor on the QA branch.
--
-- Skips the seeder's simulated settlements (their hashes start 5EED).
-- Drops outliers per metric: anything outside Tukey's far-out fences,
-- Q1 - 3*IQR .. Q3 + 3*IQR (e.g. the worker-wake bug's multi-hour queue waits).
WITH s AS (
  SELECT
    EXTRACT(EPOCH FROM t.confirmed_at - t.processed_at)::float8 AS burn_s,   -- XRPL call + confirm task
    EXTRACT(EPOCH FROM t.processed_at - r.created_at)::float8   AS queue_s,  -- send -> worker picks it up
    EXTRACT(EPOCH FROM t.confirmed_at - r.created_at)::float8   AS total_s   -- send -> settled
  FROM transactions t
  JOIN remittances r ON r.quote_id = t.quote_id
  WHERE t.type = 'token_burn'
    AND t.status = 'confirmed'
    AND t.xrpl_tx_hash NOT LIKE '5EED%'
),
q AS (
  SELECT
    percentile_cont(0.25) WITHIN GROUP (ORDER BY burn_s)  AS b1,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY burn_s)  AS b3,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY queue_s) AS q1,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY queue_s) AS q3,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY total_s) AS t1,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY total_s) AS t3
  FROM s
),
k AS (
  SELECT
    s.*,
    burn_s  BETWEEN b1 - 3 * (b3 - b1) AND b3 + 3 * (b3 - b1) AS keep_burn,
    queue_s BETWEEN q1 - 3 * (q3 - q1) AND q3 + 3 * (q3 - q1) AS keep_queue,
    total_s BETWEEN t1 - 3 * (t3 - t1) AND t3 + 3 * (t3 - t1) AS keep_total
  FROM s CROSS JOIN q
)
SELECT
  count(*)                               AS settlements,
  count(*) FILTER (WHERE NOT keep_burn)  AS burn_outliers,
  count(*) FILTER (WHERE NOT keep_queue) AS queue_outliers,
  count(*) FILTER (WHERE NOT keep_total) AS total_outliers,
  round((percentile_cont(0.50) WITHIN GROUP (ORDER BY burn_s)  FILTER (WHERE keep_burn))::numeric, 2)  AS burn_p50_s,
  round((percentile_cont(0.90) WITHIN GROUP (ORDER BY burn_s)  FILTER (WHERE keep_burn))::numeric, 2)  AS burn_p90_s,
  round((percentile_cont(0.95) WITHIN GROUP (ORDER BY burn_s)  FILTER (WHERE keep_burn))::numeric, 2)  AS burn_p95_s,
  round((max(burn_s)                                           FILTER (WHERE keep_burn))::numeric, 2)  AS burn_max_s,
  round((percentile_cont(0.50) WITHIN GROUP (ORDER BY queue_s) FILTER (WHERE keep_queue))::numeric, 2) AS queue_p50_s,
  round((percentile_cont(0.95) WITHIN GROUP (ORDER BY queue_s) FILTER (WHERE keep_queue))::numeric, 2) AS queue_p95_s,
  round((percentile_cont(0.50) WITHIN GROUP (ORDER BY total_s) FILTER (WHERE keep_total))::numeric, 2) AS total_p50_s,
  round((percentile_cont(0.95) WITHIN GROUP (ORDER BY total_s) FILTER (WHERE keep_total))::numeric, 2) AS total_p95_s
FROM k;
