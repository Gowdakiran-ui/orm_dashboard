-- Seed Part B source expansion feeds.
-- Idempotent: safe to re-run, matches seed_dev.sql's ON CONFLICT style.

-- === B2: Static publisher RSS feeds (topical_global, client_id NULL) ===
-- All 14 candidate URLs from TASK.md were fetched live and verified reachable
-- except Business Standard Latest, which returned HTTP 403 (bot-blocked)
-- regardless of User-Agent — excluded here, see FINDINGS.md.

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml', 'News', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml', 'Business', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'BBC Tech', 'https://feeds.bbci.co.uk/news/technology/rss.xml', 'Technology', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'TechCrunch', 'https://techcrunch.com/feed/', 'Technology', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'The Verge', 'https://www.theverge.com/rss/index.xml', 'Technology', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'The Guardian World', 'https://www.theguardian.com/world/rss', 'News', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'NPR', 'https://feeds.npr.org/1001/rss.xml', 'News', 30, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'LiveMint News', 'https://www.livemint.com/rss/news', 'News', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'LiveMint Markets', 'https://www.livemint.com/rss/markets', 'Business', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'LiveMint Tech', 'https://www.livemint.com/rss/technology', 'Technology', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'Economic Times Government', 'https://government.economictimes.indiatimes.com/rss/topstories', 'Government', 30, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'Economic Times Retail', 'https://retail.economictimes.indiatimes.com/rss/topstories', 'Business', 30, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'SEBI Press/Circulars/Orders', 'https://www.sebi.gov.in/sebirss.xml', 'Government', 60, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

-- Excluded: Business Standard Latest (https://www.business-standard.com/rss/latest-news-101.rss)
-- verified HTTP 403 at write time regardless of User-Agent. See FINDINGS.md.

-- === Part C (TASK_ADD_RSS_FEEDS.md Phase 2): 6 additional sources, 8 URLs ===
-- Validated live in Phase 1 (FINDINGS.md) using the production adapter's
-- actual User-Agent, not just a browser check. Excluded from this batch,
-- with reasons logged in FINDINGS.md/BACKLOG.md: Financial Express (dead,
-- RSS retired, no working alternative found), Business Standard and PIB
-- (both blocked with HTTP 403 by Akamai under this adapter's User-Agent —
-- same class of block as the pre-existing Business Standard exclusion
-- above, not a code bug; fixing the shared User-Agent is deferred to a
-- separate task since it affects every existing feed), Indian Express
-- (reachable and collision-free, but its own feed entries have empty
-- content/summary fields — headline-only, decided not worth adding).
-- Ars Technica's "Read full article Comments" trailing boilerplate is
-- handled by a dedicated strip rule in text_processing.py::strip_html(),
-- not by excluding the source.

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'The Hindu National', 'https://www.thehindu.com/news/national/feeder/default.rss', 'News', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'The Hindu Business', 'https://www.thehindu.com/business/feeder/default.rss', 'Business', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'ZDNet', 'https://www.zdnet.com/news/rss.xml', 'Technology', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'Wired Business', 'https://www.wired.com/feed/category/business/latest/rss', 'Business', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'Hindu BusinessLine', 'https://www.thehindubusinessline.com/feeder/default.rss', 'Business', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'CNBC Top News', 'https://www.cnbc.com/id/100003114/device/rss/rss.html', 'News', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'CNBC Business News', 'https://www.cnbc.com/id/10001147/device/rss/rss.html', 'Business', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES (gen_random_uuid(), 'Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index', 'Technology', 15, true, NULL, 'topical_global', 'rss')
ON CONFLICT (feed_url) DO NOTHING;


-- === B4: Per-client GDELT + HN Algolia feeds, backfilled for existing clients ===
-- onboard_client() now provisions these for new clients; this backfills the
-- 6 real existing clients (the 5 duplicate "Forensic Test Client 2" rows are
-- intentionally excluded — see FINDINGS.md).

INSERT INTO rss_feeds (id, feed_name, feed_url, category, poll_interval_minutes, is_active, client_id, source_type, source_format)
VALUES
  (gen_random_uuid(), 'Apple Inc GDELT Feed', 'https://api.gdeltproject.org/api/v2/doc/doc?query=Apple+Inc&mode=artlist&format=json&maxrecords=50', 'News', 60, true, '129cd6d1-639b-4bb0-ae2b-fea068a28706', 'json_api', 'gdelt_json'),
  (gen_random_uuid(), 'Apple Inc HN Algolia Feed', 'https://hn.algolia.com/api/v1/search?query=Apple+Inc&tags=story', 'News', 60, true, '129cd6d1-639b-4bb0-ae2b-fea068a28706', 'json_api', 'hn_algolia_json'),

  (gen_random_uuid(), 'Nvidia GDELT Feed', 'https://api.gdeltproject.org/api/v2/doc/doc?query=Nvidia&mode=artlist&format=json&maxrecords=50', 'News', 60, true, '2aadc821-bd31-4f90-9ed4-96c75b96cabf', 'json_api', 'gdelt_json'),
  (gen_random_uuid(), 'Nvidia HN Algolia Feed', 'https://hn.algolia.com/api/v1/search?query=Nvidia&tags=story', 'News', 60, true, '2aadc821-bd31-4f90-9ed4-96c75b96cabf', 'json_api', 'hn_algolia_json'),

  (gen_random_uuid(), 'OpenAI GDELT Feed', 'https://api.gdeltproject.org/api/v2/doc/doc?query=OpenAI&mode=artlist&format=json&maxrecords=50', 'News', 60, true, '1c0a302a-b8aa-4e51-b868-43e42128d05c', 'json_api', 'gdelt_json'),
  (gen_random_uuid(), 'OpenAI HN Algolia Feed', 'https://hn.algolia.com/api/v1/search?query=OpenAI&tags=story', 'News', 60, true, '1c0a302a-b8aa-4e51-b868-43e42128d05c', 'json_api', 'hn_algolia_json'),

  (gen_random_uuid(), 'PepsiCo GDELT Feed', 'https://api.gdeltproject.org/api/v2/doc/doc?query=PepsiCo&mode=artlist&format=json&maxrecords=50', 'News', 60, true, 'c6c012fe-2346-471a-9932-b81a4fd4896c', 'json_api', 'gdelt_json'),
  (gen_random_uuid(), 'PepsiCo HN Algolia Feed', 'https://hn.algolia.com/api/v1/search?query=PepsiCo&tags=story', 'News', 60, true, 'c6c012fe-2346-471a-9932-b81a4fd4896c', 'json_api', 'hn_algolia_json'),

  (gen_random_uuid(), 'Tata Motors GDELT Feed', 'https://api.gdeltproject.org/api/v2/doc/doc?query=Tata+Motors&mode=artlist&format=json&maxrecords=50', 'News', 60, true, 'a1bbfc20-3865-4856-b040-6a1c399fe9bc', 'json_api', 'gdelt_json'),
  (gen_random_uuid(), 'Tata Motors HN Algolia Feed', 'https://hn.algolia.com/api/v1/search?query=Tata+Motors&tags=story', 'News', 60, true, 'a1bbfc20-3865-4856-b040-6a1c399fe9bc', 'json_api', 'hn_algolia_json'),

  (gen_random_uuid(), 'Tesla GDELT Feed', 'https://api.gdeltproject.org/api/v2/doc/doc?query=Tesla&mode=artlist&format=json&maxrecords=50', 'News', 60, true, 'ce3934b9-40cd-4bd1-8cc7-1c278107a8eb', 'json_api', 'gdelt_json'),
  (gen_random_uuid(), 'Tesla HN Algolia Feed', 'https://hn.algolia.com/api/v1/search?query=Tesla&tags=story', 'News', 60, true, 'ce3934b9-40cd-4bd1-8cc7-1c278107a8eb', 'json_api', 'hn_algolia_json')
ON CONFLICT (feed_url) DO NOTHING;
