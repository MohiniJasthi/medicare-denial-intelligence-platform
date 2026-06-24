/*
  anl_withhold_national
  =====================
  National specialty benchmarks by year — primary withhold analytics dataset.
*/

select
    specialty,
    year,
    sum(provider_count) as provider_count,
    sum(service_line_count) as service_line_count,
    sum(total_services) as total_services,
    sum(total_beneficiaries) as total_beneficiaries,
    round(
        sum(avg_withhold_rate * provider_count) / nullif(sum(provider_count), 0),
        4
    ) as weighted_avg_withhold_rate,
    round(avg(median_withhold_rate)::numeric, 4) as avg_median_withhold_rate,
    round(max(max_withhold_rate)::numeric, 4) as max_withhold_rate
from {{ ref('fct_utilization_by_specialty') }}
where specialty <> 'Unknown'
group by specialty, year
