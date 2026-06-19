/*
  fct_utilization_by_specialty
  ============================
  Aggregated utilization and implied withhold metrics by specialty,
  state, and year — primary table for denial-pattern analytics.
*/

with utilization as (

    select * from {{ ref('int_utilization_enriched') }}

),

aggregated as (

    select
        coalesce(cms_specialty, 'Unknown')                        as specialty,
        coalesce(provider_state, 'Unknown')                       as state,
        year,

        count(distinct npi)                                       as provider_count,
        count(*)                                                  as service_line_count,
        sum(service_count)                                        as total_services,
        sum(unique_beneficiary_count)                             as total_beneficiaries,

        round(avg(avg_allowed_amount)::numeric, 2)                as avg_allowed_amount,
        round(avg(avg_medicare_payment)::numeric, 2)              as avg_medicare_payment,
        round(avg(implied_withhold_rate)::numeric, 4)             as avg_withhold_rate,
        round(
            percentile_cont(0.5) within group (order by implied_withhold_rate)::numeric,
            4
        )                                                         as median_withhold_rate,
        round(max(implied_withhold_rate)::numeric, 4)             as max_withhold_rate,

        current_timestamp                                         as _updated_at

    from utilization
    where implied_withhold_rate is not null
    group by 1, 2, 3

)

select
    md5(specialty || '-' || state || '-' || coalesce(cast(year as varchar), '')) as specialty_benchmark_id,
    *
from aggregated
