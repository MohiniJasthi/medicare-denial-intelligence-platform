"""
download_cms_data.py
=====================
Downloads CMS public datasets for the Medicare Claim Denial Intelligence Platform.

Datasets:
  1. Medicare Part D Prescribers by Provider and Drug (multi-year)
  2. Medicare Physician and Other Practitioners by Provider and Service (multi-year)
  3. NPPES NPI Registry bulk file (manual download — see instructions below)

Usage:
  python ingestion/scripts/download_cms_data.py

Environment variables (optional, override defaults):
  DATA_DIR      — target directory for raw files (default: data/raw)
  CMS_YEARS     — comma-separated years to download (default: 2021,2022,2023)

NPPES Manual Download Instructions:
  The NPPES full replacement monthly file is too large for automated download
  (it requires agreeing to a license). Steps:
    1. Go to https://download.cms.gov/nppes/NPI_Files.html
    2. Download the most recent "Full Replacement Monthly NPI File"
    3. Unzip and place the CSV at: data/raw/nppes_providers.csv
"""

import os
import sys
import time
import logging
from pathlib import Path

import requests
from tqdm import tqdm

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
DATA_DIR = Path(os.environ.get("DATA_DIR", "data/raw"))
CMS_YEARS = [
    int(y) for y in os.environ.get("CMS_YEARS", "2021,2022,2023").split(",")
]

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
CHUNK_SIZE = 8192  # bytes per streaming chunk

# ── CMS API / Direct-download URLs ────────────────────────────────────────────
# These are the stable CMS data.cms.gov direct CSV export endpoints.
# CMS publishes these datasets annually; update year suffixes as new data drops.

PART_D_URL_TEMPLATE = (
    "https://data.cms.gov/provider-summary-by-type-of-service/"
    "medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug/"
    "api/1/datastore/query/{year}/0?offset=0&count=true&results=true&schema=true"
    "&keys=true&format=csv&rowIds=false"
)

# Fallback: stable direct CSV links maintained by CMS
PART_D_CSV_URLS = {
    2021: "https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug/data/2021/Medicare_Part_D_Prescribers_by_Provider_and_Drug_2021.csv",
    2022: "https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug/data/2022/Medicare_Part_D_Prescribers_by_Provider_and_Drug_2022.csv",
    2023: "https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug/data/2023/Medicare_Part_D_Prescribers_by_Provider_and_Drug_2023.csv",
}

PROVIDER_UTIL_CSV_URLS = {
    2021: "https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service/data/2021/Medicare_Physician_Other_Practitioners_by_Provider_and_Service_2021.csv",
    2022: "https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service/data/2022/Medicare_Physician_Other_Practitioners_by_Provider_and_Service_2022.csv",
    2023: "https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service/data/2023/Medicare_Physician_Other_Practitioners_by_Provider_and_Service_2023.csv",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def ensure_data_dir(path: Path) -> None:
    """Create the data directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)
    log.info(f"Data directory: {path.resolve()}")


def download_file(url: str, dest_path: Path, description: str = "") -> bool:
    """
    Download a file from `url` to `dest_path` with a tqdm progress bar.
    Retries up to MAX_RETRIES times on transient errors.
    Returns True on success, False on failure.
    """
    label = description or dest_path.name

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info(f"[{label}] Attempt {attempt}/{MAX_RETRIES}: GET {url}")
            response = requests.get(url, stream=True, timeout=120)
            response.raise_for_status()

            total_bytes = int(response.headers.get("content-length", 0))

            with open(dest_path, "wb") as f, tqdm(
                desc=label,
                total=total_bytes if total_bytes > 0 else None,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                leave=True,
            ) as bar:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        bar.update(len(chunk))

            file_mb = dest_path.stat().st_size / (1024 * 1024)
            log.info(f"[{label}] Saved to {dest_path} ({file_mb:.1f} MB)")
            return True

        except requests.exceptions.HTTPError as e:
            log.warning(f"[{label}] HTTP error on attempt {attempt}: {e}")
        except requests.exceptions.ConnectionError as e:
            log.warning(f"[{label}] Connection error on attempt {attempt}: {e}")
        except requests.exceptions.Timeout:
            log.warning(f"[{label}] Timeout on attempt {attempt}")
        except Exception as e:
            log.error(f"[{label}] Unexpected error: {e}")
            return False

        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_SECONDS * attempt
            log.info(f"[{label}] Retrying in {wait}s...")
            time.sleep(wait)

    log.error(f"[{label}] Failed after {MAX_RETRIES} attempts.")
    return False


def check_cms_availability() -> bool:
    """Ping the CMS API to verify connectivity."""
    probe_url = "https://data.cms.gov/api/1/metastore/schemas/dataset/items?limit=1"
    try:
        resp = requests.head(probe_url, timeout=15)
        log.info(f"CMS API reachable — HTTP {resp.status_code}")
        return resp.status_code < 400
    except Exception as e:
        log.warning(f"CMS API probe failed: {e}")
        return False


# ── Download functions ────────────────────────────────────────────────────────

def download_part_d_data(data_dir: Path, years: list[int]) -> list[Path]:
    """Download Medicare Part D Prescribers by Provider and Drug for each year."""
    downloaded = []
    for year in years:
        dest = data_dir / f"cms_part_d_spending_{year}.csv"
        if dest.exists():
            log.info(f"[Part D {year}] Already downloaded — skipping ({dest})")
            downloaded.append(dest)
            continue

        url = PART_D_CSV_URLS.get(year)
        if not url:
            log.warning(f"[Part D {year}] No URL configured for year {year} — skipping")
            continue

        success = download_file(url, dest, description=f"Part D Spending {year}")
        if success:
            downloaded.append(dest)

    return downloaded


def download_provider_utilization(data_dir: Path, years: list[int]) -> list[Path]:
    """Download Medicare Physician and Other Practitioners utilization data."""
    downloaded = []
    for year in years:
        dest = data_dir / f"cms_provider_utilization_{year}.csv"
        if dest.exists():
            log.info(f"[Provider Util {year}] Already downloaded — skipping ({dest})")
            downloaded.append(dest)
            continue

        url = PROVIDER_UTIL_CSV_URLS.get(year)
        if not url:
            log.warning(f"[Provider Util {year}] No URL configured for year {year} — skipping")
            continue

        success = download_file(url, dest, description=f"Provider Utilization {year}")
        if success:
            downloaded.append(dest)

    return downloaded


def check_nppes_file(data_dir: Path) -> None:
    """
    NPPES bulk file requires a manual download due to license agreement.
    This function just checks if it's present and prints instructions if not.
    """
    nppes_path = data_dir / "nppes_providers.csv"
    if nppes_path.exists():
        file_mb = nppes_path.stat().st_size / (1024 * 1024)
        log.info(f"[NPPES] Found at {nppes_path} ({file_mb:.1f} MB) ✓")
    else:
        log.warning(
            "\n"
            "=" * 70 + "\n"
            "NPPES NPI Registry file NOT found.\n"
            "\n"
            "To download it manually:\n"
            "  1. Go to: https://download.cms.gov/nppes/NPI_Files.html\n"
            "  2. Download 'Full Replacement Monthly NPI File' (latest month)\n"
            "  3. Unzip the archive\n"
            "  4. Rename/copy the main CSV to:\n"
            f"     {nppes_path.resolve()}\n"
            "\n"
            "Note: The file is ~8 GB uncompressed. Ensure you have disk space.\n"
            "=" * 70
        )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    log.info("=" * 60)
    log.info("Medicare Claim Denial Platform — CMS Data Downloader")
    log.info(f"Target directory : {DATA_DIR.resolve()}")
    log.info(f"Years            : {CMS_YEARS}")
    log.info("=" * 60)

    ensure_data_dir(DATA_DIR)

    # Connectivity check
    available = check_cms_availability()
    if not available:
        log.warning("CMS API may be unreachable — downloads may fail. Continuing anyway.")

    results = {}

    # Part D spending
    log.info("\n── Downloading Medicare Part D Spending ─────────────────────")
    part_d_files = download_part_d_data(DATA_DIR, CMS_YEARS)
    results["part_d"] = len(part_d_files)

    # Provider utilization
    log.info("\n── Downloading Medicare Provider Utilization ────────────────")
    util_files = download_provider_utilization(DATA_DIR, CMS_YEARS)
    results["provider_utilization"] = len(util_files)

    # NPPES (manual)
    log.info("\n── Checking NPPES NPI Registry ──────────────────────────────")
    check_nppes_file(DATA_DIR)

    # Summary
    log.info("\n" + "=" * 60)
    log.info("Download Summary:")
    log.info(f"  Part D files downloaded     : {results['part_d']}")
    log.info(f"  Provider util files         : {results['provider_utilization']}")
    log.info(f"  Target directory            : {DATA_DIR.resolve()}")
    log.info("=" * 60)

    if results["part_d"] == 0 and results["provider_utilization"] == 0:
        log.error("No files were downloaded. Check network connectivity and URLs.")
        sys.exit(1)

    log.info("Done. Next step: run ingestion/scripts/load_to_postgres.py")


if __name__ == "__main__":
    main()
