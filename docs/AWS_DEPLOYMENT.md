# AWS Deployment (Copilot / ECS Fargate)

This is the reference for deploying the ORM Intelligence Platform to AWS
using [AWS Copilot](https://aws.github.io/copilot-cli/) over ECS Fargate.
**Nothing in this doc has been run.** The `copilot/` manifests and addon
CloudFormation templates in this repo were generated without a real AWS
account; every command below creates real, billable infrastructure and must
be run by you, reviewed as you go.

Target scale: ~500 total users / ~100 concurrent. Sizing choices throughout
are conservative starting points for a fresh deployment with no existing
traffic data — see the sizing notes in each `copilot/*/manifest.yml` and
`copilot/environments/addons/*.yml` file, and revisit once real usage
exists.

## 1. Prerequisites

1. An AWS account, with an IAM user (not the root account) that has
   permissions to create VPCs, ECS/Fargate resources, RDS, ElastiCache, S3,
   Secrets Manager, IAM roles/policies, ALBs, and Route53/ACM records (or
   the `AdministratorAccess` managed policy while getting this running, then
   scope it down).
2. AWS CLI v2 installed and configured (`aws configure`) with that IAM
   user's credentials.
3. [Copilot CLI](https://aws.github.io/copilot-cli/docs/getting-started/install/)
   installed (`brew install aws/tap/copilot-cli` on macOS, or see the linked
   install docs for Linux/Windows).
4. Docker installed and running locally (Copilot builds images locally by
   default and pushes them to ECR).
5. **Before the first `svc deploy` for `backend`**: `bootstrap_schema.py`
   (run automatically on container start — see the backend Dockerfile CMD)
   looks for `database/schema.sql` relative to the container, which
   docker-compose provides via a bind mount that doesn't exist on Fargate.
   Copy the schema into the backend's build context so it ships inside the
   image:
   ```bash
   cp -r database orm_collection/database
   ```
   (Add `orm_collection/database/` to a `.dockerignore` exception if one
   exists, and re-run this after any `database/schema.sql` change until this
   is automated.)
6. Edit the placeholder values in the generated manifests before deploying:
   - `copilot/backend/manifest.yml`: `CORS_ALLOWED_ORIGINS`, `S3_ENDPOINT_URL`
     region if not `us-east-1`.
   - `copilot/frontend/manifest.yml`: `NEXT_PUBLIC_API_URL` build arg (must
     be the backend's real public URL as the browser will see it).
   - Every `celery-worker-*` manifest's `S3_ENDPOINT_URL` region, if not
     `us-east-1`.

## 2. Command sequence

Run from the repository root, in order. Each `copilot svc deploy` triggers a
Docker build + ECR push + CloudFormation deploy — confirm you're ready for
billable resources before running it.

```bash
# 1. Register the application (creates the Copilot IAM roles/S3 bucket for
#    Copilot's own state -- not the app's S3 bucket, that's the addon below).
copilot app init orm-platform

# 2. Create the environment (VPC, subnets, NAT gateway, ECS cluster, ALB).
copilot env init --name production --profile default --default-config

# 3. Deploy the environment -- this is what actually provisions the VPC/
#    cluster, and picks up copilot/environments/addons/*.yml (RDS,
#    ElastiCache, S3) in the same deploy.
copilot env deploy --name production

# 4. Set every secret referenced in the manifests (see section 3) before
#    deploying any service that needs it -- a service will fail to start if
#    a secret it references doesn't exist yet.

# 5. Deploy the two public-facing services first.
copilot svc deploy --name backend --env production
copilot svc deploy --name frontend --env production

# 6. Deploy the six internal services. Order doesn't matter to Copilot, but
#    celery-beat schedules work for all queues, so deploying the workers
#    first (they'll simply idle with an empty queue) avoids a burst of
#    immediately-due tasks with no worker yet listening.
copilot svc deploy --name celery-worker-io --env production
copilot svc deploy --name celery-worker-cpu --env production
copilot svc deploy --name celery-worker-nlp --env production
copilot svc deploy --name celery-worker-aggregation --env production
copilot svc deploy --name celery-worker-pipeline --env production
copilot svc deploy --name celery-beat --env production
```

Recommended validation before step 5/6, once the Copilot CLI is installed
locally: `copilot svc package --name <service> --output-dir tmp/cfn` renders
the CloudFormation template for a service without deploying anything --
useful for reviewing exactly what a `svc deploy` would create.

## 3. Secrets (`copilot secret init`)

None of these values exist anywhere in this repo. Set each one interactively
(the CLI prompts for the value per environment):

```bash
copilot secret init --name S3_ACCESS_KEY
copilot secret init --name S3_SECRET_KEY
copilot secret init --name GROQ_API_KEY
```

- `S3_ACCESS_KEY` / `S3_SECRET_KEY`: an IAM user's static access key with
  read/write on the addon-created bucket (the app's S3 client passes these
  explicitly rather than using the task role's implicit credentials -- see
  `app/core/s3_client.py`/`app/utils/s3_client.py`). Create a dedicated IAM
  user scoped to just that bucket; don't reuse your deploy user's keys.
- `GROQ_API_KEY`: the AI Reputation Advisor's provider key (see
  `AI_PROVIDER`/`AI_MODEL` in `app/core/config.py`).

`DB_USER`/`DB_PASSWORD` are **not** set this way -- they come from the RDS
addon's auto-generated Secrets Manager secret (`copilot/environments/addons/
rds.yml`), wired into each service's `secrets:` block automatically.

Once `backend` is deployed and healthy, seed the first login user (see
`docs/AUTH.md`):
```bash
copilot svc exec --name backend --env production --command \
  "python scripts/seed_user.py --email admin@example.com --password 'change-me' --role super_admin"
```

## 4. Custom domain + HTTPS

Copilot has built-in support for ACM certificates + Route53, if the domain's
hosted zone is in the same AWS account:

```bash
# One-time, at environment creation/update, for each domain:
copilot env init --name production --default-config --import-cert-arns <acm-cert-arn>
# or, if Copilot should provision the cert itself via Route53 validation:
copilot app init orm-platform --domain your-domain.com
```

Then attach the domain to each public-facing service by adding an `alias:`
field under `http:` in `copilot/backend/manifest.yml` and
`copilot/frontend/manifest.yml`, e.g.:

```yaml
http:
  alias: api.your-domain.com
```

Re-run `copilot svc deploy` for that service after adding the alias --
Copilot provisions the ACM cert (DNS validation via Route53) and updates the
ALB listener automatically. If the domain's DNS is hosted elsewhere, Copilot
will print the validation CNAME records to create manually instead.

## 5. Sizing reference

See the reasoning comments in each file for the full justification --
summarized here for convenience:

| Service | CPU | Memory | Count | Type |
|---|---|---|---|---|
| backend | 512 | 1024 | 2 | Load Balanced Web Service |
| frontend | 256 | 512 | 2 | Load Balanced Web Service |
| celery-worker-io | 512 | 1024 | 1 | Backend Service |
| celery-worker-cpu | 512 | 1024 | 1 | Backend Service |
| celery-worker-nlp | 2048 | 8192 | 1 | Backend Service |
| celery-worker-aggregation | 512 | 1024 | 1 | Backend Service |
| celery-worker-pipeline | 512 | 1024 | 1 | Backend Service |
| celery-beat | 256 | 512 | 1 (fixed -- see manifest comment) | Backend Service |

| Addon | Instance | Notes |
|---|---|---|
| RDS Postgres | db.t4g.micro, 20 GiB gp3, single-AZ | `copilot/environments/addons/rds.yml` |
| ElastiCache Redis | cache.t4g.micro, single node | `copilot/environments/addons/redis.yml` |
| S3 | standard, versioned, 30-day lifecycle on `backups/` | `copilot/environments/addons/s3.yml` |

All of the above are deliberately minimal for a fresh, no-traffic-yet
deployment -- not permanent choices. Revisit RDS/ElastiCache instance class
and Multi-AZ once real usage data exists. celery-worker-nlp's sizing below
(Section 6) is now backed by a real measurement, not a guess.

## 6. celery-worker-nlp memory profiling (real numbers)

Previously `celery-worker-nlp` ran at `--pool=solo --concurrency=1` /
4096 MiB everywhere -- an unmeasured guess (~2.5x the models' stated
parameter-count size) made because the transformer models' real memory
footprint had never been profiled, and `docker-compose.yml`'s local worker
carried the same conservative default for the same reason. This section
replaces that guess with a measured number.

**Method**: `orm_collection/scripts/profile_nlp_memory.py` loads both
models exactly as `intelligence_tasks.py` does at worker-process import
time (FinBERT sentiment + `valhalla/distilbart-mnli-12-3` zero-shot topic,
both `use_mock=False`), then runs them over a batch of ~20 realistic
financial/business-news documents -- mirroring the ~20-concurrent-client
production target -- while sampling RSS via `psutil`. A second run pushed
document length to the 2000-char preprocessing ceiling (`preprocess_text` /
`preprocess_document_text`'s truncation limit) to rule out longer real
articles changing the picture.

**Raw results** (Windows dev machine, CPU inference, `transformers` 5.12,
`torch` 2.12 cpu build):

| Point | RSS |
|---|---|
| Baseline (interpreter + imports, no models) | ~17 MB |
| After FinBERT load | ~767 MB |
| After both models loaded (cold) | ~977 MB |
| **Steady state, both models warmed up on a document batch** | **~1.77-1.80 GB** |

The jump from ~977 MB (cold) to ~1.8 GB happens in the first 5-10 documents
processed (the zero-shot topic classifier's one-forward-pass-per-candidate-
label inference is what drives it -- 10 candidate topics x 20 docs = 200
forward passes) and then holds flat -- confirmed by running 80 unique
documents through the topic classifier alone (plateaus at doc #20 and stays
there through doc #80) and by re-running the combined-model batch with
document lengths pinned to the 2000-char truncation ceiling (plateaus at
~1.80 GB, no further growth). This is PyTorch's CPU allocator reaching a
stable buffer size for the sequence lengths in play, not a leak.

**Working number for sizing: ~1.9 GB per worker process** (rounding the
observed ~1.8 GB plateau up for safety margin).

**Concurrent-process sanity check**: ran 2 of these worker processes
simultaneously (`scripts/_nlp_worker_child.py`, on this same dev machine,
6.8 GB available at the time) -- both completed cleanly with no OOM kill,
at ~1.78 GB RSS each, confirming processes don't share memory savings when
run concurrently (each genuinely duplicates its own model copy, as
expected) and that the single-process number extrapolates linearly.

**Concurrency recommendation by Fargate task memory**, targeting >=20%
memory headroom above N x 1.9GB (OS/container/Celery-process overhead plus
safety margin beyond the measured plateau):

| Task memory | Safe concurrency | Used (N x 1.9GB) | Headroom |
|---|---|---|---|
| 4096 MiB | **1** | 1.9 GB | 54% |
| 8192 MiB | **3** | 5.7 GB | 30% |
| 16384 MiB | **6** | 11.4 GB | 30% |

4096 MiB cannot safely support concurrency=2 (3.8 GB used, only 7%
headroom -- too tight given this was measured on synthetic documents, not
worst-case production text). 8192 MiB's 4th process and 16384 MiB's 7th
process both drop headroom below 20% (7% and 19% respectively) and aren't
recommended without a larger-scale reprofile.

**Chosen default: 8192 MiB / concurrency=3** (`copilot/celery-worker-nlp/
manifest.yml`), trading the previous single-process 4096 MiB setup for 3x
NLP throughput at ~2x the monthly cost -- a reasonable middle point for the
~20-concurrent-client target. Pick a different row from the table above
(edit that manifest's `cpu`/`memory`/`--concurrency`) if cost or the
concurrency target changes; 4096 MiB/concurrency=1 remains the safe
low-cost floor, and 16384 MiB/concurrency=6 is the throughput ceiling this
data supports.
