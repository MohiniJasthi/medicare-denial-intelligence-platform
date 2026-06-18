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
  python ingestion/scripts/download_cms_data.py --list-urls --years 2023
  python ingestion/scripts/download_cms_data.py --years 2023 --only part-d

Environment variables (optional, override defaults):
  DATA_DIR      — target directory for raw files (default: data/raw)
  CMS_YEARS     — comma-separated years to download (default: 2021,2022,2023)

Note: CMS changes direct download links frequently. This script resolves the
current URL from https://data.cms.gov/data.json when static links fail.

NPPES Manual Download Instructions:
  The NPPES full replacement monthly file is too large for automated download
  (it requires agreeing to a license). Steps:
    1. Go to https://download.cms.gov/nppes/NPI_Files.html
    2. Download the most recent "Full Replacement Monthly NPI File"
    3. Unzip and place the CSV at: data/raw/nppes_providers.csv
"""

import argparse
import os
import sys
import time
import logging
import zipfile
from pathlib import Path
from typing import Optional

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

CMS_CATALOG_URL = "https://data.cms.gov/data.json"

# Dataset title fragments used to locate entries in data.cms.gov/data.json
CATALOG_MATCHERS = {
    "part_d": ["Medicare Part D Prescribers", "Provider and Drug"],
    "provider_util": ["Medicare Physician", "Provider and Service"],
}

# Official dataset landing pages (use in browser if automated download fails)
LANDING_PAGES = {
    "part_d": (
        "https://data.cms.gov/provider-summary-by-type-of-service/"
        "medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug"
    ),
    "provider_util": (
        "https://data.cms.gov/provider-summary-by-type-of-service/"
        "medicare-physician-other-practitioners/"
        "medicare-physician-other-practitioners-by-provider-and-service"
    ),
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
    """Ping the CMS catalog to verify connectivity."""
    try:
        resp = requests.head(CMS_CATALOG_URL, timeout=15)
        log.info(f"CMS catalog reachable — HTTP {resp.status_code}")
        return resp.status_code < 400
    except Exception as e:
        log.warning(f"CMS catalog probe failed: {e}")
        return False


def load_cms_catalog() -> list[dict]:
    """Load the official CMS data catalog (data.json)."""
    log.info(f"Fetching CMS catalog: {CMS_CATALOG_URL}")
    response = requests.get(CMS_CATALOG_URL, timeout=120)
    response.raise_for_status()
    return response.json().get("dataset", [])


def find_dataset_in_catalog(catalog: list[dict], dataset_key: str) -> Optional[dict]:
    """Find a dataset entry by title keyword matching."""
    keywords = CATALOG_MATCHERS[dataset_key]
    for dataset in catalog:
        title = dataset.get("title", "")
        if all(keyword in title for keyword in keywords):
            return dataset
    return None


def find_csv_url_in_catalog(dataset: dict, year: int) -> Optional[str]:
    """Return the CSV downloadURL for a given year from a catalog dataset."""
    year_str = str(year)
    matches = []

    for distro in dataset.get("distribution", []):
        media_type = (distro.get("mediaType") or "").lower()
        if media_type not in {"text/csv", "application/csv"}:
            continue

        blob = " ".join(
            str(distro.get(field, ""))
            for field in ("title", "description", "downloadURL", "temporal")
        )
        if year_str in blob:
            matches.append(distro)

    if not matches:
        return None

    # Prefer entries whose title/description explicitly mention the year.
    matches.sort(
        key=lambda d: (
            year_str not in str(d.get("title", "")),
            year_str not in str(d.get("description", "")),
        )
    )
    return matches[0].get("downloadURL")


def resolve_download_url(dataset_key: str, year: int, catalog: list[dict]) -> Optional[str]:
    """
    Resolve a download URL using:
      1) CMS data.json catalog (current links)
      2) Legacy static CSV URL map
      3) CMS datastore CSV API template (Part D only)
    """
    dataset = find_dataset_in_catalog(catalog, dataset_key)
    if dataset:
        url = find_csv_url_in_catalog(dataset, year)
        if url:
            log.info(f"[{dataset_key} {year}] Resolved URL from CMS catalog")
            return url

    static_map = PART_D_CSV_URLS if dataset_key == "part_d" else PROVIDER_UTIL_CSV_URLS
    if year in static_map:
        log.info(f"[{dataset_key} {year}] Falling back to legacy static URL")
        return static_map[year]

    if dataset_key == "part_d":
        log.info(f"[{dataset_key} {year}] Falling back to CMS datastore API URL")
        return PART_D_URL_TEMPLATE.format(year=year)

    return None


def list_download_urls(years: list[int], datasets: list[str]) -> None:
    """Print resolved download URLs without downloading files."""
    catalog = load_cms_catalog()
    log.info("\n── Resolved CMS download URLs ───────────────────────────────")
    for dataset_key in datasets:
        log.info(f"\n{dataset_key}:")
        log.info(f"  Landing page: {LANDING_PAGES[dataset_key]}")
        for year in years:
            url = resolve_download_url(dataset_key, year, catalog)
            log.info(f"  {year}: {url or 'NOT FOUND — use landing page manually'}")


def extract_csv_from_zip(zip_path: Path, dest_csv: Path) -> bool:
    """Extract the largest CSV from a downloaded ZIP into dest_csv."""
    with zipfile.ZipFile(zip_path, "r") as archive:
        csv_members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
        if not csv_members:
            log.error(f"No CSV found inside ZIP: {zip_path}")
            return False
        largest = max(csv_members, key=lambda name: archive.getinfo(name).file_size)
        log.info(f"Extracting {largest} from {zip_path.name}")
        with archive.open(largest) as src, open(dest_csv, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
    zip_path.unlink(missing_ok=True)
    return True


def download_dataset_year(
    dataset_key: str,
    year: int,
    dest: Path,
    catalog: list[dict],
) -> bool:
    """Download one yearly file, handling CSV or ZIP responses."""
    url = resolve_download_url(dataset_key, year, catalog)
    if not url:
        log.error(
            f"[{dataset_key} {year}] No download URL found. "
            f"Open manually: {LANDING_PAGES[dataset_key]}"
        )
        return False

    label = f"{dataset_key} {year}"
    temp_zip = dest.with_suffix(".zip.tmp")

    # Try direct CSV download first.
    if download_file(url, dest, description=label):
        return True

    # Some catalog links return ZIP archives.
    log.info(f"[{label}] Direct CSV failed — trying ZIP response")
    if download_file(url, temp_zip, description=f"{label} (zip)"):
        try:
            return extract_csv_from_zip(temp_zip, dest)
        except zipfile.BadZipFile:
            log.error(f"[{label}] Downloaded file is not a valid ZIP")
            temp_zip.unlink(missing_ok=True)

    log.error(
        f"[{label}] All download methods failed.\n"
        f"  1. Open: {LANDING_PAGES[dataset_key]}\n"
        f"  2. Download the {year} CSV manually\n"
        f"  3. Save as: {dest.resolve()}"
    )
    return False


# ── Download functions ────────────────────────────────────────────────────────

def download_part_d_data(
    data_dir: Path,
    years: list[int],
    catalog: list[dict],
) -> list[Path]:
    """Download Medicare Part D Prescribers by Provider and Drug for each year."""
    downloaded = []
    for year in years:
        dest = data_dir / f"cms_part_d_spending_{year}.csv"
        if dest.exists():
            log.info(f"[Part D {year}] Already downloaded — skipping ({dest})")
            downloaded.append(dest)
            continue

        if download_dataset_year("part_d", year, dest, catalog):
            downloaded.append(dest)

    return downloaded


def download_provider_utilization(
    data_dir: Path,
    years: list[int],
    catalog: list[dict],
) -> list[Path]:
    """Download Medicare Physician and Other Practitioners utilization data."""
    downloaded = []
    for year in years:
        dest = data_dir / f"cms_provider_utilization_{year}.csv"
        if dest.exists():
            log.info(f"[Provider Util {year}] Already downloaded — skipping ({dest})")
            downloaded.append(dest)
            continue

        if download_dataset_year("provider_util", year, dest, catalog):
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

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download CMS datasets into data/raw/")
    parser.add_argument(
        "--years",
        default=",".join(str(y) for y in CMS_YEARS),
        help="Comma-separated years, e.g. 2023 or 2021,2022,2023",
    )
    parser.add_argument(
        "--only",
        choices=["part-d", "provider-util", "all"],
        default="all",
        help="Download only one dataset family",
    )
    parser.add_argument(
        "--list-urls",
        action="store_true",
        help="Print resolved download URLs and exit (no download)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    log.info("=" * 60)
    log.info("Medicare Claim Denial Platform — CMS Data Downloader")
    log.info(f"Target directory : {DATA_DIR.resolve()}")
    log.info(f"Years            : {years}")
    log.info("=" * 60)

    datasets = ["part_d", "provider_util"]
    if args.only == "part-d":
        datasets = ["part_d"]
    elif args.only == "provider-util":
        datasets = ["provider_util"]

    if args.list_urls:
        list_download_urls(years, datasets)
        return

    ensure_data_dir(DATA_DIR)

    available = check_cms_availability()
    if not available:
        log.warning("CMS catalog may be unreachable — downloads may fail. Continuing anyway.")

    catalog = load_cms_catalog()
    results: dict[str, int] = {}

    if "part_d" in datasets:
        log.info("\n── Downloading Medicare Part D Spending ─────────────────────")
        part_d_files = download_part_d_data(DATA_DIR, years, catalog)
        results["part_d"] = len(part_d_files)

    if "provider_util" in datasets:
        log.info("\n── Downloading Medicare Provider Utilization ────────────────")
        util_files = download_provider_utilization(DATA_DIR, years, catalog)
        results["provider_utilization"] = len(util_files)

    # NPPES (manual)
    log.info("\n── Checking NPPES NPI Registry ──────────────────────────────")
    check_nppes_file(DATA_DIR)

    # Summary
    log.info("\n" + "=" * 60)
    log.info("Download Summary:")
    log.info(f"  Part D files downloaded     : {results.get('part_d', 0)}")
    log.info(f"  Provider util files         : {results.get('provider_utilization', 0)}")
    log.info(f"  Target directory            : {DATA_DIR.resolve()}")
    log.info("=" * 60)

    if sum(results.values()) == 0:
        log.error("No files were downloaded. Try: python ingestion/scripts/download_cms_data.py --list-urls --years 2023")
        sys.exit(1)

    log.info("Done. Next step: run ingestion/scripts/load_to_postgres.py")


if __name__ == "__main__":
    main()
