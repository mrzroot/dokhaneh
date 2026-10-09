<div align="center">

# Dokhaneh · دوخانه

**One release, two homes.** Publish every release to GitHub *and* to domestic hosts at the same time,
with an Ed25519-signed manifest that proves every mirror carries exactly the same bytes.

[![CI](https://github.com/mrzroot/dokhaneh/actions/workflows/ci.yml/badge.svg)](https://github.com/mrzroot/dokhaneh/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

[English](#english) · [فارسی](#فارسی)

</div>

---

## English

### Why

When Iran switches to the national-information-network-only mode, or GitHub drops off a whitelist
(Russia's allowlists raise the same problem), users inside the country lose access to `github.com`
release downloads, `install.sh` one-liners and docs sites. Open-source projects go dark for them
overnight.

**Dokhaneh** ("two houses") keeps your project reachable by publishing each release to two kinds of home
at once:

| Home | Targets |
|------|---------|
| 🌍 **Global** | GitHub Releases |
| 🏠 **Domestic** | ArvanCloud Object Storage (S3), Liara Object Storage (S3), any S3-compatible bucket, self-hosted Gitea/Forgejo (git mirror + releases) |

Then it gives users a generated `install.sh` that tries GitHub first and falls back to the domestic mirrors,
and refuses to install anything whose signature or hash doesn't match.

> **Not a circumvention tool.** Dokhaneh doesn't touch proxies, VPNs or filtering. It only uploads *your own*
> releases to legitimate hosting providers you have accounts with, the same way you'd add a second CDN.

### Features

- 📦 **One config, many targets**: `dokhaneh.yml` describes artifacts, docs and targets. Secrets come only from env vars.
- 🔏 **Signed manifest**: `manifest.json` lists every file's SHA-256 and size, signed with Ed25519 (PyNaCl).
  Every mirror gets byte-identical copies, so one public key verifies them all.
- ✅ **`dokhaneh verify`** checks a local manifest and files, or fetches the manifest from **every** mirror and
  proves they all serve the same signed release (`--deep` re-hashes every file).
- 🧯 **Fallback `install.sh`**: a POSIX sh script that tries global → domestic sources, verifies the signature with
  `openssl`, checks SHA-256, then installs. Tampered or stale mirrors are skipped.
- 📡 **`dokhaneh status`** probes each target from wherever you run it (inside Iran, outside, CI) and reports
  UP / MISSING / DOWN with latency.
- 📚 **Docs too**: a static docs folder (MkDocs, Docusaurus, …) is uploaded as a browsable site to the S3 mirrors
  and as a signed `*-docs.tar.gz` asset everywhere.
- 🤖 **Composite GitHub Action**: add one step to your tag workflow.
- 🧱 **Fault-isolated**: one mirror failing never blocks the others. The exit code tells you if anything failed.

### Install

```bash
pip install git+https://github.com/mrzroot/dokhaneh
dokhaneh --help
```

### Quick start

```bash
dokhaneh init        # writes a commented dokhaneh.yml
dokhaneh keygen      # prints an Ed25519 keypair
```

Put the **public** key in `dokhaneh.yml` and keep the **private** key as the secret `DOKHANEH_SIGNING_KEY`.

```yaml
project:
  name: myapp
  tag: "v{version}"            # version comes from the git tag, --version, or project.version

artifacts: ["dist/*.tar.gz", "dist/*.zip"]
docs: site/

signing:
  private_key_env: DOKHANEH_SIGNING_KEY
  public_key: "PASTE_OUTPUT_OF_dokhaneh_keygen"

install:
  asset: "myapp-{version}-linux-amd64.tar.gz"
  binary: myapp

targets:
  - name: github
    type: github
    repo: myorg/myapp
    token_env: GITHUB_TOKEN

  - name: arvan
    type: arvan                       # endpoint/public URL defaults for ArvanCloud ir-thr-at1
    bucket: myapp-releases
    access_key_env: ARVAN_ACCESS_KEY
    secret_key_env: ARVAN_SECRET_KEY

  - name: liara
    type: liara                       # default endpoint https://storage.c2.liara.site
    bucket: myapp
    access_key_env: LIARA_ACCESS_KEY
    secret_key_env: LIARA_SECRET_KEY

  - name: gitea
    type: gitea
    url: https://git.example.ir
    repo: myorg/myapp
    token_env: GITEA_TOKEN
    mirror: true                      # push HEAD → branch, plus all tags
    branch: main
```

```bash
dokhaneh publish --version 1.2.0 --dry-run   # sign + show the upload plan
dokhaneh publish --version 1.2.0             # do it
dokhaneh verify  --version 1.2.0 --deep      # every mirror serves identical, signed bytes?
dokhaneh status  --version 1.2.0             # what is reachable from here, right now?
```

Example `status` output from a network that can't reach GitHub:

```text
DOWN    github  global    ---  10003ms  https://github.com/myorg/myapp/releases/download/v1.2.0/manifest.json
UP      arvan   domestic  200     41ms  https://myapp-releases.s3.ir-thr-at1.arvanstorage.ir/releases/1.2.0/manifest.json
UP      liara   domestic  200     38ms  https://myapp.storage.c2.liara.site/releases/1.2.0/manifest.json
UP      gitea   domestic  200     55ms  https://git.example.ir/myorg/myapp/releases/download/v1.2.0/manifest.json
3/4 targets reachable, 3/4 release found
```

### GitHub Action

```yaml
# .github/workflows/release.yml
on:
  push:
    tags: ["v*"]
permissions:
  contents: write
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      # … build dist/ and site/ …
      - uses: mrzroot/dokhaneh@v0.1.0
        with:
          signing-key: ${{ secrets.DOKHANEH_SIGNING_KEY }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ARVAN_ACCESS_KEY: ${{ secrets.ARVAN_ACCESS_KEY }}
          ARVAN_SECRET_KEY: ${{ secrets.ARVAN_SECRET_KEY }}
          LIARA_ACCESS_KEY: ${{ secrets.LIARA_ACCESS_KEY }}
          LIARA_SECRET_KEY: ${{ secrets.LIARA_SECRET_KEY }}
          GITEA_TOKEN: ${{ secrets.GITEA_TOKEN }}
```

| Input | Default | Description |
|-------|---------|-------------|
| `command` | `publish` | `publish`, `sign`, `verify` or `status` |
| `config` | `dokhaneh.yml` | config path |
| `version` | tag | release version |
| `only` | all | comma-separated target names |
| `dry-run` | `false` | sign + plan only |
| `deep` | `false` | `verify`: re-hash every file on every mirror |
| `signing-key` | – | base64 Ed25519 private key (secret) |

Outputs: `version`, `manifest`, `succeeded`, `failed`. A full example is in [`examples/release.yml`](examples/release.yml).

### What gets published where

```
GitHub / Gitea release  v1.2.0
  ├─ myapp-1.2.0-linux-amd64.tar.gz, … (your artifacts)
  ├─ myapp-1.2.0-docs.tar.gz            (if docs: is set)
  ├─ install.sh
  ├─ manifest.json                      (all of the above + SHA-256)
  └─ manifest.json.sig                  (Ed25519, base64)

S3 bucket (Arvan / Liara / generic)
  ├─ releases/1.2.0/…                   (same files as above)
  ├─ releases/latest/…                  (overwritten on each release)
  ├─ install.sh                         (latest installer)
  └─ docs/…                             (browsable static site)
```

### The installer

```bash
curl -fsSL https://myapp-releases.s3.ir-thr-at1.arvanstorage.ir/install.sh | sh
```

For each source, global first, the script:

1. downloads `manifest.json` and `manifest.json.sig`,
2. verifies the Ed25519 signature against the public key embedded in the script (`openssl pkeyutl -rawin`, OpenSSL ≥ 3.0),
3. checks that the manifest is for the expected version (no rollback to an older signed release),
4. downloads the asset and compares its SHA-256,
5. on any failure, moves on to the next mirror.

Overrides: `DOKHANEH_SOURCES`, `DOKHANEH_INSTALL_DIR`, `DOKHANEH_OUT_DIR`, `DOKHANEH_ASSET`, `DOKHANEH_TIMEOUT`.

### Security model

- The private key signs; it is only read from an env var and never written to disk by `publish`.
- `publish` refuses to sign if the private key doesn't match `signing.public_key`.
- A compromised mirror can withhold files, but can't serve modified ones without failing verification.
- Gitea push URLs carry the token only in-process, and it is redacted from all error output.
- Distribute your public key through more than one channel (README, website, the script itself).

### Configuration reference

| Target type | Required | Optional |
|-------------|----------|----------|
| `github` | `repo` | `token_env` (default `GITHUB_TOKEN`), `api_url`, `uploads_url`, `web_url` (GHES) |
| `s3` | `bucket`, `endpoint`, `public_url` | `prefix`, `acl` (default `public-read`, `""` to disable), `region_name`, `addressing_style`, `latest`, `docs`, `access_key_env`, `secret_key_env` |
| `arvan` | `bucket` | same as `s3`. `endpoint` defaults to `https://s3.ir-thr-at1.arvanstorage.ir` |
| `liara` | `bucket` | same as `s3`. `endpoint` defaults to `https://storage.c2.liara.site` (copy yours from the Liara panel) |
| `gitea` | `url`, `repo` | `token_env` (default `GITEA_TOKEN`), `mirror`, `branch`, `release`, `force`, `username`, `push_url` |

All targets accept `region: global|domestic` to control installer ordering. Any string value may use `${ENV}` or `${ENV:-default}`.

### Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest            # GitHub/Gitea mocked with respx, S3 with moto, install.sh run for real against file:// mirrors
ruff check src tests
```

---

<div dir="rtl" align="right">

## فارسی

### چرا دوخانه؟

وقتی اینترنت ایران به حالت «فقط شبکهٔ ملی» می‌رود یا GitHub از لیست سفید حذف می‌شود (همین مشکل با
لیست‌های سفید روسیه هم وجود دارد)، کاربران داخل کشور دیگر به دانلودهای Release، اسکریپت‌های نصب و
سایت مستندات روی GitHub دسترسی ندارند و پروژه‌های متن‌باز عملاً برایشان از دسترس خارج می‌شوند.

**دوخانه** هر نسخه را هم‌زمان در دو «خانه» منتشر می‌کند:

| خانه | مقصدها |
|------|---------|
| 🌍 **جهانی** | GitHub Releases |
| 🏠 **داخلی** | فضای ابری آروان‌کلاد (S3)، فضای ذخیره‌سازی لیارا (S3)، هر باکت سازگار با S3، و Gitea/Forgejo شخصی (آینهٔ git و Release) |

یک `install.sh` هم ساخته می‌شود که اول از GitHub دانلود می‌کند و اگر در دسترس نبود سراغ آینه‌های داخلی
می‌رود. اگر امضا یا هش فایل درست نباشد، چیزی نصب نمی‌شود.

> **دوخانه ابزار دور زدن فیلترینگ نیست.** با پروکسی، VPN یا فیلترینگ هیچ کاری ندارد. فقط نسخه‌های
> *پروژهٔ خودتان* را روی سرویس‌دهنده‌های قانونی که در آن‌ها حساب دارید بارگذاری می‌کند؛ مثل اضافه کردن یک CDN دوم.

### امکانات

- 📦 **یک پیکربندی، چند مقصد**: فایل `dokhaneh.yml`. کلیدهای محرمانه فقط از متغیرهای محیطی خوانده می‌شوند.
- 🔏 **مانیفست امضاشده**: فایل `manifest.json` هش SHA-256 و اندازهٔ همهٔ فایل‌ها را دارد و با Ed25519 امضا
  می‌شود. همهٔ آینه‌ها دقیقاً همین بایت‌ها را دریافت می‌کنند، پس یک کلید عمومی برای راستی‌آزمایی همه کافی است.
- ✅ **`dokhaneh verify`**: بررسی مانیفست و فایل‌های محلی، یا دریافت مانیفست از **همهٔ** آینه‌ها و اثبات اینکه
  همه یک نسخهٔ امضاشده را ارائه می‌دهند (با `--deep` هش همهٔ فایل‌ها هم بررسی می‌شود).
- 🧯 **`install.sh` با جایگزین خودکار**: اسکریپت POSIX که منابع را به ترتیب جهانی ← داخلی امتحان می‌کند، امضا را با
  `openssl` و هش را با SHA-256 بررسی می‌کند و آینه‌های دست‌کاری‌شده یا قدیمی را کنار می‌گذارد.
- 📡 **`dokhaneh status`**: وضعیت دسترسی به هر مقصد را از همان جایی که اجرا می‌کنید (داخل ایران، خارج یا CI)
  نشان می‌دهد: UP یا MISSING یا DOWN، به همراه تأخیر.
- 📚 **مستندات**: پوشهٔ سایت ایستا روی آینه‌های S3 به شکل سایت قابل مرور بارگذاری می‌شود و به صورت
  `*-docs.tar.gz` امضاشده در همهٔ مقصدها قرار می‌گیرد.
- 🤖 **GitHub Action ترکیبی**: فقط یک step به workflow تگ اضافه کنید.
- 🧱 **مستقل از خطا**: خرابی یک آینه جلوی بقیه را نمی‌گیرد.

### نصب

</div>

```bash
pip install git+https://github.com/mrzroot/dokhaneh
```

<div dir="rtl" align="right">

### شروع سریع

</div>

```bash
dokhaneh init      # ساخت dokhaneh.yml نمونه
dokhaneh keygen    # ساخت جفت‌کلید Ed25519
```

<div dir="rtl" align="right">

کلید **عمومی** را در `dokhaneh.yml` بگذارید و کلید **خصوصی** را به عنوان secret با نام
`DOKHANEH_SIGNING_KEY` ذخیره کنید. هرگز کلید خصوصی را commit نکنید.

</div>

```bash
dokhaneh publish --version 1.2.0 --dry-run   # امضا و نمایش برنامهٔ بارگذاری
dokhaneh publish --version 1.2.0             # انتشار در همهٔ مقصدها
dokhaneh verify  --version 1.2.0 --deep      # آیا همهٔ آینه‌ها یکسان و امضاشده‌اند؟
dokhaneh status  --version 1.2.0             # از این شبکه چه چیزی در دسترس است؟
```

<div dir="rtl" align="right">

### استفاده در GitHub Actions

</div>

```yaml
- uses: mrzroot/dokhaneh@v0.1.0
  with:
    signing-key: ${{ secrets.DOKHANEH_SIGNING_KEY }}
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    ARVAN_ACCESS_KEY: ${{ secrets.ARVAN_ACCESS_KEY }}
    ARVAN_SECRET_KEY: ${{ secrets.ARVAN_SECRET_KEY }}
    LIARA_ACCESS_KEY: ${{ secrets.LIARA_ACCESS_KEY }}
    LIARA_SECRET_KEY: ${{ secrets.LIARA_SECRET_KEY }}
    GITEA_TOKEN: ${{ secrets.GITEA_TOKEN }}
```

<div dir="rtl" align="right">

### نصب برای کاربران نهایی

کاربران داخل ایران می‌توانند مستقیم از آینهٔ داخلی نصب کنند:

</div>

```bash
curl -fsSL https://myapp-releases.s3.ir-thr-at1.arvanstorage.ir/install.sh | sh
```

<div dir="rtl" align="right">

اسکریپت برای هر منبع این مراحل را انجام می‌دهد: دریافت `manifest.json` و امضای آن، بررسی امضای Ed25519 با
کلید عمومی داخل اسکریپت، اطمینان از اینکه نسخه همان نسخهٔ مورد انتظار است (جلوگیری از بازگشت به نسخهٔ قدیمی)،
دانلود فایل و مقایسهٔ SHA-256. اگر هر مرحله شکست بخورد، آینهٔ بعدی امتحان می‌شود.

### نکات امنیتی

- کلید خصوصی فقط از متغیر محیطی خوانده می‌شود.
- اگر کلید خصوصی با `signing.public_key` مطابقت نداشته باشد، انتشار انجام نمی‌شود.
- یک آینهٔ آلوده می‌تواند فایل را ارائه ندهد، اما نمی‌تواند فایل تغییر‌یافته را بدون شکست در راستی‌آزمایی تحویل دهد.
- توکن Gitea در همهٔ پیام‌های خطا پنهان می‌شود.
- کلید عمومی خود را از چند کانال منتشر کنید (README، وب‌سایت، خود اسکریپت).

### مشارکت

مشارکت شما خوشحالمان می‌کند! برای افزودن مقصد جدید (مثلاً یک سرویس‌دهندهٔ داخلی دیگر) کافی است یک کلاس از
`dokhaneh.targets.base.Target` بسازید و در `REGISTRY` ثبت کنید. تست‌ها را با `pytest` اجرا کنید.

</div>

---

## License · مجوز

[MIT](LICENSE) © mrzroot
