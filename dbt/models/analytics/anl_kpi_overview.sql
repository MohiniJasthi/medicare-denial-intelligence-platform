/*
  anl_kpi_overview
  ================
  Single-row KPI snapshot for dashboard title cards (Power BI / Streamlit).
*/

with counts as (
    select
        (select count(*) from {{ ref('dim_providers') }}) as provider_count,
        (select count(*) from {{ ref('fct_utilization_by_specialty') }}) as benchmark_row_count
),

withhold as (
    select
        round(avg(avg_withhold_rate)::numeric, 4) as national_avg_withhold_rate,
        round(avg(median_withhold_rate)::numeric, 4) as national_median_withhold_rate
    from {{ ref('fct_utilization_by_specialty') }}
    where specialty <> 'Unknown'
),

spending as (
    select
        round(sum(total_drug_cost)::numeric, 2) as total_part_d_cost,
        count(distinct npi) as part_d_prescriber_count,
        count(distinct drug_name) as distinct_drugs
    from {{ ref('fct_provider_spending') }}
)

select
    c.provider_count,
    c.benchmark_row_count,
    w.national_avg_withhold_rate,
    w.national_median_withhold_rate,
    s.total_part_d_cost,
    s.part_d_prescriber_count,
    s.distinct_drugs,
    current_timestamp as _updated_at
from counts c
cross join withhold w
cross join spending s
