# Data source register

Availability investigated and executed on 2026-11-04. Acquisition metadata lives beside each raw response; checksums tie observations to model registry records. Source URLs in those manifests are the exact requests used.

## CAISO actual demand — executed

- Official source: California ISO OASIS. Documentation: https://www.caiso.com/documents/oasisapispecification.pdf and https://www.caiso.com/documents/oasis-frequently-asked-questions.pdf
- Endpoint: `https://oasis.caiso.com/oasisapi/SingleZip`
- Parameters: `queryname=SLD_FCST`, `market_run_id=ACTUAL`, `version=1`, `resultformat=6`, UTC `startdatetime` / `enddatetime` in `YYYYMMDDTHH:MM-0000` format.
- Representation: total actual hourly integrated load; select **CA ISO-TAC**, not individual TACs, other balancing areas or forecast runs.
- Resolution/unit: hourly, MW average integrated load; geographic scope CAISO system, not every California balancing authority.
- Executed historical period: 2024-01-01 through 2025-12-31 UTC. One missing hour, 2024-08-31 17:00 UTC. No imputation.
- Role: demand target; delayed lags and rolling/calendar features.
- Practical window: current OASIS portal describes roughly 39 months online; older market archives use a separate historical bulk downloader, with market prices back to 2016. No claim that longer demand histories were acquired or validated.

## CAISO NP15 day-ahead LMP — executed

- Same official endpoint, `queryname=PRC_LMP`, `market_run_id=DAM`, `node=TH_NP15_GEN-APND`, `version=12`, `resultformat=6`.
- Select only `LMP_TYPE=LMP` total price; do not treat congestion, energy, loss and GHG component rows as extra prices.
- Hourly **USD/MWh**, even though the generic source value column is named `MW`.
- Scope: North Path 15 generation trading hub; not market-wide, not every California location, not retail prices.
- Executed window: all 17,544 UTC hours in 2024–2025, including 559 negative prices; no missing hours. Real-time prices were not acquired or mixed in.
- Role: separate price target and delayed price-history features. Short-horizon delivery-anchored DAM results are research comparisons, not an auction-ready operational forecast.

CAISO data usage is governed by https://www.caiso.com/privacy-terms-of-use . This is not a CC0 dataset, and the code's MIT license does not license source data. Reproduction scripts download from CAISO directly; exclude raw data/model artifacts from Git. Review applicable CAISO terms before redistribution or commercial use; no legal permission is inferred from public accessibility.

## EIA — availability verified, reference only

- Official Form EIA-930, hourly CISO demand. Methodology: https://www.eia.gov/electricity/930-content/about.html
- Endpoint: `https://api.eia.gov/v2/electricity/rto/region-data/data/`
- Query: hourly frequency, `data[0]=value`, respondent CISO, type D. A 48-hour Jan 1–2, 2024 sample was downloaded with the documented demonstration API key. API response supplies **megawatthours**, which must not be silently relabeled as MW across aggregation conventions.
- API route metadata returned available history starting 2019-01-01; the full available series was not acquired or verified. No annual bulk endpoint is presumed working.
- A guessed old CSV URL redirected then returned HTTP 503; a guessed XLSX route was not adopted. The official API data route worked.
- EIA timestamps/source reporting conventions and revision differences need explicit reconciliation before comparison or merging. This sample is not a substitute for missing CAISO load.
- EIA public data policy: https://www.eia.gov/about/copyrights_reuse.php ; attribute EIA, note source-data qualifications and third-party content exceptions. A personal API key is recommended for sustained use; keep it server-side.

## Open-Meteo historical weather — executed for retrospective EDA only

- Official endpoint: `https://archive-api.open-meteo.com/v1/archive`.
- Documentation: https://open-meteo.com/en/docs/historical-weather-api
- Sacramento location 38.58, -121.49; hourly temperature_2m (C), relative_humidity_2m (%), wind_speed_10m (km/h), UTC, 2024-01-01 to 2025-12-31.
- The response is **gridded reanalysis/model-estimated weather**, not a station observation archive or an archived forecast vintage. The default blended dataset is preserved as downloaded; its selection can change across future requests. Raw response and checksum fix this release's input.
- One grid cell is illustrative, not population/load-weighted California weather. Missing-weather counts are reported from the acquired payload; the scatter uses only matched nonmissing hours.
- No forecast features or operational weather sensitivities use this data. Its role is a descriptive demand-temperature association.
- Source data attribution: Open-Meteo historical reanalysis, CC BY 4.0. See https://open-meteo.com/en/terms and pricing/service restrictions at https://open-meteo.com/en/pricing . Data licensing and free API service access are distinct; this local research uses the free service, not an approved commercial service contract.

## NOAA — researched, not downloaded

- Official hourly observations: https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database ; search API documentation at https://www.ncei.noaa.gov/access/search/documentation/search-service/ .
- Hourly/synoptic station records, temperature/humidity/wind; record coverage and missingness vary by station and era. Some archives extend far back, but no station-level period is claimed here.
- A 2026 official notice announces an ISD service migration: https://www.nesdis.noaa.gov/news/service-location-change-integrated-surface-data-global-hourly . Do not hardcode an old endpoint without revalidation.
- Potential role: observed historical weather with station QA and publication-lag review. Not yet integrated; no NOAA features or results claimed. Verify dataset-specific federal/third-party usage terms before distributing data.

## California Energy Commission — researched, not downloaded

- Official entry: https://www.energy.ca.gov/data-reports/energy-almanac/california-electricity-data
- State/utility energy and generation statistics, often monthly/annual rather than hourly; file-specific periods, units, coverage and licenses must be checked before ingestion.
- Potential role: geographic context, annual plausibility checks and long-run energy trends, not direct hourly forecast labels. No implemented CEC ingestion, coverage or measured missingness claimed.

## Reproduction

`gridcast ingest` downloads only primary model inputs. `python pipelines/discover_sources.py` reacquires EIA and weather reference inputs using documented endpoints. The modeling pipeline does not depend on either reference source succeeding. All displayed model results use CAISO observations.
