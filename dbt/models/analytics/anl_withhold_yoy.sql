/*
  anl_withhold_yoy
  ================
  Year-over-year change in weighted average withhold rate by specialty (2023 vs 2024).
*/

with national as (
    select * from {{ ref('anl_withhold_national') }}
),

pivoted as (
    select
        specialty,
        max(case when year = 2023 then weighted_avg_withhold_rate end) as withhold_rate_2023,
        max(case when year = 2024 then weighted_avg_withhold_rate end) as withhold_rate_2024,
        max(case when year = 2023 then total_services end) as total_services_2023,
        max(case when year = 2024 then total_services end) as total_services_2024
    from national
    group by specialty
)

select
    specialty,
    withhold_rate_2023,
    withhold_rate_2024,
    round((withhold_rate_2024 - withhold_rate_2023)::numeric, 4) as withhold_rate_change,
    round(
        (withhold_rate_2024 - withhold_rate_2023) / nullif(withhold_rate_2023, 0),
        4
    ) as withhold_rate_pct_change,
    total_services_2023,
    total_services_2024,
    total_services_2024 - total_services_2023 as service_volume_change
from pivoted
where withhold_rate_2023 is not null
  and withhold_rate_2024 is not null
