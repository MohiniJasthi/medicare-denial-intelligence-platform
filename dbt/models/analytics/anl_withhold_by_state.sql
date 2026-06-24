/*
  anl_withhold_by_state
  =====================
  State × year withhold benchmarks for maps and geographic analysis.
*/

select
    state,
    year,
    count(distinct specialty) as specialty_count,
    sum(provider_count) as provider_count,
    sum(total_services) as total_services,
    round(
        sum(avg_withhold_rate * provider_count) / nullif(sum(provider_count), 0),
        4
    ) as weighted_avg_withhold_rate,
    round(avg(median_withhold_rate)::numeric, 4) as avg_median_withhold_rate
from {{ ref('fct_utilization_by_specialty') }}
where state <> 'Unknown'
group by state, year
